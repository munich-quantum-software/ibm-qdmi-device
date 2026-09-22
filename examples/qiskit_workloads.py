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

"""Run sampling, benchmarking, or an H2 energy estimate through QDMI."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

from mqt.bench import BenchmarkLevel, get_benchmark
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import SparsePauliOp

from examples.common import open_backend, parser

if TYPE_CHECKING:
    from mqt.core.plugins.qiskit.backend import QDMIBackend


def sample_bell(backend: QDMIBackend, shots: int) -> dict[str, int]:
    """Sample a Bell pair using the shared sampler primitive.

    Returns:
        Counts for the two measured logical qubits.
    """
    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure_all()
    mapped = transpile(circuit, backend, optimization_level=1, seed_transpiler=7)
    result = backend.sampler(default_shots=shots).run([(mapped,)]).result()
    return result[0].data["meas"].get_counts()


def estimate_h2(backend: QDMIBackend, shots: int, angle: float = -0.22) -> float:
    """Estimate one H2 trial-state energy with finite shots.

    The two-qubit Hamiltonian is the model in IBM Quantum Learning's
    variational-algorithm examples. No chemistry package or geometry calculation
    is needed; this is one energy evaluation, not a converged VQE calculation.

    Returns:
        The energy estimate in hartrees.
    """
    hamiltonian = SparsePauliOp.from_list([
        ("II", -1.052373245772859),
        ("IZ", 0.39793742484318045),  # spellchecker:disable-line
        ("ZI", -0.39793742484318045),
        ("ZZ", -0.01128010425623538),
        ("XX", 0.18093119978423156),
    ])
    circuit = QuantumCircuit(2)
    circuit.x(0)
    circuit.ry(angle, 1)
    circuit.cx(1, 0)
    mapped = transpile(circuit, backend, optimization_level=1, seed_transpiler=7)
    observable = hamiltonian.apply_layout(mapped.layout)
    result = backend.estimator().run([(mapped, observable)], precision=1 / math.sqrt(shots)).result()
    return float(result[0].data["evs"])


def benchmark(backend: QDMIBackend, shots: int) -> dict[str, int]:
    """Map and sample a three-qubit MQT Bench GHZ circuit.

    Returns:
        Counts for the benchmark's measured register.
    """
    circuit = get_benchmark("ghz", level=BenchmarkLevel.MAPPED, circuit_size=3, target=backend.target)
    result = backend.sampler(default_shots=shots).run([(circuit,)]).result()
    return result[0].data[circuit.cregs[0].name].get_counts()


def main() -> None:
    """Run one finite-shot workload."""
    arguments = parser(__doc__ or "")
    arguments.add_argument("--workload", choices=("bell", "benchmark", "h2"), default="bell")
    options = arguments.parse_args()
    if options.backend == "ibm" and options.device is None:
        arguments.error("--backend ibm requires --device")
    backend = open_backend(options.backend, options.device)
    if options.workload == "h2":
        result = {"energy_hartree": estimate_h2(backend, options.shots)}
    elif options.workload == "benchmark":
        result = benchmark(backend, options.shots)
    else:
        result = sample_bell(backend, options.shots)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
