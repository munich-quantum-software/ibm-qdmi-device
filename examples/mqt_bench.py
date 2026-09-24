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

"""Generate, map, sample, and validate seven MQT Bench workloads through QDMI."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from mqt.bench import BenchmarkLevel, get_benchmark
from qiskit.quantum_info import hellinger_fidelity

from examples.common import open_backend, parser, positive_integer

if TYPE_CHECKING:
    from mqt.core.plugins.qiskit.backend import QDMIBackend

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BenchmarkConfig:
    """Configuration for one benchmark family."""

    benchmark: str
    title: str
    default_shots: int
    default_qubits: int
    result_register: str
    description: str


BENCHMARKS: dict[str, BenchmarkConfig] = {
    "ghz": BenchmarkConfig(
        benchmark="ghz",
        title="GHZ",
        default_shots=1024,
        default_qubits=3,
        result_register="meas",
        description="GHZ state preparation for multi-qubit entanglement checks.",
    ),
    "dj": BenchmarkConfig(
        benchmark="dj",
        title="Deutsch-Jozsa",
        default_shots=1024,
        default_qubits=4,
        result_register="c",
        description="Deutsch-Jozsa oracle sampling.",
    ),
    "qft": BenchmarkConfig(
        benchmark="qft",
        title="QFT",
        default_shots=1024,
        default_qubits=3,
        result_register="meas",
        description="Quantum Fourier Transform sampling.",
    ),
    "graphstate": BenchmarkConfig(
        benchmark="graphstate",
        title="Graph State",
        default_shots=1024,
        default_qubits=4,
        result_register="meas",
        description="Graph-state preparation and sampling.",
    ),
    "wstate": BenchmarkConfig(
        benchmark="wstate",
        title="W State",
        default_shots=1024,
        default_qubits=3,
        result_register="meas",
        description="W-state sampling.",
    ),
    "grover": BenchmarkConfig(
        benchmark="grover",
        title="Grover",
        default_shots=8192,
        default_qubits=7,
        result_register="meas",
        description="Grover search sampling.",
    ),
    "qpe": BenchmarkConfig(
        benchmark="qpeexact",
        title="Quantum Phase Estimation",
        default_shots=8192,
        default_qubits=5,
        result_register="c",
        description="Quantum Phase Estimation sampling.",
    ),
}


def _describe_result(key: str, counts: dict[str, int], num_qubits: int, shots: int) -> str:
    """Summarize the observed result distribution for the selected benchmark.

    Returns:
        A short human-readable summary for the selected benchmark family.
    """
    if key == "ghz":
        expected = {"0" * num_qubits: shots // 2, "1" * num_qubits: shots - shots // 2}
        return f"GHZ fidelity={hellinger_fidelity(counts, expected):.7f}"
    if key == "dj":
        expected = {"1" * (num_qubits - 1): shots}
        return f"Deutsch-Jozsa fidelity={hellinger_fidelity(counts, expected):.7f}"
    if key == "qft":
        expected = {format(i, f"0{num_qubits}b"): shots / (2**num_qubits) for i in range(2**num_qubits)}
        return f"QFT fidelity={hellinger_fidelity(counts, expected):.7f}"
    if key == "graphstate":
        expected = {format(i, f"0{num_qubits}b"): shots / (2**num_qubits) for i in range(2**num_qubits)}
        return f"Graph-state fidelity={hellinger_fidelity(counts, expected):.7f}"
    if key == "wstate":
        expected = {
            f"{1 << (num_qubits - index - 1):0{num_qubits}b}": shots / num_qubits for index in range(num_qubits)
        }
        return f"W-state fidelity={hellinger_fidelity(counts, expected):.7f}"
    if key == "grover":
        actual_qubits = num_qubits - 1
        r = int(np.pi / 4 * np.sqrt(2**actual_qubits))
        theta = 2 * np.arcsin(1 / np.sqrt(2**actual_qubits))
        success_prob = float(np.sin((r + 0.5) * theta) ** 2)
        expected: dict[str, float] = {"1" * num_qubits: success_prob * shots}
        if success_prob < 1:
            remaining_prob = 1 - success_prob
            remaining_prob_per_bitstring = remaining_prob * shots / (2**actual_qubits - 1)
            for index in range(2**actual_qubits):
                bitstring = format(index, f"0{actual_qubits}b")
                if bitstring != "1" * actual_qubits:
                    expected["1" + bitstring] = remaining_prob_per_bitstring
        return f"Grover fidelity={hellinger_fidelity(counts, expected):.7f}"
    ideal_bitstring = max(counts, key=counts.__getitem__)
    expected = {ideal_bitstring: sum(counts.values())}
    return f"QPE modal outcome={ideal_bitstring}, concentration={hellinger_fidelity(counts, expected):.7f}"


def run(backend: QDMIBackend, benchmark: str = "ghz", *, shots: int = 1024, num_qubits: int = 3) -> dict[str, int]:
    """Map and sample a benchmark on the selected target.

    Returns:
        Counts in the benchmark's logical classical register.

    Raises:
        ValueError: The benchmark, shot count, or problem size is invalid.
    """
    if benchmark not in BENCHMARKS:
        msg = f"Unknown benchmark: {benchmark}"
        raise ValueError(msg)
    if shots <= 0 or num_qubits < 2:
        msg = "Use positive shots and at least two qubits."
        raise ValueError(msg)
    if backend.num_qubits < num_qubits:
        msg = f"Backend exposes {backend.num_qubits} qubits; requested {num_qubits}."
        raise ValueError(msg)
    config = BENCHMARKS[benchmark]
    circuit = get_benchmark(
        benchmark=config.benchmark,
        level=BenchmarkLevel.MAPPED,
        circuit_size=num_qubits,
        target=backend.target,
    )
    log.info(
        "%s circuit: %d qubits, %d gates, depth %d", config.title, circuit.num_qubits, circuit.size(), circuit.depth()
    )
    result = backend.sampler(default_shots=shots).run([(circuit,)]).result()
    counts: dict[str, int] = result[0].data[config.result_register].get_counts()
    log.info("Collected %d shots: %s", sum(counts.values()), sorted(counts.items()))
    log.info("Validation: %s", _describe_result(benchmark, counts, num_qubits, shots))
    return counts


def main() -> None:
    """Run one of the MQT Bench showcase circuits."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    arguments = parser(__doc__ or "")
    arguments.set_defaults(shots=None)
    arguments.add_argument("--benchmark", choices=tuple(BENCHMARKS), default="ghz")
    arguments.add_argument("--num-qubits", type=positive_integer)
    options = arguments.parse_args()
    if options.backend == "ibm" and options.device is None:
        arguments.error("--backend ibm requires --device")
    config = BENCHMARKS[options.benchmark]
    num_qubits = options.num_qubits if options.num_qubits is not None else config.default_qubits
    if num_qubits < 2:
        arguments.error("--num-qubits must be at least two")
    backend = open_backend(options.backend, options.device)
    run(
        backend,
        options.benchmark,
        shots=options.shots if options.shots is not None else config.default_shots,
        num_qubits=num_qubits,
    )


if __name__ == "__main__":
    main()
