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
import os
import subprocess
import sys
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from mqt.core.plugins.qiskit.exceptions import CircuitValidationError, JobSubmissionError, UnsupportedOperationError
from mqt.core.qdmi import ProgramFormat
from offline_service import CRN
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit.providers import JobStatus
from qiskit_service import open_backend

from ibm.qdmi import qiskit as adapter
from ibm.qdmi.qiskit import IBMBackend

if TYPE_CHECKING:
    from qiskit_service import RuntimeProxy


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


@pytest.mark.parametrize("use_environment", [False, True])
def test_session_overrides_and_existing_device(monkeypatch: pytest.MonkeyPatch, *, use_environment: bool) -> None:
    """Forward explicit or environment values without opening a native session."""
    device = Mock(spec=adapter.Device)
    opened = Mock(return_value=device)
    initialized = Mock(return_value=None)
    registered = Mock()
    monkeypatch.setattr(adapter, "open_device", opened)
    monkeypatch.setattr(adapter, "register_device", registered)
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
    registered.assert_called_once_with("ibm.default")
    opened.assert_called_once_with(
        "ibm.default",
        token="synthetic-key",  # ruff: ignore[hardcoded-password-func-arg] -- synthetic forwarding assertion
        custom1="ibm_test",
        custom2=CRN,
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
        token="synthetic-key",  # ruff: ignore[hardcoded-password-func-arg] -- synthetic test credential
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
from unittest.mock import Mock
from mqt.core.qdmi import driver
from ibm import qdmi
from ibm.qdmi import qiskit as adapter
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
