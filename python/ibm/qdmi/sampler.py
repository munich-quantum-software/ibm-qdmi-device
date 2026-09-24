# Copyright (c) 2025 - 2026 IQM Finland Oy
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

"""Run a serialized workload on IBM or the local simulator."""

from __future__ import annotations

import argparse
import base64
import pickle  # ruff:ignore[suspicious-pickle-import]
from pathlib import Path
from typing import TYPE_CHECKING

from qiskit import qpy

from .offloader import sample

if TYPE_CHECKING:
    from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> None:
    """Execute the worker using trusted inputs from the shared jobs directory."""
    parser = argparse.ArgumentParser(description="Sample a serialized QPY circuit.")
    parser.add_argument("circuit", help="Path to the QPY circuit file.")
    parser.add_argument("--shots", type=int, required=True, help="Number of shots.")
    parser.add_argument("--simulator", action="store_true", help="Use the local simulator without IBM access.")
    parser.add_argument("--backend-name", help="IBM backend selection; otherwise use IBM_QUANTUM_BACKEND.")
    args = parser.parse_args(argv)
    with Path(args.circuit).open("rb") as stream:
        circuit = qpy.load(stream)[0]
    result = sample(
        circuit,
        shots=args.shots,
        local=True,
        simulator=args.simulator,
        backend_name=args.backend_name,
    )
    print(base64.b64encode(pickle.dumps(result)).decode("ascii"))


if __name__ == "__main__":
    main()
