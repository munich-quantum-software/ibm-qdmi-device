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

"""Optional IBM Executor programs over the native QDMI transport."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mqt.core.qdmi import CustomProperty, Job, ProgramFormat

try:
    from qiskit_ibm_runtime.decoders.quantum_program.decoder import QuantumProgramResultDecoder
    from qiskit_ibm_runtime.options_models.executor import ExecutorOptions
    from qiskit_ibm_runtime.quantum_program.params_converters import QUANTUM_PROGRAM_PARAMS_CONVERTERS
except ImportError as error:
    msg = "Install 'ibm-qdmi[executor]' to use Executor."
    raise ImportError(msg) from error

if TYPE_CHECKING:
    from qiskit.primitives import PrimitiveResult
    from qiskit_ibm_runtime.quantum_program import QuantumProgram
    from qiskit_ibm_runtime.results import QuantumProgramResult

    from .qiskit import IBMBackend

__all__ = ["Executor", "ExecutorJob"]


class ExecutorJob:
    """An Executor job with native QDMI lifecycle and IBM result decoding.

    Args:
        job: A native job submitted or retrieved through Executor.
    """

    def __init__(self, job: Job) -> None:
        """Retain the native handle and its session.

        Raises:
            ValueError: The handle does not represent an Executor program.
        """
        if job.program_format != ProgramFormat.CUSTOM1:
            msg = "The job is not an IBM Executor program."
            raise ValueError(msg)
        self._job = job

    def job_id(self) -> str:
        """Return the remote job identifier."""
        return self._job.id

    def status(self) -> Job.Status:
        """Query the current QDMI job status.

        Returns:
            The native QDMI status.
        """
        return self._job.check()

    def cancel(self) -> None:
        """Cancel the remote job through QDMI."""
        self._job.cancel()

    def result(self, timeout: int = 0) -> QuantumProgramResult | PrimitiveResult:
        """Wait and decode results without flattening experiment dimensions.

        Args:
            timeout: Wait limit in seconds; zero waits indefinitely.

        Returns:
            IBM's decoded result, including samplex correction metadata.

        Raises:
            TimeoutError: The wait limit expired. The remote job remains active.
            RuntimeError: The device did not supply Executor results.
        """
        if not self._job.wait(timeout):
            msg = "Executor job did not finish within the wait limit."
            raise TimeoutError(msg)
        raw = self._job.get_custom_result(CustomProperty.CUSTOM1, str)
        if raw is None:
            msg = "The device did not return Executor results."
            raise RuntimeError(msg)
        return QuantumProgramResultDecoder.decode(raw)


class Executor:
    """Run QuantumProgram objects through an IBM QDMI backend.

    Circuits must already target the selected device. Execution uses independent
    jobs, without IBM Runtime session or batch contexts. The optional Runtime
    dependency supplies the v2.0 encoder and result decoder.

    Args:
        backend: An open IBM QDMI backend.
        options: IBM Executor options. Nondefault environment settings are
            unsupported. The native execution cap is 60 seconds.
    """

    def __init__(self, backend: IBMBackend, *, options: ExecutorOptions | None = None) -> None:
        """Retain the backend without opening another connection."""
        self._backend = backend
        self.options = options if options is not None else ExecutorOptions()

    def run(self, program: QuantumProgram) -> ExecutorJob:
        """Encode and submit one program through the native device.

        Returns:
            A job that preserves the complete Executor result.

        Raises:
            ValueError: Unsupported environment or simulator settings, or an empty program.
        """
        if not program.items:
            msg = "An Executor program must contain at least one item."
            raise ValueError(msg)
        environment = self.options.environment.model_dump(exclude_defaults=True)
        if environment:
            msg = "Nondefault Executor environment options are unsupported."
            raise ValueError(msg)
        if self.options.experimental.get("local_mode") or "simulator_options" in self.options.experimental:
            msg = "Local Executor simulation is unsupported by the QDMI transport."
            raise ValueError(msg)
        params = QUANTUM_PROGRAM_PARAMS_CONVERTERS["v2.0"].encoder(program, self.options)
        job = self._backend.device.submit_job(
            params.model_dump_json(),
            ProgramFormat.CUSTOM1,
        )
        return ExecutorJob(job)

    def retrieve_job(self, job_id: str) -> ExecutorJob:
        """Open an existing Executor job on this backend.

        Returns:
            A job with the same lifecycle and decoding as a new submission.
        """
        return ExecutorJob(self._backend.device.retrieve_job_by_id(job_id))
