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

"""One bounded hardware job and fresh-session retrieval through public APIs."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from mqt.core.qdmi import Job, ProgramFormat
from qiskit import QuantumCircuit, transpile

from ibm.qdmi.serializers import qiskit_to_qasm3

if TYPE_CHECKING:
    from collections.abc import Callable

    from ibm.qdmi.qiskit import IBMBackend


def valid_results(memory: object, counts: object, program_index: int) -> bool:
    """Check the fixed shot budget, bit ordering, histogram, and noisy Bell pair.

    Returns:
        Whether the results satisfy the hardware acceptance contract.
    """
    if not isinstance(memory, list) or len(memory) != 64 or not isinstance(counts, dict):
        return False
    if any(not isinstance(shot, str) or len(shot) != 3 or set(shot) - {"0", "1"} for shot in memory):
        return False
    if any(type(count) is not int or count <= 0 for count in counts.values()) or Counter(memory) != counts:
        return False
    outcomes = ("100", "111") if program_index == 0 else ("000", "011")
    return (
        sum(counts.get(outcome, 0) for outcome in outcomes) >= 48
        and min(counts.get(outcome, 0) for outcome in outcomes) >= 7
    )


def validate_execution(open_backend: Callable[[], IBMBackend], *, timeout: int = 3600) -> str | None:
    """Submit once, wait with a deadline, and retrieve through a fresh session.

    Args:
        open_backend: Open a new session for the selected backend on each call.
        timeout: Maximum seconds spent waiting after submission.

    Returns:
        A fixed diagnostic category on failure, or None on success. Job IDs and
        native exception text never leave this function. Failure triggers one
        cancellation attempt for an active job before releasing it.
    """
    backend = fresh = job = retrieved = None
    category = "configuration"
    failure = None
    success = False
    try:  # ruff: ignore[too-many-statements-in-try-clause] -- one boundary redacts the entire paid lifecycle
        backend = open_backend()
        category = "transpilation"
        circuits = []
        for program_index in range(2):
            circuit = QuantumCircuit(3, 3)
            circuit.h(0)
            circuit.cx(0, 1)
            if program_index == 0:
                circuit.x(2)
            circuit.measure(range(3), range(3))
            circuits.append(circuit)
        # Level 2 searches calibrated layouts even when the trivial layout fits.
        compiled = transpile(circuits, backend, optimization_level=2, seed_transpiler=7, num_processes=1)
        programs = [qiskit_to_qasm3(circuit, backend.num_qubits) for circuit in compiled]
        category = "submission"
        # One explicit QDMI job prevents adapter fallback into separate paid jobs.
        job = backend.device.submit_job(programs, ProgramFormat.QASM3, 64)
        category = "waiting"
        if not job.wait(timeout):
            failure = "timeout"
        elif job.check() != Job.Status.DONE:
            failure = "remote state"
        else:
            category = "results"
            results = [(job.get_shots(index), job.get_counts(index)) for index in range(2)]
            if not all(valid_results(memory, counts, index) for index, (memory, counts) in enumerate(results)):
                failure = "result contract"
            else:
                category = "fresh retrieval"
                fresh = open_backend()
                retrieved = fresh.device.retrieve_job_by_id(job.id)
                if retrieved.num_programs != 2 or any(
                    retrieved.get_shots(index) != memory or retrieved.get_counts(index) != counts
                    for index, (memory, counts) in enumerate(results)
                ):
                    failure = "retrieval mismatch"
                else:
                    success = True
    except Exception:  # ruff: ignore[blind-except] -- report only the fixed stage, never native exception values
        failure = category
    finally:
        if job is not None and not success:
            try:
                job.cancel()
            except Exception:  # ruff: ignore[blind-except] -- cancellation can race with completion
                try:
                    terminal = job.check() in {Job.Status.DONE, Job.Status.FAILED, Job.Status.CANCELED}
                except Exception:  # ruff: ignore[blind-except] -- a failed status lookup leaves cancellation unconfirmed
                    terminal = False
                if not terminal:
                    failure = f"{failure or category}; cancellation failed"
        # Release job handles before their sessions; local cleanup never cancels.
        retrieved = job = None
        fresh = backend = None
    return failure
