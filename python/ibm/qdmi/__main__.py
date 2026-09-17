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

"""Print package information without initializing a device."""

from __future__ import annotations

import argparse

from . import (
    IBM_QDMI_CATALOG_PATH,
    IBM_QDMI_CMAKE_DIR,
    IBM_QDMI_INCLUDE_DIR,
    IBM_QDMI_LIBRARY_PATH,
    __version__,
)


def main() -> None:
    """Print the selected installed path or package version."""
    parser = argparse.ArgumentParser(prog="ibm-qdmi", description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--version", action="version", version=__version__)
    for option, path in (
        ("include_dir", IBM_QDMI_INCLUDE_DIR),
        ("cmake_dir", IBM_QDMI_CMAKE_DIR),
        ("lib_path", IBM_QDMI_LIBRARY_PATH),
        ("catalog_path", IBM_QDMI_CATALOG_PATH),
    ):
        options.add_argument(f"--{option}", dest="path", action="store_const", const=path)
    args = parser.parse_args()
    if args.path is None:
        parser.print_help()
    else:
        print(args.path)


if __name__ == "__main__":
    main()
