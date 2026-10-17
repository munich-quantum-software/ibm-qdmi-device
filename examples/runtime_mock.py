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

"""Run sampling and Executor through native QDMI without an IBM account."""

from __future__ import annotations

from qiskit import QuantumCircuit, transpile
from qiskit_ibm_runtime import QuantumProgram

from ibm.qdmi.qiskit import IBMBackend


def main() -> None:
    """Execute the same Bell circuit through both native program formats."""
    backend = IBMBackend(backend_name="fake_manila")
    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure_all()
    compiled = transpile(circuit, backend, seed_transpiler=7)
    result = backend.run(compiled, shots=128).result()
    counts = result.get_counts()
    assert sum(counts.values()) == 128
    print("Native Sampler:", counts)

    program = QuantumProgram(shots=16)
    program.append_circuit_item(compiled)
    output = backend.executor().run(program).result(timeout=30)
    assert output[0]["meas"].shape == (16, 2)
    print("Native Executor shape:", output[0]["meas"].shape)


if __name__ == "__main__":
    main()
