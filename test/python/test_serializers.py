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

import math
from collections import Counter
from typing import TYPE_CHECKING

import pytest
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.circuit import Parameter
from qiskit_service import open_backend

if TYPE_CHECKING:
    from qiskit_service import RuntimeProxy


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
