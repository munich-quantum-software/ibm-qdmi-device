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

"""Public Qiskit execution through the real installed MQT Core/native stack."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import Mock

import numpy as np
import pytest
from mqt.core.mlir import TerminalReadout, serialize_program
from mqt.core.plugins.qiskit.exceptions import CircuitValidationError, JobSubmissionError, UnsupportedOperationError
from mqt.core.qdmi import Device, ProgramFormat
from offline_service import CRN
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit.providers import JobStatus
from qiskit.quantum_info import Operator
from qiskit_service import open_backend, submitted_circuit

from ibm.qdmi import qiskit as adapter
from ibm.qdmi.qiskit import IBMBackend

if TYPE_CHECKING:
    from qiskit_service import Runtime


def test_direct_qdmi_dynamical_decoupling(runtime: Runtime) -> None:
    """Send the documented JSON string through MQT Core's direct job API."""
    backend = open_backend(runtime)
    program = 'OPENQASM 3; include "stdgates.inc"; qubit[5] q; bit[1] c; x q[4]; c[0] = measure q[4];'
    job = backend.device.submit_job(
        program,
        ProgramFormat.QASM3,
        num_shots=7,
        custom2=json.dumps({"enable": True, "sequence_type": "XpXm"}),
    )
    job.wait(10)
    assert job.get_shots() == ["1"] * 7
    submitted = runtime.snapshot()["submissions"]
    assert len(submitted) == 1
    assert submitted[0]["params"]["options"]["dynamical_decoupling"]["enable"] is True
    assert submitted[0]["params"]["options"]["dynamical_decoupling"]["sequence_type"] == "XpXm"


def test_native_compiler_qasm_import(runtime: Runtime) -> None:
    """Native submission adds missing gate definitions and preserves physical/readout semantics."""
    config = runtime.snapshot()["configuration"]
    runtime.set_configuration("basis_gates", [*config["basis_gates"], "ecr", "rzz"])
    runtime.set_configuration(
        "gates",
        [
            *config["gates"],
            {"name": "ecr", "parameters": [], "coupling_map": [[3, 4]]},
            {"name": "rzz", "parameters": ["theta"], "coupling_map": [[3, 4]]},
        ],
    )
    backend = open_backend(runtime)
    circuit = QuantumCircuit(5, 4)
    circuit.x(4)
    circuit.ecr(3, 4)
    circuit.rzz(0.25, 3, 4)
    circuit.measure([3, 4, 3], [0, 2, 3])
    program = serialize_program(circuit, target=backend.device, terminal_readout=TerminalReadout.MEASURED)
    assert isinstance(program.payload, str)
    assert 'include "stdgates.inc";' in program.payload
    assert "gate ecr" not in program.payload
    assert "$3" in program.payload
    assert "$4" in program.payload
    job = backend.device.submit_job(program.payload, program.program_format, num_shots=16)
    assert job.wait(10)
    source = runtime.snapshot()["submissions"][0]["params"]["pubs"][0][0]
    emitted = submitted_circuit(source)
    emitted.remove_final_measurements()
    circuit.remove_final_measurements()
    np.testing.assert_allclose(
        Operator(emitted).data,
        Operator(circuit).data,
        atol=1e-12,
    )
    assert program.result_layout is not None
    shots = job.get_shots()
    assert len(shots) == 16
    for raw in shots:
        decoded = program.result_layout.decode_bits(raw)
        assert len(decoded) == 4
        assert decoded[2] == "0"
        assert decoded[0] == decoded[3]


@pytest.mark.parametrize("shots", [0, -1, True, 1.5])
def test_invalid_shots_submit_nothing(runtime: Runtime, shots: object) -> None:
    """Invalid shots never reach the native submission endpoint."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(1, 1)
    circuit.measure(0, 0)
    with pytest.raises(CircuitValidationError):
        backend.run(circuit, shots=shots)
    assert not runtime.snapshot()["submissions"]


@pytest.mark.parametrize("invalid", ["gate", "sites", "unbound", "unmeasured"])
def test_entire_batch_validated_before_submission(runtime: Runtime, invalid: str) -> None:
    """A later invalid circuit prevents even the first batch submission."""
    backend = open_backend(runtime)
    valid = QuantumCircuit(2, 2)
    valid.measure([0, 1], [0, 1])
    circuit = QuantumCircuit(2, 2)
    if invalid == "gate":
        circuit.h(0)
    elif invalid == "sites":
        circuit.cx(1, 0)
    elif invalid == "unbound":
        circuit.rz(Parameter("theta"), 0)
    if invalid != "unmeasured":
        circuit.measure([0, 1], [0, 1])
    with pytest.raises((CircuitValidationError, UnsupportedOperationError)):
        backend.run([valid, circuit])
    assert not runtime.snapshot()["submissions"]


def test_multi_program_submission_and_indexed_results(runtime: Runtime) -> None:
    """Distinct circuits share one request and retain their input order."""
    backend = open_backend(runtime)
    zero = QuantumCircuit(1, 1, name="zero", metadata={"index": 0})
    zero.measure(0, 0)
    one = QuantumCircuit(1, 1, name="one", metadata={"index": 1})
    one.x(0)
    one.measure(0, 0)
    job = backend.run([zero, one], shots=4, memory=True)
    result = job.result()
    assert result.get_counts(0) == {"0": 4}
    assert result.get_counts(1) == {"1": 4}
    results = result.results
    assert results is not None
    assert results[0].header["metadata"] == {"index": 0}
    assert results[1].header["metadata"] == {"index": 1}
    submissions = runtime.snapshot()["submissions"]
    assert len(submissions) == 1
    assert len(submissions[0]["params"]["pubs"]) == 2
    retrieved = open_backend(runtime).device.retrieve_job_by_id(job.job_id())
    assert retrieved.get_shots(0) == ["0"] * 4
    assert retrieved.get_shots(1) == ["1"] * 4


def test_failed_multi_program_submission_is_not_retried(runtime: Runtime) -> None:
    """An uncertain native submission never creates a replacement execution."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(1, 1)
    circuit.measure(0, 0)
    runtime.set_state("Queued", 1)
    with pytest.raises(JobSubmissionError):
        backend.run([circuit, circuit], shots=4)
    assert len(runtime.snapshot()["submissions"]) == 1
    assert not runtime.snapshot()["cancellations"]


def test_status_cancellation_and_retrieval(runtime: Runtime) -> None:
    """Job state and genuine results remain accessible through a fresh session."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(1, 1)
    circuit.x(0)
    circuit.measure(0, 0)
    runtime.set_state("Queued", 0)
    job = backend.run(circuit, shots=4, memory=True)
    assert job.status() == JobStatus.QUEUED
    assert job.cancel()
    assert job.status() == JobStatus.CANCELLED
    runtime.set_state("Completed", 0)
    job = backend.run(circuit, shots=4, memory=True)
    fresh = open_backend(runtime)
    retrieved = fresh.device.retrieve_job_by_id(job.job_id())
    assert retrieved.get_shots() == job.result().get_memory()
    assert len(runtime.snapshot()["submissions"]) == 2


@pytest.mark.parametrize("use_environment", [False, True])
def test_session_overrides_and_existing_device(monkeypatch: pytest.MonkeyPatch, *, use_environment: bool) -> None:
    """Forward explicit overrides and leave environment defaults to the native device."""
    device = Mock(spec=Device)
    opened = Mock(return_value=device)
    initialized = Mock(return_value=None)
    monkeypatch.setattr(adapter, "open_device", opened)
    monkeypatch.setattr(adapter.QDMIBackend, "__init__", initialized)
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "synthetic-key" if use_environment else "wrong-key")
    monkeypatch.setenv("IBM_QUANTUM_INSTANCE_CRN", CRN if use_environment else "wrong-crn")
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "ibm_test" if use_environment else "wrong-backend")
    IBMBackend(
        base_url="http://127.0.0.1:1",
        auth_url="http://127.0.0.1:1/auth",
        api_key=None if use_environment else "synthetic-key",
        instance_crn=None if use_environment else CRN,
        backend_name=None if use_environment else "ibm_test",
    )
    opened.assert_called_once_with(
        "ibm.default",
        token=None if use_environment else "synthetic-key",
        custom1=None if use_environment else "ibm_test",
        custom2=None if use_environment else CRN,
        base_url="http://127.0.0.1:1",
        auth_url="http://127.0.0.1:1/auth",
    )
    assert initialized.call_args.kwargs["device"] is device
    IBMBackend(device=device)
    assert initialized.call_args.kwargs["device"] is device
    assert opened.call_count == 1
    with pytest.raises(ValueError, match="exclusive"):
        IBMBackend(device=device, api_key="")


@pytest.mark.parametrize(("device_id", "backend_name"), [("ibm.berlin", "ibm_berlin"), ("ibm.aachen", "ibm_aachen")])
def test_concrete_catalogue_selection(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch, device_id: str, backend_name: str
) -> None:
    """Concrete IDs select their backend despite the generic environment default."""
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "wrong-backend")
    runtime.set_configuration("backend_name", backend_name)
    url = runtime.snapshot()["url"]
    backend = IBMBackend(device_id, api_key="synthetic-key", instance_crn=CRN, base_url=url, auth_url=url + "/auth")
    assert backend.device.name() == backend_name
    assert any(f"/backends/{backend_name}/configuration" in path for path, _, _ in runtime.snapshot()["requests"])


def test_generic_selection_required(runtime: Runtime, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing backend selection fails before authentication or metadata access."""
    monkeypatch.delenv("IBM_QUANTUM_BACKEND", raising=False)
    url = runtime.snapshot()["url"]
    with pytest.raises(ValueError, match="Allocating QDMI session"):
        IBMBackend(api_key="synthetic-key", instance_crn=CRN, base_url=url, auth_url=url + "/auth")
    assert not runtime.snapshot()["requests"]
