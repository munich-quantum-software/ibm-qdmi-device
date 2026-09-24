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

import gc
import json
import math
import os
import subprocess
import sys
from collections import Counter
from typing import TYPE_CHECKING

import numpy as np
import pytest
from mqt.core.plugins.qiskit.exceptions import CircuitValidationError, JobSubmissionError, UnsupportedOperationError
from mqt.core.plugins.qiskit.job import QDMIJob
from mqt.core.qdmi import ProgramFormat
from offline_service import CRN
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, transpile
from qiskit.circuit import Parameter
from qiskit.providers import JobStatus
from qiskit.quantum_info import SparsePauliOp
from qiskit_service import remote_runtime

from ibm.qdmi.qiskit import IBMBackend

if TYPE_CHECKING:
    from collections.abc import Iterator

    from qiskit_service import RuntimeProxy


@pytest.fixture
def runtime() -> Iterator[RuntimeProxy]:
    """Attach the synthetic runtime and release any Python job cycles.

    Yields:
        The loopback service and its recorded submissions.
    """
    with remote_runtime() as proxy:
        yield proxy
        gc.collect()


def open_backend(runtime: RuntimeProxy) -> IBMBackend:
    """Open a fresh installed QDMI device against the synthetic endpoints.

    Returns:
        The public IBM backend.
    """
    return IBMBackend(
        api_key="synthetic-key",
        instance_crn=CRN,
        backend_name="ibm_test",
        base_url=runtime.snapshot()["url"],
        auth_url=runtime.snapshot()["url"] + "/auth",
    )


def test_metadata_target_and_transpilation(runtime: RuntimeProxy) -> None:
    """Target properties use physical sites, signatures, and seconds."""
    backend = open_backend(runtime)
    assert backend.num_qubits == 5
    assert set(backend.target.operation_names) == {"x", "sx", "rz", "cx", "measure", "reset", "barrier"}
    assert set(backend.target["cx"]) == {(0, 1), (1, 2), (2, 3), (3, 4)}
    assert backend.target["cx"][0, 1].duration == pytest.approx(35556e-12)
    assert backend.target["cx"][0, 1].error == pytest.approx(0.02)
    assert backend.target["measure"][4,].duration == pytest.approx(1.5e-6)
    assert backend.target["measure"][4,].error == pytest.approx(0.02)
    circuit = QuantumCircuit(2, 2, name="physical-bell", metadata={"experiment": 7})
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [1, 0])
    compiled = transpile(circuit, backend, initial_layout=[3, 4], optimization_level=0, seed_transpiler=2)
    job = backend.run(compiled, shots=128, memory=True)
    assert isinstance(job, QDMIJob)
    result = job.result()
    assert result.results is not None
    assert result.results[0].header["name"] == "physical-bell"
    assert result.results[0].header["metadata"] == {"experiment": 7}
    assert Counter(result.get_memory()) == result.get_counts()
    assert set(result.get_counts()) == {"00", "11"}
    source = runtime.snapshot()["submissions"][0]["params"]["pubs"][0][0]
    assert "qubit[5] q;" in source
    assert "cx q[3], q[4];" in source
    assert "q[0]" not in source
    assert runtime.snapshot()["submissions"][0]["cost"] == 60
    assert runtime.snapshot()["submissions"][0]["params"]["support_qiskit"] is False


def test_repeated_measurement_calibration_opens_backend(runtime: RuntimeProxy) -> None:
    """IBM's qubit and gate readout records describe one target calibration."""
    runtime.set_properties({
        "qubits": [
            [
                {"name": "readout_error", "value": 0.02},
                {"name": "readout_length", "value": 1.5, "unit": "us"},
            ]
            for _ in range(5)
        ],
        "gates": [
            {
                "gate": "measure",
                "qubits": [site],
                "parameters": [
                    {"name": "gate_error", "value": 0.02},
                    {"name": "gate_length", "value": 1.5, "unit": "us"},
                ],
            }
            for site in range(5)
        ],
    })
    backend = open_backend(runtime)
    assert backend.target["measure"][4,].duration == pytest.approx(1.5e-6)
    assert backend.target["measure"][4,].error == pytest.approx(0.02)


def test_classical_registers_batch_and_ordered_memory(runtime: RuntimeProxy) -> None:
    """Register names, declaration order, memory, and experiments survive a batch."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(QuantumRegister(5, "physical"), ClassicalRegister(2, "z"), ClassicalRegister(1, "a"))
    circuit.name = "first"
    circuit.x(4)
    circuit.measure(4, 0)
    circuit.measure(0, 2)
    other = circuit.copy(name="second")
    other.x(0)
    other.measure(0, 2)
    result = backend.run([circuit, other], shots=9, memory=True).result()
    assert result.results is not None
    assert result.get_memory(0) == ["0 01"] * 9
    assert result.get_memory(1) == ["1 01"] * 9
    assert result.get_counts(0) == {"0 01": 9}
    assert result.get_counts(1) == {"1 01": 9}
    assert [experiment.header["name"] for experiment in result.results] == ["first", "second"]
    assert result.results[0].header["creg_sizes"] == [["z", 2], ["a", 1]]
    assert len(runtime.snapshot()["submissions"]) == 2


def test_direct_qdmi_dynamical_decoupling(runtime: RuntimeProxy) -> None:
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


def test_parameter_binding_and_classical_q_name(runtime: RuntimeProxy) -> None:
    """Binding preserves an independently named classical register."""
    backend = open_backend(runtime)
    theta = Parameter("theta")
    circuit = QuantumCircuit(QuantumRegister(1, "wire"), ClassicalRegister(1, "q"))
    circuit.sx(0)
    circuit.rz(theta, 0)
    circuit.sx(0)
    circuit.measure(0, 0)
    job = backend.run([circuit, circuit], parameter_values=[{theta: 0}, [math.pi]], shots=7, memory=True)
    assert job.result().get_counts(0) == {"1": 7}
    assert job.result().get_counts(1) == {"0": 7}
    assert all("bit[1] c0;" in request["params"]["pubs"][0][0] for request in runtime.snapshot()["submissions"])


@pytest.mark.parametrize("shots", [0, -1, True, 1.5])
def test_invalid_shots_submit_nothing(runtime: RuntimeProxy, shots: object) -> None:
    """Invalid shots never reach the native submission endpoint."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(1, 1)
    circuit.measure(0, 0)
    with pytest.raises(CircuitValidationError):
        backend.run(circuit, shots=shots)
    assert not runtime.snapshot()["submissions"]


@pytest.mark.parametrize("invalid", ["gate", "control", "sites", "unbound", "unmeasured"])
def test_entire_batch_validated_before_submission(runtime: RuntimeProxy, invalid: str) -> None:
    """A later invalid circuit prevents even the first batch submission."""
    backend = open_backend(runtime)
    valid = QuantumCircuit(2, 2)
    valid.measure([0, 1], [0, 1])
    circuit = QuantumCircuit(2, 2)
    if invalid == "gate":
        circuit.h(0)
    elif invalid == "control":
        with circuit.if_test((circuit.clbits[0], True)):
            circuit.x(0)
    elif invalid == "sites":
        circuit.cx(1, 0)
    elif invalid == "unbound":
        circuit.rz(Parameter("theta"), 0)
    if invalid != "unmeasured":
        circuit.measure([0, 1], [0, 1])
    with pytest.raises((CircuitValidationError, UnsupportedOperationError)):
        backend.run([valid, circuit])
    assert not runtime.snapshot()["submissions"]


def test_partial_submission_cancels_earlier_jobs(runtime: RuntimeProxy) -> None:
    """The shared adapter cancels earlier jobs after a later submission fails."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(1, 1)
    circuit.measure(0, 0)
    runtime.set_state("Queued", 2)
    with pytest.raises(JobSubmissionError):
        backend.run([circuit, circuit, circuit], shots=4)
    assert len(runtime.snapshot()["submissions"]) == 2
    assert runtime.snapshot()["cancellations"] == ["synthetic-1"]


def test_status_cancellation_and_retrieval(runtime: RuntimeProxy) -> None:
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


def test_session_overrides_and_existing_device(runtime: RuntimeProxy, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit values override environment defaults; an open device is exclusive."""
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "wrong-key")
    monkeypatch.setenv("IBM_QUANTUM_INSTANCE_CRN", "wrong-crn")
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "wrong-backend")
    backend = open_backend(runtime)
    assert backend.device.name() == "ibm_test"
    adapted = IBMBackend(device=backend.device)
    assert adapted.device is backend.device
    with pytest.raises(ValueError, match="exclusive"):
        IBMBackend(device=backend.device, api_key="")
    assert all("wrong-key" not in body.decode() for _, _, body in runtime.snapshot()["requests"])


@pytest.mark.parametrize(("device_id", "backend_name"), [("ibm.berlin", "ibm_berlin"), ("ibm.aachen", "ibm_aachen")])
def test_concrete_catalogue_selection(
    runtime: RuntimeProxy, monkeypatch: pytest.MonkeyPatch, device_id: str, backend_name: str
) -> None:
    """Concrete IDs select their backend despite the generic environment default."""
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "wrong-backend")
    runtime.set_configuration("backend_name", backend_name)
    url = runtime.snapshot()["url"]
    backend = IBMBackend(device_id, api_key="synthetic-key", instance_crn=CRN, base_url=url, auth_url=url + "/auth")
    assert backend.device.name() == backend_name
    assert any(f"/backends/{backend_name}/configuration" in path for path, _, _ in runtime.snapshot()["requests"])


def test_generic_selection_required(runtime: RuntimeProxy, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing backend selection fails before authentication or metadata access."""
    monkeypatch.delenv("IBM_QUANTUM_BACKEND", raising=False)
    url = runtime.snapshot()["url"]
    with pytest.raises(RuntimeError):
        IBMBackend(api_key="synthetic-key", instance_crn=CRN, base_url=url, auth_url=url + "/auth")
    assert not runtime.snapshot()["requests"]


def test_inherited_factory(runtime: RuntimeProxy) -> None:
    """The shared factory can pass provider and registry metadata to the subclass."""
    registered = open_backend(runtime)
    url = runtime.snapshot()["url"]
    backend = IBMBackend.from_device_id(
        "ibm.default",
        token="synthetic-key",  # ruff: ignore[hardcoded-password-func-arg] -- synthetic loopback credential
        custom1="ibm_test",
        custom2=CRN,
        base_url=url,
        auth_url=url + "/auth",
    )
    assert isinstance(backend, IBMBackend)
    assert backend.device_id == "ibm.default"
    assert backend.device is not registered.device
    circuit = QuantumCircuit(1, 1)
    circuit.x(0)
    circuit.measure(0, 0)
    assert backend.run(circuit, shots=3).result().get_counts() == {"1": 3}


def test_administrator_default(runtime: RuntimeProxy) -> None:
    """An isolated registry keeps configured defaults and explicit precedence."""
    script = """
import os
import sys
from mqt.core.qdmi import driver
from ibm import qdmi
from ibm.qdmi.qiskit import IBMBackend
driver.register_device(driver.DeviceDefinition(
    'ibm.default', qdmi.IBM_QDMI_LIBRARY_PATH, 'IBM', custom1='ibm_test',
    token='synthetic-key', custom2=sys.argv[2],
    base_url=sys.argv[1], auth_url=sys.argv[1] + '/auth',
))
assert IBMBackend().device.name() == 'ibm_test'
os.environ['IBM_QUANTUM_BACKEND'] = 'wrong-backend'
assert IBMBackend(backend_name='ibm_test').device.name() == 'ibm_test'
del os.environ['IBM_QUANTUM_BACKEND']
assert IBMBackend().device.name() == 'ibm_test'
"""
    env = {
        key: value for key, value in os.environ.items() if not key.startswith(("IBM_QUANTUM_", "MQT_CORE_QDMI_CONFIG_"))
    }
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed script and loopback inputs
        [sys.executable, "-c", script, runtime.snapshot()["url"], CRN],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert not runtime.snapshot()["submissions"]


def test_incomplete_gate_signature_is_not_exposed(runtime: RuntimeProxy) -> None:
    """Missing or contradictory metadata cannot widen the transpilation target."""
    gates = runtime.snapshot()["configuration"]["gates"]
    gates[0]["parameters"] = ["unexpected"]
    gates[1]["coupling_map"] = []
    runtime.set_configuration("gates", gates)
    backend = open_backend(runtime)
    assert "x" not in backend.target.operation_names
    assert "sx" not in backend.target.operation_names
    assert "measure" in backend.target.operation_names


@pytest.mark.parametrize("name", ["ecr", "rzz"])
def test_native_gates_outside_standard_include(runtime: RuntimeProxy, name: str) -> None:
    """Native nonstandard gates remain named operations with importable declarations."""
    config = runtime.snapshot()["configuration"]
    config["gates"].append({"name": name, "parameters": ["theta"] if name == "rzz" else [], "coupling_map": [[3, 4]]})
    runtime.set_configuration("gates", config["gates"])
    runtime.set_configuration("basis_gates", [*config["basis_gates"], name])
    backend = open_backend(runtime)
    circuit = QuantumCircuit(5, 2)
    if name == "ecr":
        circuit.ecr(3, 4)
    else:
        circuit.rzz(math.pi / 4, 3, 4)
    circuit.measure([3, 4], [0, 1])
    result = backend.run(circuit, shots=32, memory=True).result()
    assert sum(result.get_counts().values()) == 32
    assert Counter(result.get_memory()) == result.get_counts()
    source = runtime.snapshot()["submissions"][0]["params"]["pubs"][0][0]
    assert f"gate {name}" in source
    assert "q[3], q[4]" in source


@pytest.mark.parametrize("precision", [0, -0.1])
def test_invalid_estimator_precision_submits_nothing(runtime: RuntimeProxy, precision: float) -> None:
    """Invalid primitive precision cannot create a native job."""
    backend = open_backend(runtime)
    with pytest.raises(ValueError, match="precision"):
        backend.estimator().run([(QuantumCircuit(1), SparsePauliOp("Z"))], precision=precision).result()
    assert not runtime.snapshot()["submissions"]


def test_sampler_parameter_broadcast_and_registers(runtime: RuntimeProxy) -> None:
    """The shared BackendSamplerV2 expands bound PUBs and preserves registers."""
    backend = open_backend(runtime)
    theta = Parameter("theta")
    circuit = QuantumCircuit(QuantumRegister(1, "q"), ClassicalRegister(1, "z"), ClassicalRegister(1, "a"))
    circuit.sx(0)
    circuit.rz(theta, 0)
    circuit.sx(0)
    circuit.measure(0, circuit.cregs[0][0])
    circuit.measure(0, circuit.cregs[1][0])
    result = backend.sampler(default_shots=32).run([(circuit, {theta: np.array([[0.0], [math.pi]])})]).result()[0]
    assert result.data["z"].get_counts(0) == {"1": 32}
    assert result.data["z"].get_counts(1) == {"0": 32}
    assert result.data["a"].get_counts(0) == {"1": 32}
    assert len(runtime.snapshot()["submissions"]) == 2
    assert all(request["params"]["pubs"][0][2] == 32 for request in runtime.snapshot()["submissions"])


def test_estimator_precision_observables_and_layout(runtime: RuntimeProxy) -> None:
    """The shared estimator maps observables and produces finite-shot expectations."""
    backend = open_backend(runtime)
    theta = Parameter("theta")
    circuit = QuantumCircuit(1)
    circuit.ry(theta, 0)
    mapped = transpile(circuit, backend, initial_layout=[4], optimization_level=0)
    observable = SparsePauliOp("Z").apply_layout(mapped.layout)
    result = (
        backend
        .estimator()
        .run([(mapped, observable, {theta: np.array([[0.0], [math.pi]])})], precision=0.125)
        .result()[0]
    )
    np.testing.assert_allclose(result.data["evs"], [1, -1], atol=1e-12)
    np.testing.assert_allclose(result.data["stds"], [0, 0], atol=1e-12)
    assert len(runtime.snapshot()["submissions"]) == 2
    assert all(request["params"]["pubs"][0][2] == 64 for request in runtime.snapshot()["submissions"])
    assert all(request["cost"] == 60 for request in runtime.snapshot()["submissions"])
