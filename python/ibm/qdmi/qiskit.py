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

"""Public Qiskit backend backed by the native IBM QDMI device."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from mqt.core.mlir import CompiledProgram
    from mqt.core.plugins.qiskit.backend import QDMIBackend
    from mqt.core.plugins.qiskit.exceptions import CircuitValidationError
    from mqt.core.qdmi.builtin_driver import open_device
except ImportError as error:
    msg = "Install 'ibm-qdmi[qiskit]' to use IBMBackend."
    raise ImportError(msg) from error

from qiskit.circuit import QuantumCircuit

from . import IBM_QDMI_DEVICE_ID
from ._catalogue import session_parameters

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mqt.core.plugins.qiskit.backend import ParametersType
    from mqt.core.plugins.qiskit.job import QDMIJob
    from mqt.core.plugins.qiskit.provider import QDMIProvider
    from mqt.core.qdmi import Device
    from qiskit_ibm_runtime.options_models.executor import ExecutorOptions

    from .executor import Executor

__all__ = ["IBMBackend"]


class IBMBackend(QDMIBackend):
    """Execute through an IBM QDMI session using MQT Core's shared adapter.

    Args:
        device: An already-open QDMI device, exclusive with connection overrides.
        provider: Provider associated with this backend.
        device_id: Catalogue ID, or identity metadata for an already-open device.
        backend_name: Backend override; otherwise use environment or catalogue defaults.
        api_key: IBM Cloud API key; defaults to ``IBM_QUANTUM_API_KEY``.
        instance_crn: Instance CRN; defaults to ``IBM_QUANTUM_INSTANCE_CRN``.
        base_url: Trusted API endpoint override, principally for loopback tests.
        auth_url: Trusted IAM endpoint override, principally for loopback tests.
    """

    def __init__(
        self,
        device_id: str | None = None,
        *,
        device: Device | None = None,
        provider: QDMIProvider | None = None,
        backend_name: str | None = None,
        api_key: str | None = None,
        instance_crn: str | None = None,
        base_url: str | None = None,
        auth_url: str | None = None,
    ) -> None:
        """Open a fresh session or adapt the supplied device.

        Raises:
            ValueError: An open device conflicts with connection overrides.
        """
        overrides = (backend_name, api_key, instance_crn, base_url, auth_url)
        if device is not None:
            if any(value is not None for value in overrides):
                msg = "An already-open device is exclusive with connection overrides."
                raise ValueError(msg)
            super().__init__(device=device, provider=provider, device_id=device_id)
            return

        resolved_id = IBM_QDMI_DEVICE_ID if device_id is None else device_id
        device = open_device(
            resolved_id,
            **session_parameters(
                device_id=resolved_id,
                backend_name=backend_name,
                api_key=api_key,
                instance_crn=instance_crn,
                base_url=base_url,
                auth_url=auth_url,
            ),
        )
        super().__init__(device=device, provider=provider, device_id=resolved_id)

    @staticmethod
    def _preprocess_circuit(circuit: QuantumCircuit) -> QuantumCircuit:
        """Require the measurements used to produce Sampler results.

        Returns:
            The unchanged circuit.

        Raises:
            mqt.core.plugins.qiskit.exceptions.CircuitValidationError:
                The circuit has no measurement.
        """
        if not any(instruction.operation.name == "measure" for instruction in circuit.data):
            msg = "At least one measurement is required."
            raise CircuitValidationError(msg)
        return circuit

    def executor(self, *, options: ExecutorOptions | None = None) -> Executor:
        """Create the optional Executor primitive using this QDMI session.

        Returns:
            An Executor requiring the ``ibm-qdmi[executor]`` extra.
        """
        from .executor import Executor  # ruff: ignore[import-outside-top-level]

        return Executor(self, options=options)

    def run(
        self,
        run_input: QuantumCircuit | CompiledProgram | Sequence[QuantumCircuit | CompiledProgram],
        parameter_values: Sequence[ParametersType] | None = None,
        **options: Any,  # ruff: ignore[any-type]
    ) -> QDMIJob:
        """Submit validated circuits through the shared job and result adapter.

        Returns:
            MQT Core's QDMI job, with indexed results from a native multi-program job.

        Raises:
            mqt.core.plugins.qiskit.exceptions.CircuitValidationError:
                The requested shot count is zero.
        """
        if options.get("shots", self.options.shots) == 0:
            msg = "shots must be positive."
            raise CircuitValidationError(msg)
        programs = [run_input] if isinstance(run_input, (QuantumCircuit, CompiledProgram)) else run_input
        if any(
            isinstance(program, CompiledProgram)
            and (
                program.result_width == 0
                or (program.result_layout is not None and all(bit is None for bit in program.result_layout.bits))
            )
            for program in programs
        ):
            msg = "At least one measured output is required."
            raise CircuitValidationError(msg)
        return super().run(run_input, parameter_values, **options)
