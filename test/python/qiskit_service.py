# Copyright (c) 2026 Munich Quantum Software Company GmbH
# All rights reserved.
#
# Licensed under the Apache License v2.0 with LLVM Exceptions (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://llvm.org/LICENSE.txt
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
#
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception

"""Synthetic Sampler REST service; no external network or recorded hardware data."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from multiprocessing import get_context
from multiprocessing.managers import BaseManager
from typing import TYPE_CHECKING, Any, Protocol

from offline_service import serve
from qiskit import qasm3
from qiskit.providers.basic_provider import BasicSimulator

if TYPE_CHECKING:
    from collections.abc import Iterator

    from offline_service import Service


@dataclass
class Runtime:
    """Record native submissions and simulate only small offline circuits."""

    service: Service
    submissions: list[dict[str, Any]] = field(default_factory=list)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    cancellations: list[str] = field(default_factory=list)
    fail_submission: int = 0
    state: str = "Completed"
    cancel_failure: bool = False
    invalid_results: bool = False
    mismatch_retrieval: bool = False
    result_reads: int = 0
    job_reads: int = 0
    inconsistent_state: bool = False

    def respond(self, path: str, body: bytes) -> tuple[int, Any]:
        """Handle one synthetic request with independently stored job state.

        Returns:
            HTTP status and JSON response.
        """
        if path.endswith("/jobs"):
            request = json.loads(body)
            self.submissions.append(request)
            if len(self.submissions) == self.fail_submission:
                return 503, {}
            identifier = f"synthetic-{len(self.submissions)}"
            self.jobs[identifier] = {
                "id": identifier,
                "backend": request["backend"],
                "program": {"id": "sampler"},
                "params": request["params"],
                "state": {"status": self.state},
            }
            self.results[identifier] = self.simulate(request)
            return 200, {"id": identifier, "backend": request["backend"]}
        identifier = path.split("/jobs/")[1].split("/", maxsplit=1)[0]
        if path.endswith("/cancel"):
            self.cancellations.append(identifier)
            if self.cancel_failure:
                return 503, {}
            self.jobs[identifier]["state"]["status"] = "Cancelled"
            return 204, {}
        if path.endswith("/results"):
            self.result_reads += 1
            if self.invalid_results:
                return 200, {}
            data = self.results[identifier]
            if self.mismatch_retrieval and self.result_reads > 1:
                data = json.loads(json.dumps(data))
                samples = next(iter(data["results"][0]["data"].values()))["samples"]
                samples[0] = "0x0"
            return 200, data
        self.job_reads += 1
        if self.inconsistent_state and self.job_reads == 2:
            return 200, {**self.jobs[identifier], "state": {"status": "Queued"}}
        return 200, self.jobs[identifier]

    @staticmethod
    def simulate(request: dict[str, Any]) -> dict[str, Any]:
        """Simulate the actual submitted OpenQASM and encode IBM-shaped results.

        Returns:
            Classified per-register samples in deliberately reversed key order.
        """
        source, parameters, shots = request["params"]["pubs"][0]
        assert parameters is None
        circuit = qasm3.loads(source)
        memory = (
            BasicSimulator()
            .run(circuit.decompose(reps=4), shots=shots, memory=True, seed_simulator=7)
            .result()
            .get_memory()
        )
        data = {}
        for register in reversed(circuit.cregs):
            samples = []
            for sample in memory:
                integer = int(sample.replace(" ", ""), 2)
                value = sum(
                    ((integer >> circuit.find_bit(bit).index) & 1) << index for index, bit in enumerate(register)
                )
                samples.append(hex(value))
            data[register.name] = {"samples": samples, "num_bits": len(register)}
        return {"results": [{"data": data}]}


def configure(service: Service) -> Runtime:
    """Configure a five-qubit chain with IBM-shaped native basis metadata.

    Returns:
        The synthetic runtime attached to the loopback service.
    """
    config = service.data["configuration"]
    config["n_qubits"] = 5
    config["basis_gates"] = ["x", "sx", "rz", "cx"]
    config["supported_instructions"] = ["x", "sx", "rz", "cx", "measure", "reset", "delay", "if_else"]
    config["coupling_map"] = [[0, 1], [1, 2], [2, 3], [3, 4]]
    config["gates"] = [
        {"name": name, "parameters": params, "coupling_map": [[i] for i in range(5)]}
        for name, params in [("x", []), ("sx", []), ("rz", ["theta"])]
    ] + [{"name": "cx", "parameters": [], "coupling_map": config["coupling_map"]}]
    service.data["properties"]["qubits"] = [
        [
            {"name": "T1", "value": 100, "unit": "us"},
            {"name": "readout_error", "value": 0.02},
            {"name": "readout_length", "value": 1.5, "unit": "us"},
        ]
        for _ in range(5)
    ]
    runtime = Runtime(service)
    service.respond = runtime.respond
    return runtime


class RuntimeServer:
    """Own a synthetic HTTP server in a process separate from native bindings."""

    def __init__(self) -> None:
        """Start the synthetic HTTP service and configure its backend."""
        self.context = serve()
        self.runtime = configure(self.context.__enter__())

    def snapshot(self) -> dict[str, Any]:
        """Return recorded offline state without exposing server internals."""
        return {
            "url": self.runtime.service.url,
            "requests": self.runtime.service.requests,
            "submissions": self.runtime.submissions,
            "cancellations": self.runtime.cancellations,
            "results": self.runtime.results,
            "configuration": self.runtime.service.data["configuration"],
        }

    def set_state(self, state: str, fail_submission: int) -> None:
        """Configure deterministic failure injection."""
        self.runtime.state = state
        self.runtime.fail_submission = fail_submission

    def set_configuration(self, key: str, value: object) -> None:
        """Override one synthetic metadata field before opening a session."""
        self.runtime.service.data["configuration"][key] = value

    def set_failure(self, category: str) -> None:
        """Select a synthetic result or authentication failure."""
        self.runtime.cancel_failure = category == "cancellation"
        if self.runtime.cancel_failure:
            self.runtime.state = "Queued"
        self.runtime.invalid_results = category == "results"
        self.runtime.mismatch_retrieval = category == "retrieval"
        self.runtime.inconsistent_state = category == "status-regression"
        if category == "authentication":
            self.runtime.service.errors["auth"] = 401

    def close(self) -> None:
        """Stop the HTTP server before its owning process exits."""
        self.context.__exit__(None, None, None)


class RuntimeProxy(Protocol):
    """The methods exposed by the multiprocessing manager."""

    def snapshot(self) -> dict[str, Any]:
        """Return the synthetic state."""
        ...

    def set_state(self, state: str, fail_submission: int) -> None:
        """Change synthetic job behavior."""
        ...

    def set_failure(self, category: str) -> None:
        """Select a synthetic failure."""
        ...

    def close(self) -> None:
        """Stop the synthetic service."""
        ...

    def set_configuration(self, key: str, value: object) -> None:
        """Override one backend configuration field."""
        ...


class RuntimeManager(BaseManager):
    """Own the separate process hosting the synthetic service."""

    if TYPE_CHECKING:

        def runtime(self) -> RuntimeProxy:
            """Create a proxy using the manager's registered factory."""
            ...


RuntimeManager.register("runtime", RuntimeServer)


@contextmanager
def remote_runtime() -> Iterator[RuntimeProxy]:
    """Host HTTP outside the native binding's Python GIL.

    Yields:
        A local IPC proxy for inspecting and configuring the synthetic service.
    """
    with RuntimeManager(ctx=get_context("spawn")) as manager:
        proxy = manager.runtime()
        try:
            yield proxy
        finally:
            proxy.close()
