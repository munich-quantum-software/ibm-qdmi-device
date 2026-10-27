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

"""Check the boundaries around explicitly requested quantum execution."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.ci

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"


def workflow(name: str) -> dict:
    """Load a workflow without interpreting GitHub expressions.

    Returns:
        Parsed workflow data.
    """
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def triggers(config: dict) -> dict:
    """Account for YAML 1.1 treating the `on` key as a boolean.

    Returns:
        Workflow triggers.
    """
    return config.get("on", config.get(True))


def test_hardware_requires_an_explicit_fresh_request() -> None:
    """Ordinary updates cannot trigger QPU jobs or reuse an earlier CI run."""
    ci = workflow("ci.yml")
    label = workflow("label.yml")
    assert set(triggers(ci)["pull_request"]["types"]) == {"opened", "reopened", "synchronize", "ready_for_review"}
    assert triggers(label) == {"pull_request": {"types": ["labeled"]}}
    assert triggers(ci)["workflow_dispatch"]["inputs"]["run_hardware"]["default"] is False
    assert triggers(ci)["workflow_call"]["inputs"]["run_hardware"]["default"] is False
    caller = label["jobs"]["hardware-request"]
    assert "github.event.label.name == 'live-qpu-tests'" in caller["if"]
    assert "github.event.pull_request.head.repo.full_name == github.repository" in caller["if"]
    assert caller["uses"] == "$/.github/workflows/ci.yml"
    assert caller["with"] == {"run_hardware": True}
    assert set(caller["secrets"]) == {"IBM_QUANTUM_API_KEY", "IBM_QUANTUM_INSTANCE_CRN"}
    assert caller["permissions"] == {
        "contents": "read",
        "actions": "read",
        "id-token": "write",
        "pull-requests": "write",
    }
    check_name = label["jobs"]["required-checks-pass"]["name"]
    assert "github.event.label.name == 'live-qpu-tests'" in check_name
    assert "github.event.pull_request.head.repo.full_name == github.repository" in check_name
    assert "&& '🚦 Check' || 'Ignored label'" in check_name
    assert label["jobs"]["required-checks-pass"]["needs"] == "hardware-request"

    jobs = ci["jobs"]
    request = jobs["hardware-request"]
    assert request["if"] == "inputs.run_hardware"
    guard = request["steps"][0]["run"]
    assert '"$ATTEMPT" != 1' in guard
    assert '"$EVENT" == workflow_dispatch && "$REF" == refs/heads/main' in guard
    assert '"$EVENT" == pull_request && "$ACTION" == labeled' in guard
    assert '"$HEAD_REPO" == "$REPOSITORY"' in guard
    assert jobs["candidate-wheel"]["needs"] == "hardware-request"
    assert jobs["candidate-wheel"]["if"] == "needs.hardware-request.result == 'success'"
    assert {"hardware-request", "candidate-wheel"} <= set(jobs["offline-checks-pass"]["needs"])
    assert set(jobs["hardware"]["needs"]) == {"offline-checks-pass", "candidate-wheel"}
    assert "inputs.run_hardware" in jobs["hardware"]["if"]
    assert "needs.offline-checks-pass.result == 'success'" in jobs["hardware"]["if"]
    assert "needs.candidate-wheel.result == 'success'" in jobs["hardware"]["if"]
    assert "!inputs.run_hardware && 'hardware'" in jobs["required-checks-pass"]["steps"][0]["with"]["allowed-skips"]


@pytest.mark.parametrize(
    ("event", "action", "label", "head_repo", "ref", "attempt", "allowed"),
    [
        ("workflow_dispatch", "", "", "", "refs/heads/main", "1", True),
        ("workflow_dispatch", "", "", "", "refs/heads/feature", "1", False),
        ("pull_request", "labeled", "live-qpu-tests", "owner/device", "refs/pull/13/merge", "1", True),
        ("pull_request", "labeled", "live-qpu-tests", "fork/device", "refs/pull/13/merge", "1", False),
        ("pull_request", "synchronize", "live-qpu-tests", "owner/device", "refs/pull/13/merge", "1", False),
        ("workflow_dispatch", "", "", "", "refs/heads/main", "2", False),
    ],
)
def test_request_guard(
    event: str, action: str, label: str, head_repo: str, ref: str, attempt: str, *, allowed: bool
) -> None:
    """Execute the real request guard against allowed and rejected events."""
    guard = workflow("ci.yml")["jobs"]["hardware-request"]["steps"][0]["run"]
    env = {
        **os.environ,
        "EVENT": event,
        "ACTION": action,
        "LABEL": label,
        "HEAD_REPO": head_repo,
        "REPOSITORY": "owner/device",
        "REF": ref,
        "ATTEMPT": attempt,
    }
    bash = shutil.which("bash")
    assert bash is not None
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed workflow script
        [bash, "-e", "-c", guard], env=env, capture_output=True, check=False
    )
    assert (result.returncode == 0) == allowed


def test_only_the_live_step_receives_credentials_and_the_tested_wheel() -> None:
    """The offline candidate is installed before credential-backed execution."""
    ci = workflow("ci.yml")
    hardware = workflow("hardware.yml")
    jobs = ci["jobs"]
    steps = hardware["jobs"]["hardware"]["steps"]
    assert hardware["jobs"]["hardware"]["environment"] == "ibm-quantum"
    assert hardware["jobs"]["hardware"]["concurrency"]["cancel-in-progress"] is False
    assert steps[-1]["env"] == {
        "IBM_QUANTUM_API_KEY": "${{ secrets.IBM_QUANTUM_API_KEY }}",
        "IBM_QUANTUM_INSTANCE_CRN": "${{ secrets.IBM_QUANTUM_INSTANCE_CRN }}",
    }
    assert "--run-quantum --ibm-backend both -n 0" in steps[-1]["run"]
    assert "build/hardware/dist/*.whl" in steps[-2]["run"]
    assert "secrets." not in json.dumps(steps[:-1])
    assert "secrets." not in json.dumps(jobs["candidate-wheel"])
    assert jobs["hardware"]["with"] == {
        "artifact-id": "${{ needs.candidate-wheel.outputs.artifact-id }}",
        "run-id": "${{ github.run_id }}",
    }
    download = next(step["with"] for step in steps if "actions/download-artifact@" in step.get("uses", ""))
    assert download["artifact-ids"] == "${{ inputs.artifact-id }}"
    assert download["run-id"] == "${{ inputs.run-id }}"
