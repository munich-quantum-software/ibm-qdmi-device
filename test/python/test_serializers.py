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
from mqt.core.mlir import CompilerTarget
from mqt.core.qdmi import ProgramFormat
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.circuit import Parameter
from qiskit_service import open_backend, submitted_circuit

from ibm.qdmi.qiskit import IBMBackend

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mqt.core.mlir import CompiledProgram
    from qiskit_service import Runtime

pytestmark = pytest.mark.usefixtures("serialization_format")


@pytest.fixture(params=[ProgramFormat.QPY, ProgramFormat.QASM3])
def serialization_format(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise each advertised transport through the real provider and shared job."""
    serialize = IBMBackend._serialize_circuit  # ruff: ignore[private-member-access] Select the transport under test.

    def selected_format(
        backend: IBMBackend, circuit: QuantumCircuit, _formats: Iterable[ProgramFormat]
    ) -> tuple[CompiledProgram | str | bytes, ProgramFormat]:
        return serialize(backend, circuit, (request.param,))

    monkeypatch.setattr(IBMBackend, "_serialize_circuit", selected_format)


def test_classical_registers_batch_and_ordered_memory(runtime: Runtime) -> None:
    """Register names, declaration order, memory, and experiments survive a batch."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(QuantumRegister(5, "physical"), ClassicalRegister(3, "z"), ClassicalRegister(1, "a"))
    circuit.name = "first"
    circuit.x(4)
    circuit.measure(4, 0)
    circuit.measure(4, 2)
    circuit.measure(0, 3)
    other = circuit.copy(name="second")
    other.x(0)
    other.measure(0, 3)
    result = backend.run([circuit, other], shots=9, memory=True).result()
    assert result.results is not None
    assert result.get_memory(0) == ["0 101"] * 9
    assert result.get_memory(1) == ["1 101"] * 9
    assert result.get_counts(0) == {"0 101": 9}
    assert result.get_counts(1) == {"1 101": 9}
    assert [experiment.header["name"] for experiment in result.results] == ["first", "second"]
    assert result.results[0].header["creg_sizes"] == [["z", 3], ["a", 1]]
    submissions = runtime.snapshot()["submissions"]
    assert len(submissions) == 1
    pubs = submissions[0]["params"]["pubs"]
    assert len(pubs) == 2
    assert [pub[2] for pub in pubs] == [9, 9]
    if isinstance(pubs[0][0], str):
        assert submitted_circuit(pubs[0][0]).num_clbits == 2


def test_parameter_binding_and_classical_q_name(runtime: Runtime) -> None:
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
    pubs = [pub for request in runtime.snapshot()["submissions"] for pub in request["params"]["pubs"]]
    assert all(submitted_circuit(pub[0]).num_clbits == 1 for pub in pubs)


@pytest.mark.parametrize("name", ["ecr", "rzz"])
def test_native_gates_outside_standard_include(runtime: Runtime, name: str) -> None:
    """Native nonstandard gates remain named operations with importable declarations."""
    config = runtime.snapshot()["configuration"]
    config["gates"].append({
        "name": name,
        "parameters": ["theta"] if name == "rzz" else [],
        "coupling_map": config["coupling_map"] if name == "rzz" else [[3, 4]],
    })
    runtime.set_configuration("gates", config["gates"])
    runtime.set_configuration("basis_gates", [*config["basis_gates"], name])
    backend = open_backend(runtime)
    circuit = QuantumCircuit(5, 2)
    if name == "ecr":
        circuit.ecr(3, 4)
    else:
        circuit.rzz(math.pi / 4, 3, 4)
        target = CompilerTarget.from_device(backend.device)
        for angle, supported in [(0.0, True), (math.pi / 2, True), (-math.pi / 4, False), (math.pi, False)]:
            assert target.supports_operation("rzz", 2, 1, [3, 4], parameters=[angle]) is supported
            assert backend.target.instruction_supported("rzz", (3, 4), parameters=[angle]) is supported
    circuit.measure([3, 4], [0, 1])
    result = backend.run(circuit, shots=32, memory=True).result()
    assert sum(result.get_counts().values()) == 32
    assert Counter(result.get_memory()) == result.get_counts()
    source = runtime.snapshot()["submissions"][0]["params"]["pubs"][0][0]
    if isinstance(source, str):
        assert f"gate {name}" in source
    emitted = submitted_circuit(source)
    assert emitted.count_ops()[name] == 1
    instruction = next(item for item in emitted.data if item.operation.name == name)
    assert [emitted.find_bit(bit).index for bit in instruction.qubits] == [3, 4]
