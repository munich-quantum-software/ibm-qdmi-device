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
import zlib
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mqt.core.mlir import sample
from offline_service import CRN, serve
from qiskit import qasm3, qpy

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
        """Simulate the submitted circuit and encode IBM-shaped results.

        Returns:
            Classified per-register samples in deliberately reversed key order.
        """
        outputs = []
        for source, parameters, shots in request["params"]["pubs"]:
            assert parameters is None
            circuit = submitted_circuit(source)
            program = source if isinstance(source, str) else circuit
            memory = [bits for bits, count in sample(program, shots=shots, seed=7).items() for _ in range(count)]
            data = {}
            for register in reversed(circuit.cregs):
                samples = []
                for bits in memory:
                    integer = int(bits.replace(" ", ""), 2)
                    value = sum(
                        ((integer >> circuit.find_bit(bit).index) & 1) << index for index, bit in enumerate(register)
                    )
                    samples.append(hex(value))
                data[register.name] = {"samples": samples, "num_bits": len(register)}
            outputs.append({"data": data})
        return {"results": outputs}

    def snapshot(self) -> dict[str, Any]:
        """Return recorded offline state without exposing server internals."""
        return deepcopy({
            "url": self.service.url,
            "requests": self.service.requests,
            "submissions": self.submissions,
            "cancellations": self.cancellations,
            "results": self.results,
            "configuration": self.service.data["configuration"],
        })

    def set_executor_result(self, result: dict[str, Any]) -> None:
        """Supply a synthetic Executor response without simulating samplex."""
        self.executor_result = deepcopy(result)

    def set_state(self, state: str, fail_submission: int) -> None:
        """Configure deterministic failure injection."""
        self.state = state
        self.fail_submission = fail_submission

    def set_configuration(self, key: str, value: object) -> None:
        """Override one synthetic metadata field before opening a session."""
        self.service.data["configuration"][key] = deepcopy(value)

    def set_properties(self, value: object) -> None:
        """Replace synthetic calibration metadata before opening a session."""
        self.service.data["properties"] = deepcopy(value)

    def set_failure(self, category: str) -> None:
        """Select a synthetic result or authentication failure."""
        self.cancel_failure = category == "cancellation"
        if self.cancel_failure:
            self.state = "Queued"
        self.status_unavailable = category == "status"
        self.invalid_results = category == "results"
        self.mismatch_retrieval = category == "retrieval"
        if category == "authentication":
            self.service.errors["auth"] = 401


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


@contextmanager
def runtime_service() -> Generator[Runtime, None, None]:
    """Run the synthetic HTTP service on a background thread.

    Yields:
        The service's recorded state and failure controls.
    """
    with serve() as service:
        yield configure(service)


def open_backend(runtime: Runtime) -> IBMBackend:
    """Open a fresh installed QDMI device against the synthetic endpoints.

    Returns:
        The public IBM backend.
    """
    from ibm.qdmi.qiskit import IBMBackend  # ruff: ignore[import-outside-top-level]

    return IBMBackend(
        api_key="synthetic-key",
        instance_crn=CRN,
        backend_name="ibm_test",
        base_url=runtime.snapshot()["url"],
        auth_url=runtime.snapshot()["url"] + "/auth",
    )
