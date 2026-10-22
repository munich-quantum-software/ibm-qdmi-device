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
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mqt.core.plugins.qiskit.exceptions import CircuitValidationError, UnsupportedOperationError
from mqt.core.qdmi import ProgramFormat
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, qpy
from qiskit.circuit.classical import expr
from qiskit_service import open_backend, submitted_circuit

if TYPE_CHECKING:
    from qiskit_service import RuntimeProxy


def test_reference_service_does_not_load_core() -> None:
    """Keep native Core/LLVM libraries out of the isolated reference simulator."""
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import qiskit_service; assert 'mqt.core.qdmi' not in sys.modules",
        ],
        cwd=Path(__file__).parent,
        check=True,
        capture_output=True,
    )


def test_qpy_serialization(runtime: RuntimeProxy, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pad a copy and use Core's QPY serializer, retaining conditions and Sampler routing."""
    from mqt.core.plugins.qiskit import backend as core_backend  # ruff: ignore[import-outside-top-level]

    circuit = QuantumCircuit(2, 2)
    circuit.measure(0, 0)
    with circuit.if_test((circuit.clbits[0], True)):
        circuit.x(1)
    circuit.measure(1, 1)
    backend = open_backend(runtime)
    original = core_backend.program_serializer
    observed: list[QuantumCircuit] = []

    def serialize(prepared: QuantumCircuit, target: object) -> bytes:
        assert target is backend
        observed.append(prepared)
        serializer = original(ProgramFormat.QPY)
        assert serializer is not None
        encoded = serializer(prepared, backend)
        assert isinstance(encoded, bytes)
        return encoded

    def custom_serializer(_circuit: QuantumCircuit, _backend: object) -> str:
        return "custom device program"

    monkeypatch.setattr(
        core_backend,
        "program_serializer",
        lambda fmt: {ProgramFormat.QPY: serialize, ProgramFormat.CUSTOM1: custom_serializer}.get(fmt, original(fmt)),
    )
    encoded, program_format = backend._serialize_circuit(  # ruff: ignore[private-member-access]
        circuit, [ProgramFormat.QASM3, ProgramFormat.QPY, ProgramFormat.CUSTOM1]
    )
    assert program_format == ProgramFormat.QPY
    assert circuit.num_qubits == 2
    assert len(observed) == 1
    assert observed[0] is not circuit
    assert observed[0].num_qubits == 5
    assert isinstance(encoded, bytes)
    (decoded,) = qpy.load(io.BytesIO(encoded))
    assert decoded.num_qubits == 5
    assert decoded.num_clbits == 2
    assert decoded.count_ops()["if_else"] == 1
    assert decoded.data[1].operation.condition[0] == decoded.clbits[0]
    assert decoded.data[1].qubits == (decoded.qubits[1],)


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


@pytest.mark.parametrize("version", range(13, 18))
def test_native_binary_batch_and_retrieval(runtime: RuntimeProxy, version: int) -> None:
    """Every supported QPY version survives the public device and remote retrieval."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(QuantumRegister(5, "physical"), ClassicalRegister(2, "z"), ClassicalRegister(1, "a"))
    circuit.x(4)
    circuit.measure(4, 0)
    circuit.measure(0, 2)
    stream = io.BytesIO()
    qpy.dump(circuit, stream, version=version)
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


@pytest.mark.parametrize("initial", [0, 1])
@pytest.mark.parametrize("register_condition", [False, True])
def test_dynamic_feedforward(runtime: RuntimeProxy, initial: int, *, register_condition: bool) -> None:
    """Both condition outcomes and both branches execute after QPY transport."""
    # Aer runs in the spawned service; do not load its OpenMP runtime into pytest.
    if find_spec("qiskit_aer") is None:
        pytest.skip("Qiskit Aer is not installed.")
    backend = open_backend(runtime)
    circuit = QuantumCircuit(5, 3)
    if initial:
        circuit.x(3)
    circuit.measure(3, 0)
    operand = circuit.cregs[0] if register_condition else circuit.clbits[0]
    with circuit.if_test((operand, 1)) as otherwise:
        circuit.x(4)
    with otherwise:
        circuit.x(2)
    circuit.measure(4, 1)
    circuit.measure(2, 2)
    job = backend.run(circuit, shots=9, memory=True)
    assert job.result().get_counts() == {"011" if initial else "100": 9}
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


def test_qasm_fallback_remains_available(runtime: RuntimeProxy) -> None:
    """Static clients can still serialize for a device advertising only OpenQASM."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(2, 2)
    circuit.x(1)
    circuit.measure([0, 1], [0, 1])
    program, program_format = backend._serialize_circuit(circuit, iter([ProgramFormat.QASM3]))  # ruff: ignore[private-member-access]
    assert program_format == ProgramFormat.QASM3
    assert isinstance(program, str)
    assert submitted_circuit(program).num_qubits == 5
