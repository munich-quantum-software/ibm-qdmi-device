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

"""Exercise the installed framework adapter against Quantum System API."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import pennylane as qml
import pytest
from qiskit import QuantumCircuit, transpile

from ibm.qdmi.pennylane import IBMDevice
from ibm.qdmi.qiskit import IBMBackend

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.simulator


def test_quantum_system_qiskit(pytestconfig: pytest.Config, simulator_storage_file: Path) -> None:
    """Sample, use a primitive, and retrieve through the installed native library."""
    endpoint = pytestconfig.getoption("simulator_url")
    connect = partial(
        IBMBackend,
        backend_name="fake_lagos",
        api_key="synthetic-key",
        instance_crn="crn:v1:local:qsa_sim",
        base_url=endpoint,
        auth_url=endpoint + "/identity/token",
        access_mode="quantum-system",
        storage_config=str(simulator_storage_file),
    )
    backend = connect()
    circuit = QuantumCircuit(2, 2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    compiled = transpile(circuit, backend, seed_transpiler=7)
    job = backend.run([compiled, compiled], shots=64, memory=True)
    result = job.result()
    assert sum(result.get_counts(0).values()) == 64
    assert set(result.get_counts(1)) <= {"00", "11"}
    fresh = connect()
    restored = fresh.device.retrieve_job_by_id(job.job_id())
    assert restored.get_shots(0) == result.get_memory(0)
    output = backend.sampler().run([compiled], shots=16).result()
    assert sum(output[0].data["c"].get_counts().values()) == 16

    device = IBMDevice(
        wires=2,
        backend_name="fake_lagos",
        api_key="synthetic-key",
        instance_crn="crn:v1:local:qsa_sim",
        base_url=endpoint,
        auth_url=endpoint + "/identity/token",
        access_mode="quantum-system",
        storage_config=str(simulator_storage_file),
    )

    @qml.qnode(device, shots=16)
    def bell() -> qml.measurements.MeasurementProcess:
        qml.Hadamard(0)
        qml.CNOT([0, 1])
        return qml.sample(wires=[0, 1])

    samples = bell()
    assert samples.shape == (16, 2)
    assert all(sample[0] == sample[1] for sample in samples)
