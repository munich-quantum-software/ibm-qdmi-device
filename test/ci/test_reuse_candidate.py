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

"""Check artifact provenance and fail-closed reuse with synthetic API data."""

from __future__ import annotations

import copy
from typing import Any

import pytest
import reuse_candidate

pytestmark = pytest.mark.ci


@pytest.fixture
def metadata(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Any], dict[str, Any]]:
    """Provide one completed run for the labeled PR and its tested merge commit.

    Returns:
        The label event and mutable API response data.
    """
    event = {
        "action": "labeled",
        "label": {"name": "live-qpu-tests"},
        "repository": {"full_name": "owner/device"},
        "pull_request": {"number": 31, "head": {"sha": "head", "repo": {"full_name": "owner/device"}}},
    }
    data = {
        "runs": [
            {
                "id": 10,
                "workflow_id": 7,
                "event": "pull_request",
                "head_sha": "head",
                "head_repository": {"full_name": "owner/device"},
                "pull_requests": [{"number": 31}],
            }
        ],
        "jobs": [
            {"name": "Candidate wheel", "conclusion": "success", "run_attempt": 1},
            {"name": "Offline checks", "conclusion": "success", "run_attempt": 2},
            {"name": "IBM quantum execution", "conclusion": "skipped", "run_attempt": 2},
        ],
        "artifacts": [{"id": 20, "name": "hardware-candidate-merge-1", "expired": False}],
    }

    def get_json(path: str) -> dict[str, Any]:
        if path == "actions/runs/11":
            return {"workflow_id": 7}
        if path == "actions/workflows/7/runs?event=pull_request&head_sha=head&per_page=100&page=1":
            return {"workflow_runs": data["runs"]}
        if path == "actions/runs/10/jobs?filter=latest&per_page=100&page=1":
            return {"jobs": data["jobs"]}
        if path == "actions/runs/10/artifacts?per_page=100&page=1":
            return {"artifacts": data["artifacts"]}
        pytest.fail(f"Unexpected API request: {path}")

    monkeypatch.setattr(reuse_candidate, "get_json", get_json)
    return event, data


@pytest.mark.parametrize("hardware", ["skipped", "success"])
def test_reuses_exact_candidate(metadata: tuple[dict[str, Any], dict[str, Any]], hardware: str) -> None:
    """Partial reruns use the successful candidate's attempt; paid success is reused."""
    event, data = metadata
    data["jobs"][2]["conclusion"] = hardware
    assert reuse_candidate.find_candidate(event, "merge", 11) == {
        "run-id": "10",
        "artifact-id": "20",
        "hardware-needed": "true" if hardware == "skipped" else "false",
    }


@pytest.mark.parametrize("job", [0, 1, 2])
@pytest.mark.parametrize("result", [None, "failure", "cancelled"])
def test_rejects_unfinished_or_failed_jobs(
    metadata: tuple[dict[str, Any], dict[str, Any]], job: int, result: str | None
) -> None:
    """Failed or unfinished work cannot authorize new paid execution."""
    event, data = metadata
    data["jobs"][job]["conclusion"] = result
    with pytest.raises(RuntimeError):
        reuse_candidate.find_candidate(event, "merge", 11)


@pytest.mark.parametrize("change", ["expired", "merge", "attempt", "missing", "duplicate"])
def test_rejects_wrong_artifact(metadata: tuple[dict[str, Any], dict[str, Any]], change: str) -> None:
    """A matching head SHA alone does not prove the merge revision was tested."""
    event, data = metadata
    if change == "expired":
        data["artifacts"][0]["expired"] = True
    elif change == "merge":
        data["artifacts"][0]["name"] = "hardware-candidate-other-merge-1"
    elif change == "attempt":
        data["artifacts"][0]["name"] = "hardware-candidate-merge-2"
    elif change == "missing":
        data["artifacts"] = []
    else:
        data["artifacts"] *= 2
    with pytest.raises(RuntimeError, match="No retained candidate"):
        reuse_candidate.find_candidate(event, "merge", 11)


@pytest.mark.parametrize("change", ["fork", "head", "workflow", "event", "pr", "current"])
def test_rejects_other_runs(metadata: tuple[dict[str, Any], dict[str, Any]], change: str) -> None:
    """Only an earlier CI run for this internal PR can provide evidence."""
    event, data = metadata
    run = data["runs"][0]
    if change == "fork":
        run["head_repository"]["full_name"] = "fork/device"
    elif change == "head":
        run["head_sha"] = "old-head"
    elif change == "workflow":
        run["workflow_id"] = 8
    elif change == "event":
        run["event"] = "push"
    elif change == "pr":
        run["pull_requests"] = [{"number": 32}]
    else:
        run["id"] = 11
    with pytest.raises(RuntimeError, match="No offline CI run"):
        reuse_candidate.find_candidate(event, "merge", 11)


@pytest.mark.parametrize("change", ["fork", "label", "action"])
def test_rejects_unrelated_events(metadata: tuple[dict[str, Any], dict[str, Any]], change: str) -> None:
    """The API helper enforces the label and repository boundary too."""
    event, _ = metadata
    if change == "fork":
        event["pull_request"]["head"]["repo"]["full_name"] = "fork/device"
    elif change == "label":
        event["label"]["name"] = "bug"
    else:
        event["action"] = "unlabeled"
    with pytest.raises(RuntimeError, match="Only the live-qpu-tests label"):
        reuse_candidate.find_candidate(event, "merge", 11)


def test_ignores_label_only_runs(
    metadata: tuple[dict[str, Any], dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skipped offline gates cannot recursively validate another label run."""
    event, data = metadata
    label_run = copy.deepcopy(data["runs"][0])
    label_run["id"] = 12
    data["runs"].insert(0, label_run)
    original = reuse_candidate.get_json

    def get_json(path: str) -> dict[str, Any]:
        if path == "actions/runs/12/jobs?filter=latest&per_page=100&page=1":
            return {"jobs": [{"name": "Offline checks", "conclusion": "skipped"}]}
        return original(path)

    monkeypatch.setattr(reuse_candidate, "get_json", get_json)
    assert reuse_candidate.find_candidate(event, "merge", 11)["run-id"] == "10"


def test_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    """A completed candidate may appear beyond the first API page."""
    pages = {
        "runs?per_page=100&page=1": {"workflow_runs": [{"id": number} for number in range(100)]},
        "runs?per_page=100&page=2": {"workflow_runs": [{"id": 100}]},
    }
    monkeypatch.setattr(reuse_candidate, "get_json", pages.__getitem__)
    assert len(list(reuse_candidate.items("runs", "workflow_runs"))) == 101
