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


def evaluate(expression: str, context: dict[str, str]) -> bool | str:
    """Evaluate the workflow's boolean/string subset without executing code.

    Returns:
        The expression value.
    """
    expression = re.sub(r"(?:github|needs)\.[\w.-]+", lambda match: repr(context[match[0]]), expression)
    expression = expression.replace("&&", " and ").replace("||", " or ")

    def visit(node: ast.AST) -> bool | str:
        if isinstance(node, ast.Constant) and isinstance(node.value, (bool, str)):
            return node.value
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
            if node.func.id == "fromJSON" and len(node.args) == 1:
                argument = visit(node.args[0])
                assert isinstance(argument, str)
                value = json.loads(argument)
                assert isinstance(value, bool)
                return value
            if node.func.id == "always" and not node.args:
                return True
        msg = "CI gate expression is outside the checked subset"
        raise AssertionError(msg)

    return visit(ast.parse("(" + expression.strip() + ")", mode="eval").body)


def skip_list(expression: str, context: dict[str, str]) -> set[str]:
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
def test_hardware_eligibility(event: str, ref: str, result: str, gate: str) -> None:
    """PRs, merge queues, non-main dispatches, and failed gates cannot spend."""
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    context = {
        "github.ref": ref,
        "github.event_name": event,
        "needs.offline-checks-pass.result": "success",
        "needs.candidate-wheel.result": "success",
    }
    context[f"needs.{gate}.result"] = result
    eligible = ref == "refs/heads/main" and event in {"push", "workflow_dispatch"}
    assert bool(evaluate(jobs["hardware"]["if"], context)) == (eligible and result == "success")
    final = jobs["required-checks-pass"]
    assert final["name"] == "🚦 Check"
    assert final["if"] == "always()"
    assert set(final["needs"]) == {"offline-checks-pass", "hardware"}
    assert skip_list(final["steps"][0]["with"]["allowed-skips"], context) == (set() if eligible else {"hardware"})


def test_main_requires_every_offline_job() -> None:
    """Change detection cannot bypass an Actions prerequisite on main."""
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    gate = jobs["offline-checks-pass"]
    expected = set(jobs) - {"offline-checks-pass", "hardware", "required-checks-pass"}
    assert set(gate["needs"]) == expected
    assert gate["if"] == "always()"
    context = {"github.ref": "refs/heads/main"}
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
    assert set(workflow.get("on", workflow.get(True))) == {"push", "pull_request", "merge_group", "workflow_dispatch"}
    jobs = workflow["jobs"]
    hardware = jobs["hardware"]
    assert hardware["environment"] == "ibm-quantum"
    assert hardware["timeout-minutes"] == 40
    assert hardware["concurrency"]["cancel-in-progress"] is False
    assert set(hardware["needs"]) == {"offline-checks-pass", "candidate-wheel"}
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
    assert upload["name"] == download["name"]
    assert set(download) == {"name", "path"}  # The current run only, never another branch's artifact.
    assert upload["path"].endswith("/*.whl")
    assert "--run-quantum" not in json.dumps(jobs["candidate-wheel"])
    for name, job in jobs.items():
        safe_job = {**job, "steps": job.get("steps", [])[:-1]} if name == "hardware" else job
        assert "secrets." not in json.dumps(safe_job)
        for step in job.get("steps", []):
            if "uses" in step:
                assert re.fullmatch(r"[\w/-]+@[a-f0-9]{40}", step["uses"])
