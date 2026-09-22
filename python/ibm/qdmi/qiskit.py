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

import math
import os
from typing import TYPE_CHECKING, Any

try:
    from mqt.core.plugins.qiskit.backend import QDMIBackend
    from mqt.core.plugins.qiskit.exceptions import CircuitValidationError, UnsupportedOperationError
    from mqt.core.qdmi import Device, ProgramFormat
    from mqt.core.qdmi.driver import open_device
except ImportError as error:
    msg = "Install 'ibm-qdmi[qiskit]' to use IBMBackend."
    raise ImportError(msg) from error

from qiskit.circuit import Barrier, ControlFlowOp, QuantumCircuit

from . import IBM_QDMI_DEVICE_ID
from ._catalogue import register_device
from .serializers import qiskit_to_qasm3

if TYPE_CHECKING:
    from collections.abc import Iterable, MutableSet, Sequence

    from mqt.core.plugins.qiskit.backend import ParametersType
    from mqt.core.plugins.qiskit.job import QDMIJob
    from mqt.core.plugins.qiskit.provider import QDMIProvider
    from qiskit.transpiler import Target

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
        selected_backend = backend_name
        if resolved_id == IBM_QDMI_DEVICE_ID and selected_backend is None:
            selected_backend = os.environ.get("IBM_QUANTUM_BACKEND")
        register_device(resolved_id)
        device = open_device(
            resolved_id,
            token=api_key if api_key is not None else os.environ.get("IBM_QUANTUM_API_KEY"),
            custom2=instance_crn if instance_crn is not None else os.environ.get("IBM_QUANTUM_INSTANCE_CRN"),
            custom1=selected_backend,
            base_url=base_url,
            auth_url=auth_url,
        )
        super().__init__(device=device, provider=provider, device_id=resolved_id)

    def _add_operation_to_target(self, target: Target, op: Device.Operation, seen_gate_names: MutableSet[str]) -> None:
        """Keep unsupported or incomplete operation signatures out of the target."""
        gate = self._map_operation_to_gate(op.name())
        arity = op.qubits_num()
        if gate is None or isinstance(gate, type) or arity not in {1, 2}:
            return
        if (arity == 1 and not op.sites()) or (arity == 2 and not op.site_pairs()):
            return
        if gate.num_qubits != arity or len(gate.params) != op.parameters_num():
            return
        super()._add_operation_to_target(target, op, seen_gate_names)

    def _build_target(self) -> Target:
        """Build the metadata target and add the barrier directive.

        Returns:
            The device target, with durations in seconds.
        """
        target = super()._build_target()
        target.add_instruction(Barrier, name="barrier")
        return target

    def _preprocess_circuit(self, circuit: QuantumCircuit) -> QuantumCircuit:
        """Validate bound instructions before any circuit in a batch is submitted.

        Returns:
            The unchanged circuit, preserving physical and classical indices.

        Raises:
            mqt.core.plugins.qiskit.exceptions.CircuitValidationError:
                Measurements or finite parameters are missing.
            UnsupportedOperationError: An instruction or site tuple is unsupported.
        """
        if circuit.num_qubits > self.num_qubits or not circuit.num_clbits:
            msg = "A circuit must fit the physical device and contain classical measurements."
            raise CircuitValidationError(msg)
        measured = False
        for instruction in circuit.data:
            operation = instruction.operation
            qargs = tuple(circuit.find_bit(bit).index for bit in instruction.qubits)
            if isinstance(operation, ControlFlowOp) or not self.target.instruction_supported(
                operation_name=operation.name, qargs=qargs, parameters=operation.params
            ):
                msg = "An instruction or physical site tuple is unsupported; transpile against this backend."
                raise UnsupportedOperationError(msg)
            if any(not math.isfinite(float(value)) for value in operation.params):
                msg = "Gate parameters must be finite real numbers."
                raise CircuitValidationError(msg)
            measured |= operation.name == "measure"
        if not measured:
            msg = "At least one measurement is required."
            raise CircuitValidationError(msg)
        return circuit

    def _serialize_circuit(
        self, circuit: QuantumCircuit, supported_program_formats: Iterable[ProgramFormat]
    ) -> tuple[str, ProgramFormat]:
        """Serialize with a full physical register and the original classical order.

        Returns:
            IBM-compatible OpenQASM 3 and its QDMI format.
        """
        assert ProgramFormat.QASM3 in supported_program_formats
        return qiskit_to_qasm3(circuit, self.num_qubits), ProgramFormat.QASM3

    def run(
        self,
        run_input: QuantumCircuit | Sequence[QuantumCircuit],
        parameter_values: Sequence[ParametersType] | None = None,
        **options: Any,  # ruff: ignore[any-type]
    ) -> QDMIJob:
        """Submit validated circuits through the shared job and result adapter.

        Returns:
            MQT Core's QDMI job, with one native job per circuit.

        Raises:
            mqt.core.plugins.qiskit.exceptions.CircuitValidationError:
                The requested shot count is zero.
        """
        if options.get("shots", self.options.shots) == 0:
            msg = "shots must be positive."
            raise CircuitValidationError(msg)
        return super().run(run_input, parameter_values, **options)
