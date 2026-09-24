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

"""Evaluate the real CI gates over eligible, untrusted, and failing runs."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"


def evaluate(expression: str, context: dict[str, str | list[str]]) -> bool | str | list[str]:
    """Evaluate the workflow's boolean/string subset without executing code.

    Returns:
        The expression value.
    """
    expression = re.sub(r"(?:github|needs)\.[\w.*-]+", lambda match: repr(context[match[0]]), expression)
    expression = expression.replace("&&", " and ").replace("||", " or ")
    expression = re.sub(r"!(?!=)", " not ", expression)

    def visit(node: ast.AST) -> bool | str | list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, (bool, str)):
            return node.value
        if isinstance(node, ast.List):
            values = [visit(value) for value in node.elts]
            assert all(isinstance(value, str) for value in values)
            return [str(value) for value in values]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not visit(node.operand)
        if isinstance(node, ast.BoolOp):
            result = visit(node.values[0])
            for value in node.values[1:]:
                result = (result and visit(value)) if isinstance(node.op, ast.And) else (result or visit(value))
            return result
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right = visit(node.left), visit(node.comparators[0])
            if isinstance(node.ops[0], ast.Eq):
                return left == right
            if isinstance(node.ops[0], ast.NotEq):
                return left != right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "contains" and len(node.args) == 2:
                values, needle = visit(node.args[0]), visit(node.args[1])
                assert isinstance(values, list)
                assert isinstance(needle, str)
                return needle.casefold() in [value.casefold() for value in values]
            if node.func.id == "fromJSON" and len(node.args) == 1:
                argument = visit(node.args[0])
                assert isinstance(argument, str)
                value = json.loads(argument)
                assert isinstance(value, bool)
                return value
            if node.func.id == "always" and not node.args:
                return True
            if node.func.id == "cancelled" and not node.args:
                return context.get("cancelled") == "true"
        msg = "CI gate expression is outside the checked subset"
        raise AssertionError(msg)

    return visit(ast.parse("(" + expression.strip() + ")", mode="eval").body)


def skip_list(expression: str, context: dict[str, str | list[str]]) -> set[str]:
    """Expand the aggregate's conditional skip list.

    Returns:
        Job names the aggregate permits to skip.
    """
    rendered = re.sub(r"\$\{\{(.*?)\}\}", lambda match: str(evaluate(match[1], context)), expression, flags=re.DOTALL)
    return {name.strip() for name in rendered.split(",") if name.strip()}


@pytest.mark.parametrize("event", ["push", "workflow_dispatch", "pull_request", "merge_group"])
@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/heads/feature", "refs/pull/13/merge"])
@pytest.mark.parametrize("result", ["success", "failure", "cancelled", "skipped"])
@pytest.mark.parametrize("gate", ["offline-checks-pass", "candidate-wheel"])
@pytest.mark.parametrize("same_repo", [True, False])
@pytest.mark.parametrize("labels", [[], ["bug"], ["live-qpu-tests"], ["bug", "LIVE-QPU-TESTS"]])
def test_hardware_eligibility(
    event: str, ref: str, result: str, gate: str, labels: list[str], *, same_repo: bool
) -> None:
    """Only main runs and labeled internal PRs can spend after offline success."""
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    context: dict[str, str | list[str]] = {
        "github.ref": ref,
        "github.event_name": event,
        "github.event.action": "synchronize",
        "github.event.label.name": "",
        "github.repository": "owner/device",
        "github.event.pull_request.head.repo.full_name": "owner/device" if same_repo else "fork/device",
        "github.event.pull_request.labels.*.name": labels,
        "needs.offline-checks-pass.result": "success",
        "needs.candidate-wheel.result": "success",
        "needs.reuse-offline.result": "skipped",
        "needs.reuse-offline.outputs.hardware-needed": "",
    }
    context[f"needs.{gate}.result"] = result
    eligible = (ref == "refs/heads/main" and event in {"push", "workflow_dispatch"}) or (
        event == "pull_request" and same_repo and "live-qpu-tests" in [label.casefold() for label in labels]
    )
    assert bool(evaluate(jobs["hardware"]["if"], context)) == (eligible and result == "success")
    final = jobs["required-checks-pass"]
    assert evaluate(final["name"].strip()[3:-2], context) == "🚦 Check"
    assert evaluate(final["if"], context)
    assert set(final["needs"]) == {"offline-checks-pass", "reuse-offline", "hardware"}
    assert skip_list(final["steps"][0]["with"]["allowed-skips"], context) == (
        {"reuse-offline"} if eligible else {"reuse-offline", "hardware"}
    )


def test_main_requires_every_offline_job() -> None:
    """Change detection cannot bypass an Actions prerequisite on main."""
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    gate = jobs["offline-checks-pass"]
    expected = set(jobs) - {"offline-checks-pass", "reuse-offline", "hardware", "required-checks-pass"}
    assert set(gate["needs"]) == expected
    context: dict[str, str | list[str]] = {"github.ref": "refs/heads/main", "github.event.action": ""}
    assert evaluate(gate["if"], context)
    for key in ("run-cpp-tests", "run-cpp-linter", "run-python-linter", "run-python-tests", "run-cd"):
        context[f"needs.change-detection.outputs.{key}"] = "false"
    for name in expected:
        if "if" in jobs[name]:
            assert evaluate(jobs[name]["if"], context)
    assert not skip_list(gate["steps"][0]["with"]["allowed-skips"], context)


def test_credentials_artifact_and_budget_boundary() -> None:
    """Only the last hardware step gets secrets, after installing the candidate."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert workflow["permissions"] == {"contents": "read"}
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"push", "pull_request", "merge_group", "workflow_dispatch"}
    assert set(triggers["pull_request"]["types"]) == {"opened", "reopened", "synchronize", "labeled"}
    jobs = workflow["jobs"]
    hardware = jobs["hardware"]
    assert hardware["environment"] == "ibm-quantum"
    assert hardware["timeout-minutes"] == 130
    assert hardware["concurrency"]["cancel-in-progress"] is False
    assert set(hardware["needs"]) == {"offline-checks-pass", "candidate-wheel", "reuse-offline"}
    steps = hardware["steps"]
    assert steps[0]["with"]["ref"] == "${{ github.sha }}"
    assert steps[-1]["env"] == {
        "IBM_QUANTUM_API_KEY": "${{ secrets.IBM_QUANTUM_API_KEY }}",
        "IBM_QUANTUM_INSTANCE_CRN": "${{ secrets.IBM_QUANTUM_INSTANCE_CRN }}",
    }
    assert "--run-quantum --ibm-backend both -n 0" in steps[-1]["run"]
    assert "build/hardware/dist/*.whl" in steps[-2]["run"]
    upload = jobs["candidate-wheel"]["steps"][-1]["with"]
    download = next(step["with"] for step in steps if "actions/download-artifact@" in step.get("uses", ""))
    assert upload["name"] == "hardware-candidate-${{ github.sha }}-${{ github.run_attempt }}"
    assert download["artifact-ids"] == (
        "${{ needs.reuse-offline.outputs.artifact-id || needs.candidate-wheel.outputs.artifact-id }}"
    )
    assert download["run-id"] == "${{ needs.reuse-offline.outputs.run-id || github.run_id }}"
    assert download["github-token"] == "${{ github.token }}"
    assert set(download) == {"artifact-ids", "run-id", "github-token", "path"}
    assert hardware["permissions"] == {"contents": "read", "actions": "read"}
    assert jobs["reuse-offline"]["permissions"] == {"contents": "read", "actions": "read"}
    assert upload["path"].endswith("/*.whl")
    assert "--run-quantum" not in json.dumps(jobs["candidate-wheel"])
    for name, job in jobs.items():
        safe_job = {**job, "steps": job.get("steps", [])[:-1]} if name == "hardware" else job
        assert "secrets." not in json.dumps(safe_job)
        for step in job.get("steps", []):
            if "uses" in step:
                assert re.fullmatch(r"[\w/-]+@[a-f0-9]{40}", step["uses"])


def test_coverage_is_offline() -> None:
    """Coverage runs synthetic tests without hardware opt-ins or credentials."""
    coverage = yaml.safe_load((WORKFLOW.parent / "cpp-coverage.yml").read_text(encoding="utf-8"))
    jobs = coverage["jobs"]
    assert all("environment" not in job for job in jobs.values())
    serialized = json.dumps(coverage)
    assert "secrets." not in serialized
    assert "--run-live" not in serialized
    assert "--run-quantum" not in serialized
    steps = jobs["coverage"]["steps"]
    transport = next(step for step in steps if "--native-library=" in step.get("run", ""))
    assert "nox -s native_tests" in transport["run"]
    assert "build/coverage/src/" in transport["run"]


@pytest.mark.parametrize("label", ["bug", "live-qpu-tests"])
@pytest.mark.parametrize("same_repo", [False, True])
@pytest.mark.parametrize("reuse", ["success", "failure", "cancelled", "skipped"])
@pytest.mark.parametrize("hardware_needed", ["true", "false"])
def test_label_routes(label: str, reuse: str, hardware_needed: str, *, same_repo: bool) -> None:
    """Labels never rebuild or override unrelated required checks."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    context: dict[str, str | list[str]] = {
        "github.workflow": "CI",
        "github.run_id": "100",
        "github.head_ref": "feature",
        "github.ref": "refs/pull/13/merge",
        "github.event_name": "pull_request",
        "github.event.action": "labeled",
        "github.event.label.name": label,
        "github.repository": "owner/device",
        "github.event.pull_request.head.repo.full_name": "owner/device" if same_repo else "fork/device",
        "github.event.pull_request.labels.*.name": ["live-qpu-tests", label],
        "needs.offline-checks-pass.result": "skipped",
        "needs.candidate-wheel.result": "skipped",
        "needs.reuse-offline.result": reuse,
        "needs.reuse-offline.outputs.hardware-needed": hardware_needed,
    }
    active = same_repo and label == "live-qpu-tests"
    assert bool(evaluate(jobs["reuse-offline"]["if"], context)) == active
    for job in ("change-detection", "documentation", "candidate-wheel", "offline-checks-pass"):
        assert not evaluate(jobs[job]["if"], context)
    # Every other offline job inherits the skipped change-detection dependency.
    for job in jobs["offline-checks-pass"]["needs"]:
        if job not in {"change-detection", "documentation", "candidate-wheel"}:
            assert jobs[job]["needs"] == "change-detection"
            assert "always()" not in jobs[job]["if"]

    final = jobs["required-checks-pass"]
    assert bool(evaluate(final["if"], context)) == active
    assert evaluate(final["name"].strip()[3:-2], context) == ("🚦 Check" if active else "Ignored label")
    if active:
        assert bool(evaluate(jobs["hardware"]["if"], context)) == (reuse == "success" and hardware_needed == "true")
        skips = skip_list(final["steps"][0]["with"]["allowed-skips"], context)
        assert "offline-checks-pass" in skips
        assert "reuse-offline" not in skips
        assert ("hardware" in skips) == (reuse == "success" and hardware_needed == "false")
        context["cancelled"] = "true"
        assert not evaluate(jobs["hardware"]["if"], context)

    group = workflow["concurrency"]["group"]
    rendered = re.sub(r"\$\{\{(.*?)\}\}", lambda match: str(evaluate(match[1], context)), group)
    assert rendered == "CI-100"
    context["github.event.action"] = "synchronize"
    rendered = re.sub(r"\$\{\{(.*?)\}\}", lambda match: str(evaluate(match[1], context)), group)
    assert rendered == "CI-feature"
