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


def run_example(executable: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Execute with synthetic credentials and no inherited IBM settings.

    Returns:
        Captured output and process status.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("IBM_QUANTUM_")}
    env.update(IBM_QUANTUM_API_KEY="synthetic-key", IBM_QUANTUM_INSTANCE_CRN=CRN)
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed example and synthetic inputs
        [str(executable), *args], env=env, capture_output=True, text=True, timeout=30, check=False
    )


def test_help_requires_no_service(executable: Path) -> None:
    """The default invocation describes how to opt in without contacting IBM."""
    result = run_example(executable)
    assert result.returncode == 0
    assert "--run BACKEND" in result.stdout
    assert not result.stderr


@pytest.mark.parametrize("option", [("--timeout", "0"), ("--timeout", "61"), ("--endpoint", "https://example.com")])
def test_invalid_options_submit_nothing(executable: Path, option: tuple[str, str]) -> None:
    """Invalid bounds and non-loopback overrides fail before authentication."""
    result = run_example(executable, "--run", "ibm_test", *option)
    assert result.returncode != 0
    assert "synthetic-key" not in result.stderr
    assert CRN not in result.stderr


def test_native_lifecycle(executable: Path) -> None:
    """A full physical register yields ordered shots through the installed ABI."""
    with remote_runtime() as runtime:
        result = run_example(executable, "--run", "ibm_test", "--endpoint", runtime.snapshot()["url"])
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
        result = run_example(executable, "--run", "ibm_test", "--endpoint", runtime.snapshot()["url"], "--timeout", "1")
        assert result.returncode != 0
        assert "Wait for job: QDMI status" in result.stderr
        assert len(runtime.snapshot()["submissions"]) == 1
        assert runtime.snapshot()["cancellations"] == ["synthetic-1"]
