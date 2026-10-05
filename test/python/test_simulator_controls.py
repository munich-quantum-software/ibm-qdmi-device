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

"""Check simulator opt-in and loopback restrictions in separate pytest runs."""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Sequence


def run_simulator_tests(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run only simulator checks with the installed test interpreter.

    Returns:
        Captured pytest output and exit status.
    """
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed interpreter and repository test
        [
            sys.executable,
            "-m",
            "pytest",
            "test/integration/test_simulator_metadata.py",
            "-o",
            "addopts=",
            "-n",
            "0",
            *arguments,
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_simulator_requires_explicit_endpoint() -> None:
    """Selecting the marker alone cannot open a native session."""
    result = run_simulator_tests(["-m", "simulator"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 skipped" in result.stdout


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8290",
        "http://quantum.cloud.ibm.com",
        "http://127.0.0.1:8290/api",
        "http://user:password@127.0.0.1:8290",
        "http://127.0.0.1:8290?query=1",
        "http://127.0.0.1:invalid",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
    ],
)
def test_simulator_rejects_non_loopback_origin(url: str) -> None:
    """Reject unsupported endpoints before collection and native access."""
    result = run_simulator_tests(["--simulator-url", url, "--collect-only"])
    assert result.returncode == 4, result.stdout + result.stderr
    assert "simulator URL must be a loopback HTTP origin" in result.stderr


@pytest.mark.parametrize("url", ["http://127.0.0.1:8290", "http://localhost:8290/", "http://[::1]:8290"])
def test_simulator_accepts_loopback_origin(url: str) -> None:
    """Collect against loopback origins without connecting to a service."""
    result = run_simulator_tests(["--simulator-url", url, "--collect-only"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 tests collected" in result.stdout


def test_unavailable_simulator_fails() -> None:
    """An explicit simulator run cannot pass by skipping missing service access."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        result = run_simulator_tests(["--simulator-url", url])
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAILED" in result.stdout
    assert "skipped" not in result.stdout
