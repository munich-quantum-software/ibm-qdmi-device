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

import math
import time
from collections import Counter
from typing import TYPE_CHECKING

from mqt.core.qdmi import Job
from qiskit import QuantumCircuit, transpile
from qiskit.providers import JobStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from ibm.qdmi.qiskit import IBMBackend


def valid_results(memory: object, counts: object) -> bool:
    """Check the fixed shot budget, bit ordering, histogram, and noisy Bell pair.

    Returns:
        Whether the results satisfy the hardware acceptance contract.
    """
    if not isinstance(memory, list) or len(memory) != 128 or not isinstance(counts, dict):
        return False
    if any(not isinstance(shot, str) or len(shot) != 3 or set(shot) - {"0", "1"} for shot in memory):
        return False
    if any(type(count) is not int or count <= 0 for count in counts.values()) or Counter(memory) != counts:
        return False
    return counts.get("100", 0) + counts.get("111", 0) >= 96 and min(counts.get("100", 0), counts.get("111", 0)) >= 13


def validate_execution(open_backend: Callable[[], IBMBackend], *, timeout: int = 900) -> str | None:
    """Submit once, wait with a deadline, and retrieve through a fresh session.

    Args:
        open_backend: Open a new session for the selected backend on each call.
        timeout: Maximum seconds spent waiting after submission.

    Returns:
        A fixed diagnostic category on failure, or None on success. Job IDs and
        native exception text never leave this function. Failure triggers one
        cancellation attempt through the original Qiskit job before releasing it.
    """
    backend = fresh = job = control = retrieved = None
    category = "configuration"
    failure = None
    success = False
    try:  # ruff: ignore[too-many-statements-in-try-clause] -- one boundary redacts the entire paid lifecycle
        backend = open_backend()
        category = "transpilation"
        circuit = QuantumCircuit(3, 3)
        circuit.h(0)
        circuit.cx(0, 1)
        circuit.x(2)
        circuit.measure(range(3), range(3))
        compiled = transpile(circuit, backend, optimization_level=1, seed_transpiler=7)
        category = "submission"
        job = backend.run(compiled, shots=128, memory=True)
        deadline = time.monotonic() + timeout
        category = "retrieval"
        identifier = job.job_id()
        control = backend.device.retrieve_job_by_id(identifier)
        category = "waiting"
        state = control.check()
        remaining = math.floor(deadline - time.monotonic())
        if state in {Job.Status.FAILED, Job.Status.CANCELED}:
            failure = "remote state"
        elif remaining <= 0:
            failure = "timeout"
        elif not control.wait(remaining):
            failure = "remote state" if control.check() in {Job.Status.FAILED, Job.Status.CANCELED} else "timeout"
        # Confirm completion on the original handle too. Its cached terminal
        # state prevents the shared result adapter from starting an unlimited wait.
        elif control.check() != Job.Status.DONE or job.status() != JobStatus.DONE:
            failure = "remote state"
        else:
            category = "results"
            result = job.result()
            memory, counts = result.get_memory(), result.get_counts()
            if not valid_results(memory, counts):
                failure = "result contract"
            else:
                category = "fresh retrieval"
                fresh = open_backend()
                retrieved = fresh.device.retrieve_job_by_id(identifier)
                if retrieved.get_shots() != memory or retrieved.get_counts() != counts:
                    failure = "retrieval mismatch"
                else:
                    success = True
    except Exception:  # ruff: ignore[blind-except] -- report only the fixed stage, never native exception values
        failure = category
    finally:
        if job is not None and not success:
            try:
                if not job.cancel() and job.status() not in {JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED}:
                    failure = f"{failure or category}; cancellation failed"
            except Exception:  # ruff: ignore[blind-except] -- cleanup must not reveal or mask the original failure
                failure = f"{failure or category}; cancellation failed"
        # Release job handles before their sessions; local cleanup never cancels.
        retrieved = control = job = None
        fresh = backend = None
    return failure
