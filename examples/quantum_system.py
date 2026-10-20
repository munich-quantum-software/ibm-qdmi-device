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

"""Run a Bell circuit on an explicitly configured Quantum System API service."""

from __future__ import annotations

import os

from qiskit import QuantumCircuit, transpile

from ibm.qdmi.qiskit import IBMBackend


def main() -> None:
    """Read connection settings from the environment and execute one circuit."""
    backend = IBMBackend(
        backend_name=os.environ["IBM_QUANTUM_BACKEND"],
        api_key=os.environ["IBM_QUANTUM_API_KEY"],
        instance_crn=os.environ["IBM_QUANTUM_INSTANCE_CRN"],
        base_url=os.environ["IBM_QUANTUM_SYSTEM_URL"],
        auth_url=os.environ["IBM_QUANTUM_AUTH_URL"],
        access_mode="quantum-system",
        storage_config=os.environ["IBM_QUANTUM_STORAGE_CONFIG"],
    )
    circuit = QuantumCircuit(2, 2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    compiled = transpile(circuit, backend, seed_transpiler=7)
    print(backend.run(compiled, shots=64).result().get_counts())


if __name__ == "__main__":
    main()
