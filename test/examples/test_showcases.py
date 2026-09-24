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

"""Offline regressions for the complete showcase runners."""

from __future__ import annotations

import sys
from functools import partial
from typing import TYPE_CHECKING

import numpy as np
import pytest
from examples import mqt_bench, qsci_h2
from mqt.core.plugins.qiskit.backend import QDMIBackend
from qiskit import QuantumCircuit, transpile
from qiskit.circuit import Parameter
from qiskit.quantum_info import Operator, SparsePauliOp
from qiskit.transpiler import Target

if TYPE_CHECKING:
    from types import ModuleType


@pytest.mark.parametrize("benchmark", mqt_bench.BENCHMARKS)
def test_all_benchmarks(benchmark: str) -> None:
    """Every benchmark uses its actual mapped circuit and measurement register."""
    backend = QDMIBackend.from_device_id("mqt.ddsim.default")
    config = mqt_bench.BENCHMARKS[benchmark]
    counts = mqt_bench.run(backend, benchmark, shots=128, num_qubits=config.default_qubits)
    assert sum(counts.values()) == 128
    assert all(set(state) <= {"0", "1"} for state in counts)
    if benchmark == "ghz":
        assert set(counts) <= {"000", "111"}
    elif benchmark == "dj":
        assert set(counts) == {"111"}
    elif benchmark == "wstate":
        assert all(state.count("1") == 1 for state in counts)
    elif benchmark == "qpe":
        assert len(counts) == 1


@pytest.mark.parametrize(
    ("benchmark", "shots", "num_qubits", "message"),
    [
        ("missing", 10, 3, "Unknown benchmark"),
        ("ghz", 0, 3, "positive shots"),
        ("ghz", 10, 1, "at least two"),
        ("ghz", 10, -1, "Backend exposes"),
    ],
)
def test_benchmark_rejects_invalid_options(benchmark: str, shots: int, num_qubits: int, message: str) -> None:
    """Reject unsupported benchmark inputs before submission."""
    backend = QDMIBackend.from_device_id("mqt.ddsim.default")
    if num_qubits == -1:
        num_qubits = backend.num_qubits + 1
    with pytest.raises(ValueError, match=message):
        mqt_bench.run(backend, benchmark, shots=shots, num_qubits=num_qubits)


def test_qsci_reduced_hamiltonian() -> None:
    """Filter spin sectors and diagonalize the sampled logical subspace."""
    matrix = np.diag(np.arange(16, dtype=float))
    matrix[5, 5], matrix[10, 10] = -1, -2
    matrix[5, 10] = matrix[10, 5] = 0.3
    matrix[3, 3] = -100  # Two beta electrons must never enter the selected sector.
    observable = SparsePauliOp.from_operator(Operator(matrix))
    counts = {"0011": 100, "1010": 20, "0101": 10, "0110": 2}
    expected = np.linalg.eigvalsh(matrix[np.ix_([10, 5], [10, 5])])[0]
    assert qsci_h2.postprocess_counts(observable, counts, cutoff=2) == pytest.approx(expected)
    assert qsci_h2.postprocess_counts(observable, counts, cutoff=1) == pytest.approx(-2)


@pytest.mark.parametrize("counts", [{}, {"0011": 3}, {"01": 2}, {"xxxx": 1}, {"0101": 0}])
def test_qsci_rejects_invalid_counts(counts: dict[str, int]) -> None:
    """Invalid or empty occupancy selections cannot produce an energy."""
    with pytest.raises(ValueError, match=r"nonempty counts|No states remain|four-bit states"):
        qsci_h2.postprocess_counts(SparsePauliOp("IIII"), counts)


def test_qsci_vqe_and_sampling(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real estimator optimizes parameters and the sampler returns logical bits."""
    backend = QDMIBackend.from_device_id("mqt.ddsim.default")
    # Bound layout expansion on the simulator, which advertises 65535 qubits.
    target = Target.from_configuration(num_qubits=4, basis_gates=["rz", "sx", "x", "cx", "measure"])
    monkeypatch.setattr(qsci_h2, "transpile", partial(transpile, target=target, initial_layout=[3, 0]))
    ansatz = QuantumCircuit(2)
    ansatz.x(0)
    ansatz.ry(Parameter("theta"), 1)
    observable = SparsePauliOp("IZ")  # spellchecker:disable-line
    energy, counts = qsci_h2.optimize_and_sample(backend, ansatz, observable, shots=64, maxiter=1)
    assert energy == pytest.approx(-1)
    assert sum(counts.values()) == 64
    assert set(counts) <= {"01", "11"}


@pytest.mark.parametrize("module", [mqt_bench, qsci_h2])
def test_hardware_requires_device(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing hardware selection fails before opening any backend."""
    monkeypatch.setattr(sys, "argv", ["showcase", "--backend", "ibm"])
    with pytest.raises(SystemExit, match="2"):
        module.main()
