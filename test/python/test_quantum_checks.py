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

"""Offline regressions for the bounded hardware validation contract."""

from __future__ import annotations

from collections import Counter

import pytest
from mqt.core.plugins.qiskit.job import QDMIJob
from offline_service import CRN
from qiskit_service import remote_runtime
from quantum_checks import valid_results, validate_execution

from ibm.qdmi.qiskit import IBMBackend


@pytest.mark.parametrize(
    "failure", [None, "Queued", "Failed", "submission", "results", "retrieval", "authentication", "cancellation"]
)
def test_hardware_contract_offline(failure: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use actual native jobs to verify the budget, retrieval, and cleanup."""
    cancellation_attempts = []
    cancel = QDMIJob.cancel

    def record_cancel(job: QDMIJob) -> bool:
        cancellation_attempts.append(True)
        return cancel(job)

    monkeypatch.setattr(QDMIJob, "cancel", record_cancel)
    with remote_runtime() as runtime:
        if failure in {"Queued", "Failed"}:
            runtime.set_state(failure, 0)
        elif failure == "submission":
            runtime.set_state("Completed", 1)
        elif failure is not None:
            runtime.set_failure(failure)
        opened = []

        def open_backend() -> IBMBackend:
            opened.append(True)
            return IBMBackend(
                backend_name="ibm_test",
                api_key="synthetic-key",
                instance_crn=CRN,
                base_url=runtime.snapshot()["url"],
                auth_url=runtime.snapshot()["url"] + "/auth",
            )

        outcome = validate_execution(open_backend, timeout=2)
        expected = {
            None: None,
            "Queued": "timeout",
            "Failed": "remote state",
            "submission": "submission",
            "results": "results",
            "retrieval": "retrieval mismatch",
            "authentication": "configuration",
            "cancellation": "timeout; cancellation failed",
        }
        assert outcome == expected[failure]
        state = runtime.snapshot()
        assert len(state["submissions"]) == (0 if failure == "authentication" else 1)
        assert len(opened) == (2 if failure in {None, "retrieval"} else 1)
        if failure not in {None, "submission", "authentication"}:
            assert cancellation_attempts
            if failure in {"Queued", "cancellation"}:
                assert len(state["cancellations"]) == 1
        else:
            assert not cancellation_attempts
        if state["submissions"]:
            request = state["submissions"][0]
            assert request["cost"] == 60
            assert request["params"]["pubs"][0][2] == 128
            assert request["params"]["support_qiskit"] is False
            assert request["params"]["options"]["dynamical_decoupling"]["enable"] is False
            assert request["params"]["options"]["twirling"] == {"enable_gates": False, "enable_measure": False}


@pytest.mark.parametrize(
    ("memory", "valid"),
    [
        (["100"] * 64 + ["111"] * 64, True),
        (["100"] * 13 + ["111"] * 83 + ["001"] * 32, True),
        (["100"] * 12 + ["111"] * 116, False),
        (["100"] * 13 + ["111"] * 82 + ["001"] * 33, False),
        (["100"] * 128, False),
        (["100"] * 64 + ["111"] * 63, False),
        (["1"] * 128, False),
        (["00x"] * 128, False),
        ([100] * 128, False),
    ],
)
def test_noisy_acceptance(memory: list[object], *, valid: bool) -> None:
    """Threshold boundaries use the agreed shot count and classical ordering."""
    assert valid_results(memory, dict(Counter(memory))) is valid


def test_result_mismatch() -> None:
    """Reject inconsistent or noninteger histograms even with valid shot memory."""
    memory = ["100"] * 64 + ["111"] * 64
    assert not valid_results(memory, {"100": 63, "111": 65})
    assert not valid_results(memory, {"100": 64.0, "111": 64})
    assert not valid_results(memory, [("100", 64), ("111", 64)])
