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

"""Offline checks for the public runnable examples."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pennylane as qml
import pytest
from examples import native_job, pennylane_qaoa, qiskit_workloads
from mqt.core.plugins.qiskit.backend import QDMIBackend
from offline_service import CRN
from qiskit_service import remote_runtime

from ibm.qdmi.pennylane import IBMDevice
from ibm.qdmi.qiskit import IBMBackend

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(params=["sim", "ibm"])
def backend(request: pytest.FixtureRequest) -> Iterator[QDMIBackend]:
    """Open a local simulator or the IBM library against loopback HTTP.

    Yields:
        A QDMI-backed Qiskit backend with no live access.
    """
    if request.param == "sim":
        yield QDMIBackend.from_device_id("mqt.ddsim.default")
        return
    with remote_runtime() as runtime:
        url = runtime.snapshot()["url"]
        yield IBMBackend(
            api_key="synthetic-key", instance_crn=CRN, backend_name="ibm_test", base_url=url, auth_url=url + "/auth"
        )


def test_native_job(backend: QDMIBackend) -> None:
    """Direct QDMI submission returns the measured X state."""
    width = backend.num_qubits if isinstance(backend, IBMBackend) else 1
    assert native_job.run(backend.device, 17, qubits=width) == {"1": 17}


def test_bell_sampler(backend: QDMIBackend) -> None:
    """The sampler preserves Bell correlations and the requested shots."""
    counts = qiskit_workloads.sample_bell(backend, 64)
    assert sum(counts.values()) == 64
    assert set(counts) <= {"00", "11"}


def test_benchmark(backend: QDMIBackend) -> None:
    """The mapped benchmark preserves the three-qubit GHZ correlations."""
    counts = qiskit_workloads.benchmark(backend, 64)
    assert sum(counts.values()) == 64
    assert set(counts) <= {"000", "111"}


def test_h2(backend: QDMIBackend) -> None:
    """The estimator returns a finite energy in the Hamiltonian's bounds."""
    energy = qiskit_workloads.estimate_h2(backend, 128)
    assert math.isfinite(energy)
    assert -2.1 < energy < 0.1


def test_qaoa(backend: QDMIBackend) -> None:
    """One QAOA layer produces a bounded objective and finite-shot counts."""
    device = (
        IBMDevice(device=backend.device, wires=2)
        if isinstance(backend, IBMBackend)
        else qml.device("mqt.ddsim.default", wires=2)
    )
    value, counts = pennylane_qaoa.run(device, 64)
    assert 0 <= value <= 1
    assert sum(counts.values()) == 64
    assert set(counts) <= {"00", "01", "10", "11"}
