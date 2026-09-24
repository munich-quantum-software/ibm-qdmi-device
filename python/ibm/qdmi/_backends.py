# Copyright (c) 2025 - 2026 IQM Finland Oy
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

"""Shared backend/primitive construction for the offloader and its Slurm CLI workers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mqt.core.plugins.qiskit.backend import QDMIBackend

from ibm.qdmi.qiskit import IBMBackend

if TYPE_CHECKING:
    from qiskit.primitives import BackendEstimatorV2, BackendSamplerV2

_SIMULATOR_DEVICE_ID = "mqt.ddsim.default"

#: Optimization level used whenever a circuit is transpiled for execution
#: (offloader local path and the `ibm-sampler` Slurm worker), so the two
#: paths stay in sync instead of drifting to different Qiskit defaults.
TRANSPILE_OPTIMIZATION_LEVEL = 2


def build_sampler(
    *,
    simulator: bool,
    backend_name: str | None = None,
) -> BackendSamplerV2:
    """Build the Sampler primitive to use for a sampling job.

    Returns:
        A Sampler primitive bound to the resolved backend, which it exposes as
        its `backend` property.
    """
    if simulator:
        return QDMIBackend.from_device_id(_SIMULATOR_DEVICE_ID).sampler()

    backend = IBMBackend(backend_name=backend_name)
    return backend.sampler()


def build_estimator(
    *,
    simulator: bool,
    backend_name: str | None = None,
) -> BackendEstimatorV2:
    """Build the Estimator primitive to use for a VQE estimation job.

    Returns:
        An Estimator primitive bound to the resolved backend, which it exposes
        as its `backend` property.
    """
    if simulator:
        return QDMIBackend.from_device_id(_SIMULATOR_DEVICE_ID).estimator()

    backend = IBMBackend(backend_name=backend_name)
    return backend.estimator()
