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

"""Run the compiled C example against the synthetic IBM runtime."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from offline_service import CRN
from qiskit_service import remote_runtime


@pytest.fixture
def executable() -> Path:
    """Locate the explicitly built example.

    Returns:
        The native example executable.
    """
    default = (
        Path(__file__).resolve().parents[2]
        / "build/examples/native"
        / ("ibm-qdmi-execute.exe" if os.name == "nt" else "ibm-qdmi-execute")
    )
    result = Path(os.environ.get("IBM_QDMI_NATIVE_EXAMPLE", default)).resolve()
    assert result.is_file(), "Build the C example with `uvx nox -s examples` before running its tests"
    return result


def run_example(
    executable: Path, *args: str, api_key: str = "synthetic-key", crn: str = CRN
) -> subprocess.CompletedProcess[str]:
    """Execute with synthetic credentials and no inherited IBM settings.

    Returns:
        Captured output and process status.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("IBM_QUANTUM_")}
    env.update(IBM_QUANTUM_API_KEY=api_key, IBM_QUANTUM_INSTANCE_CRN=crn)
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed example and synthetic inputs
        [str(executable), *args], env=env, capture_output=True, text=True, timeout=30, check=False
    )


def test_help_requires_no_service(executable: Path) -> None:
    """The default invocation describes how to opt in without contacting IBM."""
    result = run_example(executable)
    assert result.returncode == 0
    assert "--run BACKEND" in result.stdout
    assert not result.stderr


@pytest.mark.parametrize(
    "option",
    [
        ("--timeout", "0"),
        ("--timeout", "61"),
        ("--test-port", "0"),
        ("--test-port", "65536"),
        ("--test-port", "-1"),
        ("--test-port", "65535/auth"),
        ("--test-port", "65535@external.invalid"),
        ("--test-port", "http://127.0.0.1:65535"),
    ],
)
def test_invalid_options_submit_nothing(executable: Path, option: tuple[str, str]) -> None:
    """Only bounded numeric ports and wait timeouts reach session initialization."""
    result = run_example(executable, "--run", "ibm_test", *option)
    assert result.returncode != 0
    assert "synthetic-key" not in result.stderr
    assert CRN not in result.stderr


@pytest.mark.parametrize(("api_key", "crn"), [("", CRN), ("synthetic-key", "")])
def test_missing_credentials_make_no_requests(executable: Path, api_key: str, crn: str) -> None:
    """Native environment defaults reject missing credentials before transport."""
    with remote_runtime() as runtime:
        port = runtime.snapshot()["url"].rsplit(":", 1)[1]
        result = run_example(executable, "--run", "ibm_test", "--test-port", port, api_key=api_key, crn=crn)
        assert result.returncode != 0
        assert not result.stdout
        assert "Initialize session: QDMI status" in result.stderr
        assert "synthetic-key" not in result.stderr
        assert CRN not in result.stderr
        assert not runtime.snapshot()["requests"]


def test_authentication_failure_is_redacted(executable: Path) -> None:
    """An IAM rejection reports a status without credential values or submission."""
    with remote_runtime() as runtime:
        runtime.set_failure("authentication")
        port = runtime.snapshot()["url"].rsplit(":", 1)[1]
        result = run_example(executable, "--run", "ibm_test", "--test-port", port)
        assert result.returncode != 0
        assert not result.stdout
        assert "Initialize session: QDMI status" in result.stderr
        assert "synthetic-key" not in result.stderr
        assert CRN not in result.stderr
        snapshot = runtime.snapshot()
        assert [path for path, _, _ in snapshot["requests"]] == ["/auth"]
        assert not snapshot["submissions"]


def test_native_lifecycle(executable: Path) -> None:
    """A full physical register yields ordered shots through the installed ABI."""
    with remote_runtime() as runtime:
        port = runtime.snapshot()["url"].rsplit(":", 1)[1]
        result = run_example(executable, "--run", "ibm_test", "--test-port", port)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().split(",") == ["1"] * 16
        assert not result.stderr
        snapshot = runtime.snapshot()
        assert len(snapshot["submissions"]) == 1
        request = snapshot["submissions"][0]
        assert request["cost"] == 60
        assert request["params"]["pubs"][0][2] == 16
        assert "qubit[5] q;" in request["params"]["pubs"][0][0]
        assert not snapshot["cancellations"]


def test_timeout_cancels_without_resubmission(executable: Path) -> None:
    """A bounded wait attempts cancellation before freeing native handles."""
    with remote_runtime() as runtime:
        runtime.set_state("Queued", 0)
        port = runtime.snapshot()["url"].rsplit(":", 1)[1]
        result = run_example(executable, "--run", "ibm_test", "--test-port", port, "--timeout", "1")
        assert result.returncode != 0
        assert "Wait for job: QDMI status" in result.stderr
        assert len(runtime.snapshot()["submissions"]) == 1
        assert runtime.snapshot()["cancellations"] == ["synthetic-1"]
