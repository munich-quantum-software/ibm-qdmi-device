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

"""Full H2 chemistry validation on supported PySCF platforms."""

from __future__ import annotations

import pytest
from examples import qsci_h2
from mqt.core.plugins.qiskit.backend import QDMIBackend
from qiskit.quantum_info import SparsePauliOp
from qiskit_nature.second_q.drivers import PySCFDriver
from qiskit_nature.second_q.mappers import JordanWignerMapper

# Qiskit Nature still derives HartreeFock/UCCSD from these deprecated base classes.
pytestmark = pytest.mark.filterwarnings(
    r"ignore:The class .*\.(BlueprintCircuit|NLocal).* is deprecated as of Qiskit 2.1:DeprecationWarning"
)


def test_h2_exact_selected_subspace() -> None:
    """Molecular integrals and all valid determinants reproduce the reference energy."""
    problem = PySCFDriver(atom=qsci_h2.ATOM, basis=qsci_h2.BASIS).run()
    observable = JordanWignerMapper().map(problem.hamiltonian.second_q_op())
    assert isinstance(observable, SparsePauliOp)
    electronic = qsci_h2.postprocess_counts(observable, {"0101": 10, "0110": 10, "1001": 10, "1010": 10})
    assert electronic + problem.hamiltonian.nuclear_repulsion_energy == pytest.approx(qsci_h2.EXPECTED_ENERGY, abs=1e-6)


def test_full_h2_workflow() -> None:
    """Run molecular construction, UCCSD VQE, sampling, and QSCI without credentials."""
    backend = QDMIBackend.from_device_id("mqt.ddsim.default")
    energy = qsci_h2.run(backend, shots=1024, maxiter=12, cutoff=4)
    # Finite sampling can retain only the Hartree-Fock determinant.
    assert qsci_h2.EXPECTED_ENERGY - 1e-6 <= energy < -1.0
