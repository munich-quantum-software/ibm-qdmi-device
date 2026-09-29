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

# Test distribution diagnostics without submitting a circuit.
from examples.mqt_bench import _describe_result  # ruff: ignore[import-private-name]
from mqt.core.plugins.qiskit.backend import QDMIBackend
from qiskit import QuantumCircuit, transpile
from qiskit.circuit import Parameter
from qiskit.quantum_info import Operator, SparsePauliOp, hellinger_fidelity
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
        ("graphstate", 10, 2, "at least three"),
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
    observable = SparsePauliOp("ZI")  # The objective depends on theta.
    energy, counts = qsci_h2.optimize_and_sample(backend, ansatz, observable, shots=2048, maxiter=40)
    assert energy < -0.9
    assert sum(counts.values()) == 2048
    assert set(counts) <= {"01", "11"}
    assert counts.get("11", 0) / 2048 > 0.95


@pytest.mark.parametrize("state", ["000", "111"])
def test_ghz_single_shot_fidelity(state: str) -> None:
    """Either ideal GHZ outcome has the same overlap after one shot."""
    assert _describe_result("ghz", {state: 1}, 3, 1) == "GHZ fidelity=0.5000000"


@pytest.mark.parametrize("benchmark", ["qft", "graphstate", "grover"])
def test_sparse_benchmark_fidelity(benchmark: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Observed-support formulas match complete ideal distributions."""
    counts = {"0000": 1, "1000": 2, "1111": 5}
    if benchmark == "grover":
        # Two Grover iterations on eight candidates give success probability 121/128.
        expected = {format(index, "04b"): 1 / 128 for index in range(8, 15)}
        expected["1111"] = 121 / 128
    else:
        expected = {format(index, "04b"): 1 / 16 for index in range(16)}
    fidelity = hellinger_fidelity(counts, expected)
    assert _describe_result(benchmark, counts, 4, 8).endswith(f"fidelity={fidelity:.7f}")

    def bounded_range(*args: int) -> range:
        result = range(*args)
        assert len(result) <= 1024, "Validation enumerated the full basis"
        return result

    # A wide result must not allocate its exponentially large ideal support.
    monkeypatch.setattr(mqt_bench, "range", bounded_range, raising=False)
    assert "fidelity=" in _describe_result(benchmark, {"1" * 40: 8}, 40, 8)


def test_graphstate_cli_rejects_two_qubits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject the invalid graph before opening a backend."""
    monkeypatch.setattr(sys, "argv", ["showcase", "--benchmark", "graphstate", "--num-qubits", "2"])
    monkeypatch.setattr(mqt_bench, "open_backend", lambda *_args: pytest.fail("Backend opened for an invalid graph"))
    with pytest.raises(SystemExit, match="2"):
        mqt_bench.main()


@pytest.mark.parametrize("module", [mqt_bench, qsci_h2])
def test_hardware_requires_device(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing hardware selection fails before opening any backend."""
    monkeypatch.setattr(sys, "argv", ["showcase", "--backend", "ibm"])
    with pytest.raises(SystemExit, match="2"):
        module.main()
