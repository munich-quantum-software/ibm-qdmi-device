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

"""Shared command-line configuration for examples."""

from __future__ import annotations

import argparse

from mqt.core.plugins.qiskit.backend import QDMIBackend

from ibm.qdmi.qiskit import IBMBackend


def positive_integer(value: str) -> int:
    """Parse a positive shot count or timeout.

    Returns:
        The parsed integer.

    Raises:
        argparse.ArgumentTypeError: If the value is not a positive integer.
    """
    try:
        result = int(value)
    except ValueError as error:
        msg = "Use a positive integer."
        raise argparse.ArgumentTypeError(msg) from error
    if result <= 0:
        msg = "Use a positive integer."
        raise argparse.ArgumentTypeError(msg)
    return result


def parser(description: str) -> argparse.ArgumentParser:
    """Create an offline-first example parser.

    Returns:
        A parser with explicit hardware selection and bounded shots.
    """
    result = argparse.ArgumentParser(description=description)
    result.add_argument("--backend", choices=("sim", "ibm"), default="sim")
    result.add_argument("--device", choices=("ibm.default", "ibm.berlin", "ibm.aachen"))
    result.add_argument("--shots", type=positive_integer, default=128)
    return result


def open_backend(backend: str, device: str | None) -> QDMIBackend:
    """Open the selected simulator or IBM device.

    Returns:
        A shared Qiskit backend.

    Raises:
        ValueError: IBM execution lacks an explicit catalogue selection.
    """
    if backend == "sim":
        return QDMIBackend.from_device_id("mqt.ddsim.default")
    if device is None:
        msg = "IBM execution requires --device and configured credentials."
        raise ValueError(msg)
    return IBMBackend(device)
