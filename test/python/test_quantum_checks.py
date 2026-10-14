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
from offline_service import CRN
from qiskit.utils import should_run_in_parallel
from qiskit_service import remote_runtime
from quantum_checks import result_failure, validate_execution

from ibm.qdmi.qiskit import IBMBackend


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "Queued",
        "Failed",
        "submission",
        "results",
        "status",
        "retrieval",
        "authentication",
        "cancellation",
    ],
)
def test_hardware_contract_offline(
    failure: str | None, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Use actual native jobs to verify the budget, retrieval, and cleanup."""
    monkeypatch.setenv("QISKIT_PARALLEL", "TRUE")
    should_run_in_parallel.cache_clear()
    request.addfinalizer(should_run_in_parallel.cache_clear)
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
            "status": "waiting",
            "retrieval": "retrieval mismatch",
            "authentication": "configuration",
            "cancellation": "timeout; cancellation failed",
        }
        assert outcome == expected[failure]
        state = runtime.snapshot()
        assert len(state["submissions"]) == (0 if failure == "authentication" else 1)
        assert len(opened) == (2 if failure in {None, "retrieval"} else 1)
        assert len(state["cancellations"]) == int(failure in {"Queued", "cancellation", "status"})
        if state["submissions"]:
            request = state["submissions"][0]
            assert request["cost"] == 60
            assert len(request["params"]["pubs"]) == 2
            assert [pub[2] for pub in request["params"]["pubs"]] == [64, 64]
            assert request["params"]["support_qiskit"] is False
            assert request["params"]["options"]["dynamical_decoupling"]["enable"] is False
            assert request["params"]["options"]["twirling"] == {"enable_gates": False, "enable_measure": False}


@pytest.mark.parametrize(
    ("memory", "failure"),
    [
        (["100"] * 32 + ["111"] * 32, None),
        (["100"] * 7 + ["111"] * 41 + ["001"] * 16, None),
        (["100"] * 6 + ["111"] * 58, "Bell balance"),
        (["100"] * 7 + ["111"] * 40 + ["001"] * 17, "Bell population"),
        (["100"] * 64, "Bell balance"),
        (["100"] * 32 + ["111"] * 31, "shot shape"),
        (["1"] * 64, "shot encoding"),
        (["00x"] * 64, "shot encoding"),
        ([100] * 64, "shot encoding"),
    ],
)
def test_noisy_acceptance(memory: list[object], failure: str | None) -> None:
    """Threshold boundaries use the agreed shot count and classical ordering."""
    assert result_failure(memory, dict(Counter(memory)), 0) == failure


def test_result_mismatch() -> None:
    """Reject inconsistent or noninteger histograms even with valid shot memory."""
    memory = ["100"] * 32 + ["111"] * 32
    assert result_failure(memory, {"100": 31, "111": 33}, 0) == "histogram"
    assert result_failure(memory, {"100": 32.0, "111": 32}, 0) == "histogram"
    assert result_failure(memory, [("100", 32), ("111", 32)], 0) == "shot shape"


def test_program_order() -> None:
    """The second circuit's independent qubit distinguishes indexed results."""
    memory = ["000"] * 32 + ["011"] * 32
    counts = dict(Counter(memory))
    assert result_failure(memory, counts, 1) is None
    assert result_failure(memory, counts, 0) == "Bell population"
