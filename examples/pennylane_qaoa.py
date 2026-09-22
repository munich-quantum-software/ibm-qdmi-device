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

"""Evaluate and sample one QAOA layer with finite shots."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pennylane as qml

from examples.common import parser

if TYPE_CHECKING:
    from pennylane.devices import Device
    from pennylane.measurements import CountsMP, ExpectationMP


def run(device: Device, shots: int) -> tuple[float, dict[str, int]]:
    """Evaluate the two-vertex MaxCut objective and sample its QAOA state.

    Returns:
        The estimated cut value and measured counts.
    """

    def ansatz() -> None:
        qml.Hadamard(0)
        qml.Hadamard(1)
        qml.IsingZZ(0.8, wires=[0, 1])
        qml.RX(0.6, wires=0)
        qml.RX(0.6, wires=1)

    @qml.set_shots(shots)
    @qml.qnode(device)
    def objective() -> ExpectationMP:
        ansatz()
        return qml.expval(0.5 * (qml.Identity(0) - qml.PauliZ(0) @ qml.PauliZ(1)))

    @qml.set_shots(shots)
    @qml.qnode(device)
    def sample() -> CountsMP:
        ansatz()
        return qml.counts(wires=[0, 1])

    return float(objective()), {str(key): int(value) for key, value in sample().items()}


def main() -> None:
    """Execute two finite-shot circuits on the selected device."""
    arguments = parser(__doc__ or "")
    options = arguments.parse_args()
    if options.backend == "ibm" and options.device is None:
        arguments.error("--backend ibm requires --device")
    if options.backend == "sim":
        device = qml.device("mqt.ddsim.default", wires=2)
    else:
        device = qml.device(options.device, wires=2)
    value, counts = run(device, options.shots)
    print(json.dumps({"cut_value": value, "counts": counts}, sort_keys=True))


if __name__ == "__main__":
    main()
