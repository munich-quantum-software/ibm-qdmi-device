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

from typing import TYPE_CHECKING, ClassVar

try:
    from mqt.core.mlir import TerminalReadout
    from mqt.core.plugins.pennylane import PennyLaneConfigurationError
    from mqt.core.plugins.pennylane.device import QDMIDevice
    from mqt.core.qdmi import ProgramFormat
except ImportError as error:
    msg = "Install 'ibm-qdmi[pennylane]' to use IBMDevice."
    raise ImportError(msg) from error

from . import IBM_QDMI_DEVICE_ID
from ._catalogue import session_parameters

if TYPE_CHECKING:
    from collections.abc import Hashable, Sequence

    from mqt.core.qdmi import Device
    from mqt.core.typing import QDMIJobParameters

__all__ = ["IBMAachenDevice", "IBMBerlinDevice", "IBMDevice"]


class IBMDevice(QDMIDevice):
    """Run finite-shot PennyLane programs on IBM Quantum Platform.

    Args:
        wires: Logical wire labels or number of wires. Core selects physical
            qubits during compilation. By default expose all backend qubits.
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
        """Open the selected IBM session.

        Raises:
            PennyLaneConfigurationError: An open device conflicts with connection overrides.
        """
        if device is not None:
            if any(value is not None for value in (device_id, backend_name, api_key, instance_crn, base_url, auth_url)):
                msg = "An already-open device is exclusive with connection overrides."
                raise PennyLaneConfigurationError(msg)
            super().__init__(
                device=device,
                wires=wires,
                job_parameters=job_parameters,
                program_format=ProgramFormat.QASM3,
                terminal_readout=TerminalReadout.MEASURED,
            )
        else:
            selected_id = self.qdmi_device_id if device_id is None else device_id
            session = session_parameters(
                device_id=selected_id,
                backend_name=backend_name,
                api_key=api_key,
                instance_crn=instance_crn,
                base_url=base_url,
                auth_url=auth_url,
            )
            super().__init__(
                selected_id,
                wires=wires,
                session_parameters=session,
                job_parameters=job_parameters,
                program_format=ProgramFormat.QASM3,
                terminal_readout=TerminalReadout.MEASURED,
            )


class IBMBerlinDevice(IBMDevice):
    """PennyLane entry point for the packaged Berlin backend."""

    qdmi_device_id = "ibm.berlin"


class IBMAachenDevice(IBMDevice):
    """PennyLane entry point for the packaged Aachen backend."""

    qdmi_device_id = "ibm.aachen"
