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

"""Run the optional Aer reference with a fresh native-library loader state."""

from __future__ import annotations

import json
import sys

from qiskit_aer import AerSimulator
from qiskit_service import submitted_circuit

if __name__ == "__main__":
    circuit = submitted_circuit(json.load(sys.stdin))
    memory = (
        AerSimulator()
        .run(circuit.decompose(reps=4), shots=int(sys.argv[1]), memory=True, seed_simulator=7)
        .result()
        .get_memory()
    )
    print(json.dumps(memory))
