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

from collections import Counter
from typing import TYPE_CHECKING

import pytest
from mqt.core.plugins.qiskit.job import QDMIJob
from qiskit import QuantumCircuit, transpile
from qiskit_service import open_backend

if TYPE_CHECKING:
    from qiskit_service import RuntimeProxy


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
