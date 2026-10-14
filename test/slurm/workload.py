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

"""Exercise IBM adapters with the device allocated by Slurm."""

from __future__ import annotations

import os
from pathlib import Path

import pennylane as qml
from mqt.core.qdmi import builtin_driver as qdmi_driver
from qiskit import QuantumCircuit

from ibm.qdmi import IBM_QDMI_LIBRARY_PATH
from ibm.qdmi.pennylane import IBMDevice
from ibm.qdmi.qiskit import IBMBackend


def main() -> None:
    """Submit and retrieve synthetic results through the selected native library."""
    # This workload requests one local Slurm license with count one.
    device_id = os.environ["SLURM_JOB_LICENSES"].removesuffix(":1")
    device = qdmi_driver.open_device(device_id)
    assert str(IBM_QDMI_LIBRARY_PATH.resolve()) in Path("/proc/self/maps").read_text(encoding="utf-8")
    assert device.name() == "ibm_berlin"
    assert device.qubits_num() == 5
    backend = IBMBackend(device=device)
    circuit = QuantumCircuit(2, 2)
    circuit.x(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    job = backend.run(circuit, shots=8)
    assert job.result().get_counts() == {"11": 8}
    assert device.retrieve_job_by_id(job.job_id()).get_shots() == ["11"] * 8

    adapter = IBMDevice(device=device, wires=2)

    @qml.qnode(adapter, shots=8)
    def sample() -> qml.measurements.CountsMP:
        qml.X(0)
        qml.CNOT(wires=[0, 1])
        return qml.counts(wires=[0, 1])

    assert sample() == {"11": 8}


if __name__ == "__main__":
    main()
