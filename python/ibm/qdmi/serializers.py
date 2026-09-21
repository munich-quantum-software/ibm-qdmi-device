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

"""Serialize validated circuits with physical and classical indices intact."""

from __future__ import annotations

from qiskit import qasm3
from qiskit.circuit import ClassicalRegister, QuantumCircuit, QuantumRegister

__all__ = ["qiskit_to_qasm3"]


def qiskit_to_qasm3(circuit: QuantumCircuit, num_qubits: int) -> str:
    """Export a circuit for the native IBM OpenQASM interface.

    Args:
        circuit: A bound circuit whose classical registers partition its bits.
        num_qubits: The full physical width of the target backend.

    Returns:
        OpenQASM 3 with stable classical names and all physical qubit indices.
    """
    # IBM imports through Qiskit, which escapes some register names. The shared
    # job adapter keeps the original circuit's names and result headers.
    translated = QuantumCircuit(
        QuantumRegister(num_qubits, "q"),
        *(ClassicalRegister(len(register), f"c{index}") for index, register in enumerate(circuit.cregs)),
    )
    for instruction in circuit.data:
        translated.append(
            instruction.operation,
            [circuit.find_bit(bit).index for bit in instruction.qubits],
            [circuit.find_bit(bit).index for bit in instruction.clbits],
        )
    # Global phase does not affect classified samples.
    return qasm3.dumps(translated)
