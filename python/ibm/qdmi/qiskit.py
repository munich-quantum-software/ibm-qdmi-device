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

import json
from copy import copy, deepcopy
from math import isfinite, ulp
from typing import TYPE_CHECKING, Any

try:
    from mqt.core.mlir import CompiledProgram
    from mqt.core.plugins.qiskit.backend import QDMIBackend
    from mqt.core.plugins.qiskit.exceptions import CircuitValidationError
    from mqt.core.qdmi.builtin_driver import open_device
except ImportError as error:
    msg = "Install 'ibm-qdmi[qiskit]' to use IBMBackend."
    raise ImportError(msg) from error

from mqt.core.qdmi import CustomProperty
from qiskit.circuit import Delay, Parameter, QuantumCircuit

from . import IBM_QDMI_DEVICE_ID
from ._session import session_parameters

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from mqt.core.plugins.qiskit.backend import ParametersType
    from mqt.core.plugins.qiskit.job import QDMIJob
    from mqt.core.plugins.qiskit.provider import QDMIProvider
    from mqt.core.qdmi import Device
    from qiskit.transpiler import Target
    from qiskit_ibm_runtime.options_models.estimator import EstimatorOptions
    from qiskit_ibm_runtime.options_models.executor import ExecutorOptions
    from qiskit_ibm_runtime.options_models.sampler import SamplerOptions

    from .executor import Executor, ExecutorEstimator, ExecutorSampler

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

    def _build_target(self) -> Target:
        """Add IBM timing to the target built from the shared device snapshot.

        Returns:
            The target with the available IBM timing information.
        """
        target = super()._build_target()
        self._executor_supports_delay = False
        raw = self.device.query_custom_property(CustomProperty.CUSTOM4, str)
        if raw is None:
            return target
        try:
            timing = json.loads(raw)
        except ValueError:
            return target
        if not isinstance(timing, dict) or timing.get("schema") != "ibm.timing.v1":
            return target
        dt = timing.get("dt")
        if not isinstance(dt, float) or not 0 < dt < float("inf"):
            return target
        keys = ("granularity", "min_length", "pulse_alignment", "acquire_alignment")
        constraints = [timing.get(key, getattr(target, key)) for key in keys]
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and 0 < value < 2**32 for value in constraints
        ):
            return target
        self._executor_supports_delay = timing.get("supports_delay") is True
        target.dt = dt
        target.granularity, target.min_length, target.pulse_alignment, target.acquire_alignment = constraints
        return target

    def _executor_dd_backend(self) -> IBMBackend:
        """Give Runtime a scheduling target with Executor's delay support.

        Returns:
            A backend view for client-side scheduling.

        Raises:
            ValueError: The backend lacks valid timing or delay support.
        """
        dt = self.target.dt
        if dt is None:
            msg = "Executor dynamical decoupling requires valid timing, including the sampling interval (dt)."
            raise ValueError(msg)
        if not self._executor_supports_delay:
            msg = "Executor dynamical decoupling requires backend support for delay instructions."
            raise ValueError(msg)
        backend = copy(self)
        backend._target = deepcopy(self.target)  # ruff: ignore[private-member-access] -- Preserve the original target.
        target = backend.target
        # QDMI rounds calibrated durations to whole picoseconds. A tick can be
        # recovered unambiguously only if adjacent ticks are more than 1 ps apart.
        if dt > 1e-12:
            for name in target.operation_names:
                for sites, properties in target[name].items():
                    if properties is None or properties.duration is None:
                        continue
                    duration = properties.duration
                    ticks = duration / dt
                    if not isfinite(ticks) or ticks < 0:
                        continue
                    nearest = round(ticks) * dt
                    difference = abs(nearest - duration)
                    # Include floating-point error at the half-picosecond cutoff.
                    tolerance = 0.5e-12 + ulp(duration) + ulp(nearest)
                    if 0 < difference <= tolerance and difference < dt / 2:
                        normalized = copy(properties)
                        normalized.duration = nearest
                        target.update_instruction_properties(name, sites, normalized)
        if "delay" not in target.operation_names:
            target.add_instruction(Delay(Parameter("duration")), {(site,): None for site in self._placeable_sites})
        return backend

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
        from ibm.qdmi.executor import Executor

        return Executor(self, options=options)

    def executor_sampler(self, *, options: SamplerOptions | dict[str, object] | None = None) -> ExecutorSampler:
        """Create the IBM Runtime Sampler using this QDMI session.

        Returns:
            An Executor-backed Sampler requiring the ``ibm-qdmi[executor]`` extra.
        """
        from ibm.qdmi.executor import ExecutorSampler

        return ExecutorSampler(self, options=options)

    def executor_estimator(self, *, options: EstimatorOptions | dict[str, object] | None = None) -> ExecutorEstimator:
        """Create the IBM Runtime Estimator using this QDMI session.

        Returns:
            An Executor-backed Estimator requiring the ``ibm-qdmi[executor]`` extra.
        """
        from ibm.qdmi.executor import ExecutorEstimator

        return ExecutorEstimator(self, options=options)

    def run(
        self,
        run_input: QuantumCircuit | CompiledProgram | Iterable[QuantumCircuit | CompiledProgram],
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
        programs = [run_input] if isinstance(run_input, (QuantumCircuit, CompiledProgram)) else list(run_input)
        # IBM Sampler requires classical output storage.
        if any(isinstance(program, CompiledProgram) and program.result_width == 0 for program in programs):
            msg = "At least one measured output is required."
            raise CircuitValidationError(msg)
        return super().run(programs, parameter_values, **options)
