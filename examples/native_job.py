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

"""Submit one OpenQASM or QPY job through the native QDMI interface."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING

from mqt.core.qdmi import Job, ProgramFormat

from examples.common import open_backend, parser, positive_integer

if TYPE_CHECKING:
    from mqt.core.qdmi import Device


def run(
    device: Device,
    shots: int,
    timeout: int = 60,
    *,
    qubits: int | None = None,
    program_format: ProgramFormat = ProgramFormat.QASM3,
) -> dict[str, int]:
    """Execute one measured X gate with a finite wait.

    Args:
        device: An open QDMI device.
        shots: Positive shot count.
        timeout: Maximum wait in seconds.
        qubits: Program width; defaults to the full physical device width.
        program_format: OpenQASM 3 or QPY submission format.

    Returns:
        Classified counts, preserving the classical-bit convention.

    Raises:
        ValueError: Shots, timeout, or device width is invalid.
    """
    width = device.qubits_num() if qubits is None else qubits
    if shots <= 0 or timeout <= 0 or not 1 <= width <= device.qubits_num():
        msg = "Shots, timeout, and device width must be positive."
        raise ValueError(msg)
    if program_format == ProgramFormat.QPY:
        from qiskit import QuantumCircuit  # ruff: ignore[import-outside-top-level]

        from ibm.qdmi.serializers import qiskit_to_qpy  # ruff: ignore[import-outside-top-level]

        circuit = QuantumCircuit(width, 1)
        circuit.x(0)
        circuit.measure(0, 0)
        program = qiskit_to_qpy(circuit, width)
    elif program_format == ProgramFormat.QASM3:
        program = f'OPENQASM 3.0; include "stdgates.inc"; qubit[{width}] q; bit[1] c; x q[0]; c[0] = measure q[0];'
    else:
        msg = "Choose OpenQASM 3 or QPY."
        raise ValueError(msg)
    job = device.submit_job(program, program_format, shots)
    try:
        return _wait_for_counts(job, timeout)
    except BaseException:
        with contextlib.suppress(Exception):
            job.cancel()
        raise


def _wait_for_counts(job: Job, timeout: int) -> dict[str, int]:
    if not job.wait(timeout):
        msg = "The QDMI wait expired."
        raise TimeoutError(msg)
    if job.check() != Job.Status.DONE:
        msg = "The QDMI job did not complete successfully."
        raise RuntimeError(msg)
    return job.get_counts()


def main() -> None:
    """Run the direct QDMI example."""
    arguments = parser(__doc__ or "")
    arguments.add_argument("--timeout", type=positive_integer, default=60)
    arguments.add_argument("--format", choices=["qasm3", "qpy"], default="qasm3")
    options = arguments.parse_args()
    if options.backend == "ibm" and options.device is None:
        arguments.error("--backend ibm requires --device")
    backend = open_backend(options.backend, options.device)
    width = 1 if options.backend == "sim" else backend.num_qubits
    program_format = ProgramFormat.QPY if options.format == "qpy" else ProgramFormat.QASM3
    print(
        json.dumps(
            run(backend.device, options.shots, options.timeout, qubits=width, program_format=program_format),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
