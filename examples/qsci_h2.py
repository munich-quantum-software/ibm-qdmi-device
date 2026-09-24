# Copyright (c) 2025 - 2026 IQM Finland Oy
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

"""Optimize and sample H2, then reconstruct its energy with QSCI."""

from __future__ import annotations

import logging
import math
import sys
from typing import TYPE_CHECKING, cast

import numpy as np
from qiskit import transpile
from qiskit_algorithms.minimum_eigensolvers import VQE
from qiskit_algorithms.optimizers import SciPyOptimizer

from examples.common import open_backend, parser, positive_integer

if TYPE_CHECKING:
    from mqt.core.plugins.qiskit.backend import QDMIBackend
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import SparsePauliOp

log = logging.getLogger(__name__)
ATOM = "H 0 0 0; H 0 0 1"
BASIS = "sto-3g"
EXPECTED_ENERGY = -1.101150


def postprocess_counts(observable: SparsePauliOp, counts: dict[str, int], *, cutoff: int = 10) -> float:
    """Diagonalize the H2 Hamiltonian in the most frequently sampled valid states.

    The Jordan-Wigner register contains two alpha and two beta spin orbitals.
    Keep one electron in each spin sector. Integer bitstrings index the original
    logical Hamiltonian in Qiskit's little-endian convention.

    Returns:
        The lowest electronic energy in the selected subspace, in hartrees.

    Raises:
        ValueError: Counts, Hamiltonian width, or cutoff are invalid, or no valid states remain.
    """
    if observable.num_qubits != 4 or cutoff <= 0 or not counts:
        msg = "Use a four-qubit H2 Hamiltonian, nonempty counts, and a positive cutoff."
        raise ValueError(msg)
    if any(len(state) != 4 or set(state) - {"0", "1"} or count <= 0 for state, count in counts.items()):
        msg = "Counts must contain four-bit states and positive frequencies."
        raise ValueError(msg)
    selected = [
        int(state, 2)
        for state in sorted(counts, key=lambda state: (-counts[state], state))
        if state[:2].count("1") == state[2:].count("1") == 1
    ][:cutoff]
    if not selected:
        msg = "No states remain after filtering for one alpha and one beta electron."
        raise ValueError(msg)
    # This H2 example has only 16 basis states; larger molecules need sparse matrix elements.
    hamiltonian = observable.to_matrix()
    reduced = hamiltonian[np.ix_(selected, selected)]
    return float(np.linalg.eigvalsh(reduced)[0])


def optimize_and_sample(
    backend: QDMIBackend,
    ansatz: QuantumCircuit,
    observable: SparsePauliOp,
    *,
    shots: int = 8192,
    maxiter: int = 30,
) -> tuple[float, dict[str, int]]:
    """Run finite-shot VQE and sample the optimized state in logical qubit order.

    Returns:
        The VQE electronic energy and logical measurement counts.

    Raises:
        ValueError: Shots, iteration count, or backend width are invalid.
        RuntimeError: VQE returns no optimal parameters.
    """
    if shots <= 0 or maxiter <= 0 or backend.num_qubits < ansatz.num_qubits:
        msg = "Use positive shots and iterations and a backend wide enough for the ansatz."
        raise ValueError(msg)
    mapped = transpile(ansatz, backend, optimization_level=2, seed_transpiler=7)
    optimizer = SciPyOptimizer(method="L-BFGS-B", options={"maxiter": maxiter, "ftol": 10 * sys.float_info.epsilon})
    estimator = backend.estimator(default_precision=1 / math.sqrt(shots))
    # VQE applies mapped.layout to this logical observable internally.
    vqe = VQE(estimator, mapped, optimizer, initial_point=np.full(mapped.num_parameters, 0.1))
    result = vqe.compute_minimum_eigenvalue(observable)
    if result.optimal_parameters is None or result.eigenvalue is None:
        msg = "VQE returned no optimal parameters."
        raise RuntimeError(msg)
    energy = float(result.eigenvalue.real)
    log.info("VQE electronic energy: %.6f Ha (%s evaluations)", energy, result.optimizer_evals)
    # Add measurements before a fresh mapping to preserve logical bit order after routing.
    measured = ansatz.assign_parameters(result.optimal_parameters)
    measured.measure_all()
    sampled = transpile(measured, backend, optimization_level=2, seed_transpiler=7)
    counts = backend.sampler(default_shots=shots).run([(sampled,)]).result()[0].data["meas"].get_counts()
    log.info("Sampled %d shots: %s", sum(counts.values()), sorted(counts.items()))
    return energy, counts


def run(backend: QDMIBackend, *, shots: int = 8192, maxiter: int = 30, cutoff: int = 10) -> float:
    """Build the H2 electronic problem and run VQE, sampling, and QSCI.

    Returns:
        The QSCI total energy, including nuclear repulsion, in hartrees.

    Raises:
        ValueError: The cutoff is not positive.
    """
    # Keep chemistry optional for --help and portable Windows tests.
    from qiskit_nature.second_q.circuit.library import UCCSD, HartreeFock  # ruff: ignore[import-outside-top-level]
    from qiskit_nature.second_q.drivers import PySCFDriver  # ruff: ignore[import-outside-top-level]
    from qiskit_nature.second_q.mappers import JordanWignerMapper  # ruff: ignore[import-outside-top-level]

    if cutoff <= 0:
        msg = "The cutoff must be positive."
        raise ValueError(msg)
    log.info("Building H2 at 1 angstrom in the %s basis", BASIS)
    problem = PySCFDriver(atom=ATOM, basis=BASIS).run()
    mapper = JordanWignerMapper()
    initial_state = HartreeFock(problem.num_spatial_orbitals, problem.num_particles, mapper)
    ansatz = UCCSD(problem.num_spatial_orbitals, problem.num_particles, mapper, initial_state=initial_state)
    observable = cast("SparsePauliOp", mapper.map(problem.hamiltonian.second_q_op()))
    _, counts = optimize_and_sample(backend, ansatz, observable, shots=shots, maxiter=maxiter)
    electronic_energy = postprocess_counts(observable, counts, cutoff=cutoff)
    total_energy = electronic_energy + (problem.hamiltonian.nuclear_repulsion_energy or 0.0)
    log.info("QSCI total energy: %.6f Ha", total_energy)
    log.info("Absolute difference from %.6f Ha: %.6f Ha", EXPECTED_ENERGY, abs(total_energy - EXPECTED_ENERGY))
    return total_energy


def main() -> None:
    """Run the chemistry showcase with explicit simulator or IBM selection."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    arguments = parser(__doc__ or "")
    arguments.set_defaults(shots=8192)
    arguments.add_argument("--maxiter", type=positive_integer, default=30)
    arguments.add_argument("--cutoff", type=positive_integer, default=10)
    options = arguments.parse_args()
    if options.backend == "ibm" and options.device is None:
        arguments.error("--backend ibm requires --device")
    if sys.platform == "win32":
        arguments.error("QSCI requires PySCF on Linux or macOS; use a supported environment, such as WSL on Windows.")
    backend = open_backend(options.backend, options.device)
    run(backend, shots=options.shots, maxiter=options.maxiter, cutoff=options.cutoff)


if __name__ == "__main__":
    main()
