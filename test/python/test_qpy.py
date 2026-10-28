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

"""QPY serialization and measurement feedforward through the native device."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from mqt.core.plugins.qiskit.exceptions import CircuitValidationError, UnsupportedOperationError
from mqt.core.qdmi import ProgramFormat
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, qpy
from qiskit.circuit.classical import expr
from qiskit_service import open_backend, submitted_circuit

from ibm.qdmi.serializers import qiskit_to_qasm3

if TYPE_CHECKING:
    from qiskit_service import RuntimeProxy


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_angles_submit_nothing(runtime: RuntimeProxy, value: float) -> None:
    """Native gate parameters must be finite before QPY serialization."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(5, 1)
    circuit.rz(value, 4)
    circuit.measure(4, 0)
    with pytest.raises(CircuitValidationError, match="finite"):
        backend.run(circuit)
    assert not runtime.snapshot()["submissions"]


def test_native_binary_batch_and_retrieval(runtime: RuntimeProxy) -> None:
    """Binary programs and register ordering survive submission and retrieval."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(QuantumRegister(5, "physical"), ClassicalRegister(2, "z"), ClassicalRegister(1, "a"))
    circuit.x(4)
    circuit.measure(4, 0)
    circuit.measure(0, 2)
    stream = io.BytesIO()
    qpy.dump(circuit, stream, version=17)
    encoded = stream.getvalue()
    job = backend.device.submit_job([encoded, encoded], ProgramFormat.QPY, num_shots=7)
    assert job.wait(10)
    assert job.get_shots(0) == ["001"] * 7
    assert job.get_shots(1) == ["001"] * 7
    assert job.get_program(bytes, 0) == encoded
    retrieved = backend.device.retrieve_job_by_id(job.id)
    assert retrieved.program_format == ProgramFormat.QPY
    assert retrieved.get_program(bytes, 0) == encoded
    assert retrieved.get_shots(1) == ["001"] * 7


def test_overlapping_registers_reject_before_submission(runtime: RuntimeProxy) -> None:
    """Reject QPY register aliases before an unrepresentable result reaches IBM."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(QuantumRegister(5, "physical"), ClassicalRegister(2, "z"), ClassicalRegister(1, "a"))
    circuit.add_register(ClassicalRegister(bits=[circuit.clbits[2], circuit.clbits[0]], name="mix"))
    stream = io.BytesIO()
    qpy.dump(circuit, stream, version=17)
    assert backend.device.try_submit_job(stream.getvalue(), ProgramFormat.QPY, num_shots=7) is None
    assert not runtime.snapshot()["submissions"]


@pytest.mark.parametrize("initial", [0, 1])
@pytest.mark.parametrize("register_condition", [False, True])
@pytest.mark.parametrize("program_format", [ProgramFormat.QPY, ProgramFormat.QASM3])
def test_dynamic_feedforward(
    runtime: RuntimeProxy, initial: int, program_format: ProgramFormat, *, register_condition: bool
) -> None:
    """Native transports preserve conditional bit indices and physical branch sites."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(
        QuantumRegister(5, "physical"), ClassicalRegister(2, "z_flag"), ClassicalRegister(2, "a_out")
    )
    if initial:
        circuit.x(3)
    circuit.measure(0, 0)
    circuit.measure(3, 1)
    operand = circuit.cregs[0] if register_condition else circuit.clbits[1]
    with circuit.if_test((operand, 2 if register_condition else 1)) as otherwise:
        circuit.x(4)
    with otherwise:
        circuit.x(2)
    circuit.measure(4, 2)
    circuit.measure(2, 3)
    expected = "0110" if initial else "1000"
    if program_format == ProgramFormat.QPY:
        job = backend.run(circuit, shots=9, memory=True)
        assert job.result().get_counts() == {f"{expected[:2]} {expected[2:]}": 9}
    else:
        program = qiskit_to_qasm3(circuit, backend.num_qubits)
        native_job = backend.device.submit_job(program, program_format, num_shots=9)
        assert native_job.wait(10)
        assert native_job.get_shots() == [expected] * 9
    source = runtime.snapshot()["submissions"][0]["params"]["pubs"][0][0]
    assert submitted_circuit(source).count_ops()["if_else"] == 1


@pytest.mark.parametrize("invalid", ["nested", "measure", "reset", "loop", "wide", "expression", "sites"])
def test_dynamic_validation_prevents_batch_submission(runtime: RuntimeProxy, invalid: str) -> None:
    """Unsupported control flow or invalid physical placements reject the whole batch."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(5, 33 if invalid == "wide" else 2)
    circuit.measure(3, 0)
    operand = circuit.cregs[0] if invalid == "wide" else circuit.clbits[0]
    if invalid == "expression":
        operand = expr.logic_not(operand)
    if invalid == "loop":
        with circuit.while_loop((circuit.clbits[0], True), body=None, qubits=None, clbits=None, label=None):
            circuit.x(4)
    else:
        condition = operand if invalid == "expression" else (operand, 1)
        with circuit.if_test(condition):
            if invalid == "nested":
                with circuit.if_test((circuit.clbits[1], True)):
                    circuit.x(4)
            elif invalid == "measure":
                circuit.measure(4, 1)
            elif invalid == "reset":
                circuit.reset(4)
            elif invalid == "sites":
                circuit.cx(4, 3)
            else:
                circuit.x(4)
    valid = QuantumCircuit(1, 1)
    valid.measure(0, 0)
    with pytest.raises((CircuitValidationError, UnsupportedOperationError)):
        backend.run([valid, circuit])
    assert not runtime.snapshot()["submissions"]
