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

"""Information CLI behavior without driver or backend access."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from ibm import qdmi
from ibm.qdmi.__main__ import main

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("option", "expected"),
    [
        ("include_dir", qdmi.IBM_QDMI_INCLUDE_DIR),
        ("cmake_dir", qdmi.IBM_QDMI_CMAKE_DIR),
        ("lib_path", qdmi.IBM_QDMI_LIBRARY_PATH),
        ("catalog_path", qdmi.IBM_QDMI_CATALOG_PATH),
    ],
)
def test_paths(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], option: str, expected: Path
) -> None:
    """Print exactly the requested installed path."""
    monkeypatch.setattr(sys, "argv", ["ibm-qdmi", f"--{option}"])
    main()
    assert capsys.readouterr().out.strip() == str(expected)


@pytest.mark.parametrize("argument", ["--help", "--version"])
def test_help_and_version(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argument: str) -> None:
    """Information options exit successfully before opening a session."""
    monkeypatch.setattr(sys, "argv", ["ibm-qdmi", argument])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 0
    assert (qdmi.__version__ if argument == "--version" else "--catalog_path") in capsys.readouterr().out


def test_no_arguments(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """No option prints usage."""
    monkeypatch.setattr(sys, "argv", ["ibm-qdmi"])
    main()
    assert "--catalog_path" in capsys.readouterr().out
