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

"""Disposable combined-branch behavior checks."""
from __future__ import annotations

import io
from functools import partial
from pathlib import Path

import pytest
from mqt.core.qdmi import ProgramFormat
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, qpy
from ibm.qdmi import _mock_runtime
from ibm.qdmi._catalogue import session_parameters
from ibm.qdmi.qiskit import IBMBackend


@pytest.mark.parametrize("setting", ["access_mode", "storage_config"])
def test_explicit_new_settings_never_select_mock(monkeypatch: pytest.MonkeyPatch, setting: str) -> None:
    monkeypatch.setattr(_mock_runtime, "connection", lambda _name: pytest.fail("selected mock"))
    parameters = session_parameters(
        backend_name="fake_lagos", api_key=None, instance_crn=None,
        base_url=None, auth_url=None,
        access_mode="quantum-system" if setting == "access_mode" else None,
        storage_config="private.json" if setting == "storage_config" else None,
    )
    assert parameters["custom1"] == "fake_lagos"
    assert parameters["base_url"] is None


@pytest.mark.simulator
def test_quantum_system_qpy(pytestconfig: pytest.Config, simulator_storage_file: Path) -> None:
    endpoint = pytestconfig.getoption("simulator_url")
    connect = partial(
        IBMBackend, backend_name="fake_lagos", api_key="synthetic-key",
        instance_crn="crn:v1:local:qsa_sim", base_url=endpoint,
        auth_url=endpoint + "/identity/token", access_mode="quantum-system",
        storage_config=str(simulator_storage_file),
    )
    backend = connect()
    circuits = []
    for initial in (0, 1):
        circuit = QuantumCircuit(QuantumRegister(7, "physical"), ClassicalRegister(2, "z"), ClassicalRegister(1, "a"))
        if initial:
            circuit.x(0)
        circuit.measure(0, 0)
        with circuit.if_test((circuit.clbits[0], 1)):
            circuit.x(1)
        circuit.measure(1, 1)
        circuit.measure(2, 2)
        circuits.append(circuit)
    job = backend.run(circuits, shots=16, memory=True)
    result = job.result()
    assert result.get_counts(0) == {"0 00": 16}
    assert result.get_counts(1) == {"0 11": 16}
    restored = connect().device.retrieve_job_by_id(job.job_id())
    assert restored.program_format == ProgramFormat.QPY
    assert restored.get_shots(0) == ["000"] * 16
    assert restored.get_shots(1) == ["011"] * 16
    (decoded,) = qpy.load(io.BytesIO(restored.get_program(bytes, 0)))
    assert [register.name for register in decoded.cregs] == ["z", "a"]
