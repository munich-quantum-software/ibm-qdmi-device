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

import base64
import io
import json
import os
import subprocess
import sys
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib.metadata import distribution
from multiprocessing import get_context
from multiprocessing.managers import BaseManager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from offline_service import CRN, serve
from qiskit import qasm3, qpy
from qiskit.circuit import ControlFlowOp
from qiskit.providers.basic_provider import BasicSimulator

if TYPE_CHECKING:
    from collections.abc import Generator

    from offline_service import Service
    from qiskit import QuantumCircuit

    from ibm.qdmi.qiskit import IBMBackend


def submitted_circuit(source: str | dict[str, Any]) -> QuantumCircuit:
    """Decode either circuit transport using Qiskit's reference readers.

    Returns:
        A circuit parsed independently of the native implementation.
    """
    if isinstance(source, dict):
        assert source["__type__"] == "QuantumCircuit"
        (circuit,) = qpy.load(io.BytesIO(zlib.decompress(base64.b64decode(source["__value__"]))))
        return circuit
    return qasm3.loads(source)


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
    status_unavailable: bool = False
    invalid_results: bool = False
    mismatch_retrieval: bool = False
    result_reads: int = 0
    executor_result: dict[str, Any] = field(default_factory=dict)

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
                "program": {"id": request["program_id"]},
                "params": request["params"],
                "state": {"status": self.state},
            }
            self.results[identifier] = (
                self.executor_result if request["program_id"] == "executor" else self.simulate(request)
            )
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
        if self.status_unavailable:
            return 400, {}
        return 200, self.jobs[identifier]

    @staticmethod
    def simulate(request: dict[str, Any]) -> dict[str, Any]:
        """Simulate the actual submitted OpenQASM and encode IBM-shaped results.

        Returns:
            Classified per-register samples in deliberately reversed key order.
        """
        outputs = []
        for source, parameters, shots in request["params"]["pubs"]:
            assert parameters is None
            circuit = submitted_circuit(source)
            if any(isinstance(item.operation, ControlFlowOp) for item in circuit.data):
                environment = os.environ.copy()
                if sys.platform == "linux":
                    # Allocate TLS for the wheel's OpenMP runtime at process startup.
                    aer = distribution("qiskit-aer")
                    libraries = [
                        str(aer.locate_file(path))
                        for path in aer.files or ()
                        if path.parent.name == "qiskit_aer.libs"
                        and path.name.startswith("libgomp")
                        and ".so" in path.name
                    ]
                    environment["LD_PRELOAD"] = " ".join([*libraries, environment.get("LD_PRELOAD", "")]).strip()
                memory = json.loads(
                    subprocess.check_output(  # ruff: ignore[subprocess-without-shell-equals-true] Fixed reference; payload uses stdin.
                        [sys.executable, str(Path(__file__).with_name("aer_reference.py")), str(shots)],
                        input=json.dumps(source).encode(),
                        timeout=30,
                        env=environment,
                    )
                )
            else:
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
            outputs.append({"data": data})
        return {"results": outputs}


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

    def set_executor_result(self, result: dict[str, Any]) -> None:
        """Supply a synthetic Executor response without simulating samplex."""
        self.runtime.executor_result = result

    def set_state(self, state: str, fail_submission: int) -> None:
        """Configure deterministic failure injection."""
        self.runtime.state = state
        self.runtime.fail_submission = fail_submission

    def set_configuration(self, key: str, value: object) -> None:
        """Override one synthetic metadata field before opening a session."""
        self.runtime.service.data["configuration"][key] = value

    def set_properties(self, value: object) -> None:
        """Replace synthetic calibration metadata before opening a session."""
        self.runtime.service.data["properties"] = value

    def set_failure(self, category: str) -> None:
        """Select a synthetic result or authentication failure."""
        self.runtime.cancel_failure = category == "cancellation"
        if self.runtime.cancel_failure:
            self.runtime.state = "Queued"
        self.runtime.status_unavailable = category == "status"
        self.runtime.invalid_results = category == "results"
        self.runtime.mismatch_retrieval = category == "retrieval"
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

    def set_executor_result(self, result: dict[str, Any]) -> None:
        """Supply a synthetic Executor response."""
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

    def set_properties(self, value: object) -> None:
        """Replace backend calibration metadata."""
        ...


class RuntimeManager(BaseManager):
    """Own the separate process hosting the synthetic service."""

    if TYPE_CHECKING:

        def runtime(self) -> RuntimeProxy:
            """Create a proxy using the manager's registered factory."""
            ...


RuntimeManager.register("runtime", RuntimeServer)


@contextmanager
def remote_runtime() -> Generator[RuntimeProxy, None, None]:
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


def open_backend(runtime: RuntimeProxy) -> IBMBackend:
    """Open a fresh installed QDMI device against the synthetic endpoints.

    Returns:
        The public IBM backend.
    """
    from ibm.qdmi.qiskit import IBMBackend  # ruff: ignore[import-outside-top-level] Keep LLVM out of the service.

    return IBMBackend(
        api_key="synthetic-key",
        instance_crn=CRN,
        backend_name="ibm_test",
        base_url=runtime.snapshot()["url"],
        auth_url=runtime.snapshot()["url"] + "/auth",
    )
