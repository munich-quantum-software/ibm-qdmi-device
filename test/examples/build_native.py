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

"""Build the native example against the installed wheel before testing it."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ibm.qdmi import IBM_QDMI_CMAKE_DIR


def main() -> None:
    """Configure and compile the installed-package consumer.

    Raises:
        RuntimeError: CMake is unavailable on the executable search path.
    """
    cmake = shutil.which("cmake")
    if cmake is None:
        msg = "Install CMake before building the native example."
        raise RuntimeError(msg)
    root = Path(__file__).resolve().parents[2]
    build = root / "build/examples/native"
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed CMake arguments
        [
            cmake,
            "-S",
            str(root / "examples/native"),
            "-B",
            str(build),
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_PREFIX_PATH={IBM_QDMI_CMAKE_DIR}",
        ],
        cwd=root,
        check=True,
        timeout=300,
    )
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed CMake arguments
        [cmake, "--build", str(build), "--target", "ibm-qdmi-execute", "--parallel", "2"],
        cwd=root,
        check=True,
        timeout=300,
    )


if __name__ == "__main__":
    main()
