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

"""Copy a mid-circuit measurement through conditional feedforward."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from qiskit import QuantumCircuit, transpile

from examples.common import open_backend, parser

if TYPE_CHECKING:
    from qiskit.providers import BackendV2


def run(backend: BackendV2, shots: int) -> dict[str, int]:
    """Execute correlated samples using measurement and a conditional X gate.

    Args:
        backend: An IBM QDMI backend or a local Aer simulator.
        shots: Number of samples.

    Returns:
        Counts containing only 00 and 11 in an ideal simulation.
    """
    circuit = QuantumCircuit(2, 2)
    circuit.h(0)
    circuit.measure(0, 0)
    with circuit.if_test((circuit.clbits[0], True)):
        circuit.x(1)
    circuit.measure(1, 1)
    compiled = transpile(circuit, backend, optimization_level=1, seed_transpiler=7)
    return backend.run(compiled, shots=shots).result().get_counts()


def main() -> None:
    """Run locally by default; IBM access requires an explicit backend choice."""
    arguments = parser(__doc__ or "")
    options = arguments.parse_args()
    if options.backend == "sim":
        from qiskit_aer import AerSimulator  # ruff: ignore[import-outside-top-level]

        backend = AerSimulator()
    else:
        if options.device is None:
            arguments.error("--backend ibm requires --device")
        backend = open_backend(options.backend, options.device)
    print(json.dumps(run(backend, options.shots), sort_keys=True))


if __name__ == "__main__":
    main()
