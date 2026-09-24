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

"""Find a successful offline candidate for the exact PR merge commit."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from collections.abc import Iterator


def get_json(path: str) -> dict[str, Any]:
    """Read GitHub Actions metadata without exposing the token.

    Returns:
        The decoded API response.
    """
    request = Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    # The URL always uses the fixed HTTPS GitHub API origin above.
    with urlopen(request, timeout=30) as response:  # ruff: ignore[suspicious-url-open-usage]
        return json.load(response)


def items(path: str, key: str) -> Iterator[dict[str, Any]]:
    """Read every page of an Actions metadata collection.

    Yields:
        Individual collection entries.
    """
    page = 1
    separator = "&" if "?" in path else "?"
    while True:
        entries = get_json(f"{path}{separator}per_page=100&page={page}")[key]
        yield from entries
        if len(entries) < 100:
            return
        page += 1


def find_candidate(event: dict[str, Any], merge_sha: str, run_id: int) -> dict[str, str]:
    """Reuse offline success and its artifact, never another revision's wheel.

    Returns:
        Outputs consumed by the hardware job and final gate.

    Raises:
        RuntimeError: No safe completed candidate is available.
    """
    repository = event["repository"]["full_name"]
    pr = event["pull_request"]
    if (
        event["action"] != "labeled"
        or event["label"]["name"].casefold() != "live-qpu-tests"
        or pr["head"]["repo"]["full_name"] != repository
    ):
        msg = "Only the live-qpu-tests label on a same-repository PR can reuse a candidate."
        raise RuntimeError(msg)

    current = get_json(f"actions/runs/{run_id}")
    head_sha = pr["head"]["sha"]
    runs = items(
        f"actions/workflows/{current['workflow_id']}/runs?event=pull_request&head_sha={head_sha}",
        "workflow_runs",
    )
    for run in runs:
        if (
            run["id"] == run_id
            or run["workflow_id"] != current["workflow_id"]
            or run["event"] != "pull_request"
            or run["head_sha"] != head_sha
            or run["head_repository"]["full_name"] != repository
            or not any(pull["number"] == pr["number"] for pull in run["pull_requests"])
        ):
            continue
        jobs = {job["name"]: job for job in items(f"actions/runs/{run['id']}/jobs?filter=latest", "jobs")}
        candidate = jobs.get("Candidate wheel", {})
        offline = jobs.get("Offline checks", {})
        # Label-only runs deliberately skip both jobs and cannot provide evidence.
        if candidate.get("conclusion") == "skipped" or offline.get("conclusion") == "skipped":
            continue
        if candidate.get("conclusion") != "success" or offline.get("conclusion") != "success":
            msg = "Offline CI has not succeeded. Complete it, then rerun this label workflow."
            raise RuntimeError(msg)

        name = f"hardware-candidate-{merge_sha}-{candidate['run_attempt']}"
        artifacts = [
            artifact
            for artifact in items(f"actions/runs/{run['id']}/artifacts", "artifacts")
            if artifact["name"] == name and not artifact["expired"]
        ]
        if len(artifacts) != 1:
            msg = (
                "No retained candidate matches this merge commit. Run fresh offline CI, then retry this label workflow."
            )
            raise RuntimeError(msg)
        hardware = jobs.get("IBM quantum execution", {}).get("conclusion")
        if hardware not in {"skipped", "success"}:
            msg = "The source CI already requires hardware. Finish or inspect that run; no paid retry was started."
            raise RuntimeError(msg)
        return {
            "run-id": str(run["id"]),
            "artifact-id": str(artifacts[0]["id"]),
            "hardware-needed": "true" if hardware == "skipped" else "false",
        }

    msg = "No offline CI run matches this PR commit. Run offline CI before retrying the label workflow."
    raise RuntimeError(msg)


def main() -> None:
    """Write validated artifact identifiers to the Actions output file."""
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    outputs = find_candidate(event, os.environ["GITHUB_SHA"], int(os.environ["GITHUB_RUN_ID"]))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.writelines(f"{key}={value}\n" for key, value in outputs.items())


if __name__ == "__main__":
    main()
