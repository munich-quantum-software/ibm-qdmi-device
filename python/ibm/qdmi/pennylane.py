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

"""PennyLane execution through the native IBM QDMI device."""

from __future__ import annotations

import math
from functools import partial
from typing import TYPE_CHECKING, ClassVar

try:
    import pennylane as qml
    from mqt.core.plugins.pennylane import PennyLaneConfigurationError
    from mqt.core.plugins.pennylane.device import QDMIDevice
    from qiskit.circuit import QuantumCircuit
    from qiskit.circuit.library import get_standard_gate_name_mapping
except ImportError as error:
    msg = "Install 'ibm-qdmi[pennylane]' to use IBMDevice."
    raise ImportError(msg) from error

# Core 4 pins this converter contract; reuse validation and sample metadata.
from mqt.core.plugins.pennylane.converter import _ProgramConverter  # ruff: ignore[import-private-name]
from pennylane import CompilePipeline
from pennylane.devices.preprocess import decompose
from pennylane.transforms.core import BoundTransform

from . import IBM_QDMI_DEVICE_ID
from ._catalogue import register_device, session_parameters
from .serializers import qiskit_to_qasm3

if TYPE_CHECKING:
    from collections.abc import Hashable, Sequence

    from mqt.core.plugins.pennylane.converter import _ConvertedProgram
    from mqt.core.qdmi import Device
    from mqt.core.typing import QDMIJobParameters
    from pennylane.devices import ExecutionConfig
    from pennylane.operation import Operator
    from pennylane.tape import QuantumScript
    from pennylane.wires import Wires

__all__ = ["IBMAachenDevice", "IBMBerlinDevice", "IBMDevice"]


def _decompose_operation(operation: Operator, *, target_gates: set[str]) -> Sequence[Operator]:
    """Express rotations and CNOT in the native basis without losing derivatives.

    Returns:
        Equivalent operations up to an unobservable global phase.
    """
    if isinstance(operation, qml.CNOT):
        control, target = operation.wires
        if "CZ" in target_gates:
            return [qml.Hadamard(target), qml.CZ(operation.wires), qml.Hadamard(target)]
        if "ECR" in target_gates:
            return [
                qml.RZ(-math.pi / 2, control),
                qml.RX(-math.pi / 2, target),
                qml.ECR(operation.wires),
                qml.X(control),
            ]
    if isinstance(operation, qml.operation.Operation) and len(operation.wires) == 1:
        try:
            phi, theta, omega = operation.single_qubit_rot_angles()
        except NotImplementedError:
            pass
        else:
            return [
                qml.RZ(phi, operation.wires),
                qml.SX(wires=operation.wires),
                qml.RZ(theta + math.pi, operation.wires),
                qml.SX(wires=operation.wires),
                qml.RZ(omega + math.pi, operation.wires),
            ]
    return operation.decomposition()


def _fold_rzz_angle(angle: float, wires: Wires) -> Sequence[Operator]:
    """Fold a bound RZZ into IBM's calibrated interval up to global phase.

    Returns:
        Equivalent operations with any RZZ angle in (0, pi/2].
    """
    angle = math.remainder(angle, 2 * math.pi)
    operations: list[Operator] = []
    if abs(angle) > math.pi / 2:
        # A pi shift contributes Z on each wire, up to global phase.
        angle -= math.copysign(math.pi, angle)
        operations.extend(qml.RZ(math.pi, wire) for wire in wires)
    if angle < 0:
        operations.append(qml.X(wires[0]))
    if angle != 0:
        operations.append(qml.IsingZZ(abs(angle), wires))
    if angle < 0:
        operations.append(qml.X(wires[0]))
    return operations


class _IBMProgramConverter(_ProgramConverter):
    """Keep Core's validation and decoding with IBM's physical QASM layout."""

    def _convert_qasm3(self, tape: QuantumScript) -> _ConvertedProgram:
        """Serialize native gates and indexed measurements for exposed wires.

        Returns:
            IBM-compatible OpenQASM with Core's measurement metadata.
        """
        circuit = QuantumCircuit(len(self._device_wires), len(self._device_wires))
        gates = get_standard_gate_name_mapping()
        for operation in tape.operations:
            operations: Sequence[Operator] = [operation]
            if isinstance(operation, qml.IsingZZ):
                _, _, parameters = self._prepare_operation(operation)
                # Fold only bound execution parameters, after gradient transforms.
                operations = _fold_rzz_angle(parameters[0], operation.wires)
            for native_operation in operations:
                spelling, indices, parameters = self._prepare_operation(native_operation)
                gate = gates[spelling].to_mutable()
                gate.params = list(parameters)
                circuit.append(gate, indices)
        circuit.measure(range(len(self._device_wires)), range(len(self._device_wires)))
        return self._program(tape, qiskit_to_qasm3(circuit, self._device.qubits_num()))


class IBMDevice(QDMIDevice):
    """Run finite-shot PennyLane programs on IBM Quantum Platform.

    Args:
        wires: Wire labels or number of wires. Labels map in order to physical
            qubits starting at zero. By default expose all backend qubits.
        device_id: Catalogue ID; defaults to the entry point's stable IBM ID.
        device: An already-open device, exclusive with connection overrides.
        backend_name: Backend override; otherwise use environment or catalogue defaults.
        api_key: IBM Cloud API key; defaults to ``IBM_QUANTUM_API_KEY``.
        instance_crn: Instance CRN; defaults to ``IBM_QUANTUM_INSTANCE_CRN``.
        base_url: Trusted API endpoint override, principally for loopback tests.
        auth_url: Trusted IAM endpoint override, principally for loopback tests.
        job_parameters: Native QDMI custom job parameters.
    """

    qdmi_device_id: ClassVar[str] = IBM_QDMI_DEVICE_ID

    def __init__(
        self,
        wires: int | Sequence[Hashable] | None = None,
        *,
        device_id: str | None = None,
        device: Device | None = None,
        backend_name: str | None = None,
        api_key: str | None = None,
        instance_crn: str | None = None,
        base_url: str | None = None,
        auth_url: str | None = None,
        job_parameters: QDMIJobParameters | None = None,
    ) -> None:
        """Open the selected session and specialize its program converter.

        Raises:
            PennyLaneConfigurationError: An open device conflicts with connection overrides.
        """
        if device is not None:
            if any(value is not None for value in (device_id, backend_name, api_key, instance_crn, base_url, auth_url)):
                msg = "An already-open device is exclusive with connection overrides."
                raise PennyLaneConfigurationError(msg)
            super().__init__(device=device, wires=wires, job_parameters=job_parameters)
        else:
            selected_id = self.qdmi_device_id if device_id is None else device_id
            register_device(selected_id)
            session = session_parameters(
                selected_id,
                backend_name=backend_name,
                api_key=api_key,
                instance_crn=instance_crn,
                base_url=base_url,
                auth_url=auth_url,
            )
            super().__init__(selected_id, wires=wires, session_parameters=session, job_parameters=job_parameters)
        self._converter = _IBMProgramConverter(self.qdmi_device, self.wires, self._program_format)

    def preprocess_transforms(self, execution_config: ExecutionConfig | None = None) -> CompilePipeline:
        """Extend Core's decomposition for IBM's native basis.

        Returns:
            Core's preprocessing pipeline with differentiable native synthesis.
        """
        pipeline = super().preprocess_transforms(execution_config)
        if not {"SX", "RZ"} <= self._converter.target_gates:
            return pipeline
        decomposer = partial(_decompose_operation, target_gates=self._converter.target_gates)
        return CompilePipeline([
            BoundTransform(decompose, transform.args, {**transform.kwargs, "decomposer": decomposer})
            if transform.tape_transform is decompose.tape_transform
            else transform
            for transform in pipeline
        ])


class IBMBerlinDevice(IBMDevice):
    """PennyLane entry point for the packaged Berlin backend."""

    qdmi_device_id = "ibm.berlin"


class IBMAachenDevice(IBMDevice):
    """PennyLane entry point for the packaged Aachen backend."""

    qdmi_device_id = "ibm.aachen"
