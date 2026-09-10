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

"""Exercise live opt-in and reporting in isolated, network-free pytest runs."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Sequence


def run_live_tests(
    tmp_path: Path, arguments: Sequence[str], *, credentials: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run the actual live test with guarded credentials and library loading.

    Returns:
        Captured, synthetic-only pytest diagnostics.
    """
    source = Path(__file__).parent
    for name in ("conftest.py", "test_live_metadata.py", "metadata_checks.py", "native_support.py"):
        shutil.copyfile(source / name, tmp_path / name)
    (tmp_path / "pyproject.toml").write_text('[tool.pytest]\nfilterwarnings = ["error"]\n', encoding="utf-8")
    # The guard replaces the test's environment and loader before any test body.
    # Even a regression in opt-in handling cannot reach the real native client.
    (tmp_path / "guard.py").write_text(
        """from types import SimpleNamespace
import pytest

class Credentials:
    def get(self, name, default):
        if not ENABLED:
            raise AssertionError("credential read without opt-in")
        return "synthetic-private-value" if PRESENT else ""

def blocked_library():
    raise RuntimeError("synthetic-private-value")

@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    global ENABLED
    ENABLED = config.getoption("run_live")
    for item in items:
        item.module.os = SimpleNamespace(environ=Credentials())
        item.module.load_native = blocked_library
"""
        f"\nPRESENT = {credentials!r}\n",
        encoding="utf-8",
    )
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed interpreter and local synthetic test files
        [sys.executable, "-m", "pytest", "-p", "guard", "-n", "0", *arguments],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_default_skips_before_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ordinary and wheel test invocations cannot activate live credentials."""
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "synthetic-private-value")
    monkeypatch.setenv("IBM_QUANTUM_INSTANCE_CRN", "synthetic-private-value")
    result = run_live_tests(tmp_path, [])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 skipped" in result.stdout


@pytest.mark.parametrize("selection", ["both", "ibm_berlin", "ibm_aachen"])
def test_live_selection_and_redaction(tmp_path: Path, selection: str) -> None:
    """Selected backends fail safely without exposing exception values or locals."""
    result = run_live_tests(
        tmp_path, ["--run-live", "--ibm-backend", selection, "--showlocals", "--full-trace", "-n", "2"]
    )
    assert result.returncode == 1
    assert "unexpected failure" in result.stdout
    assert "synthetic-private-value" not in result.stdout + result.stderr
    assert "workers" not in result.stdout
    assert ("2 failed" if selection == "both" else "1 failed, 1 skipped") in result.stdout


def test_missing_live_credentials(tmp_path: Path) -> None:
    """Explicit live requests fail clearly when credentials are absent."""
    result = run_live_tests(tmp_path, ["--run-live"], credentials=False)
    assert result.returncode == 1
    assert "missing credentials" in result.stdout


def test_invalid_live_selection(tmp_path: Path) -> None:
    """Reject unknown backends without echoing arbitrary input."""
    result = run_live_tests(tmp_path, ["--run-live", "--ibm-backend", "synthetic-private-value"])
    assert result.returncode == 4
    assert "invalid backend selection" in result.stderr
    assert "synthetic-private-value" not in result.stdout + result.stderr
