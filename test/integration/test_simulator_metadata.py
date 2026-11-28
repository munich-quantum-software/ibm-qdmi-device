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

"""Exercise installed QDMI metadata against Simulated Quantum Resource."""

from __future__ import annotations

import ctypes
from functools import partial
from typing import TYPE_CHECKING

import pytest
from metadata_checks import check, number, read, text, validate_snapshot

if TYPE_CHECKING:
    from pathlib import Path

    from native_support import Native

pytestmark = [pytest.mark.integration, pytest.mark.simulator]


@pytest.fixture
def simulator_parameters(pytestconfig: pytest.Config, simulator_storage_file: Path) -> dict[int, str]:
    """Configure explicit simulator endpoints and synthetic IAM credentials.

    Returns:
        Native session parameters that never fall back to IBM Cloud.
    """
    url = pytestconfig.getoption("simulator_url")
    return {
        0: url,
        1: "synthetic-key",
        3: url + "/identity/token",
        999999995: "fake_lagos",
        999999996: "crn:v1:local:qsa_sim",
        999999997: "5000",
        999999998: "quantum-system",
        999999999: str(simulator_storage_file),
    }


def test_simulator_metadata(native: Native, simulator_parameters: dict[int, str]) -> None:
    """Real IAM and backend responses satisfy the QDMI snapshot contracts."""
    with native.session(simulator_parameters) as session:
        check(native.init(session), "simulator session initialization")
        validate_snapshot(native, session, "fake_lagos", 7)
        for site in native.handles(session, 5):
            raw = read(partial(native.site, session, site, 1), "simulator T1")
            assert raw is not None
            assert ctypes.c_uint64.from_buffer_copy(raw).value > 0
        signatures = {}
        for operation in native.handles(session, 6):
            query = partial(native.operation, session, operation, 0, None, 0, None)
            signatures[text(partial(query, 0), "operation name")] = query
        assert number(partial(signatures["rz"], 1), "rz arity") == 1
        assert number(partial(signatures["rz"], 2), "rz parameter count") == 1


def test_simulator_rejects_invalid_api_key(native: Native, simulator_parameters: dict[int, str]) -> None:
    """The simulator's IAM rejection maps to QDMI permission denied."""
    with native.session({**simulator_parameters, 1: "invalid-synthetic-key"}) as session:
        assert native.init(session) == -8


def test_simulator_sampling_and_retrieval(native: Native, simulator_parameters: dict[int, str]) -> None:
    """Run a batch through S3 and retrieve it from an independent native session."""
    sources = [
        (
            b'OPENQASM 3; include "stdgates.inc"; qubit[7] q; bit[2] b; bit[1] a; '
            b"rz(pi/2) q[0]; sx q[0]; rz(pi/2) q[0]; cx q[0],q[1]; "
            b"b[0]=measure q[0]; b[1]=measure q[1]; a[0]=measure q[2];"
        ),
        (
            b'OPENQASM 3; include "stdgates.inc"; qubit[7] q; bit[2] b; bit[1] a; '
            b"x q[1]; b[0]=measure q[1]; b[1]=measure q[0]; a[0]=measure q[2];"
        ),
    ]
    with native.session(simulator_parameters) as session:
        check(native.init(session), "simulator initialization")
        with native.job(session) as job:
            buffers = [ctypes.create_string_buffer(source) for source in sources]
            sizes = (ctypes.c_size_t * 2)(*(len(buffer) for buffer in buffers))
            programs = (ctypes.c_void_p * 2)(*(ctypes.cast(buffer, ctypes.c_void_p) for buffer in buffers))
            check(native.set_programs(job, 1, 2, sizes, programs), "programs")
            shots = ctypes.c_size_t(64)
            check(native.job_set(job, 2, ctypes.sizeof(shots), ctypes.byref(shots)), "shots")
            check(native.submit(job), "submission")
            check(native.wait(job, 120000), "execution")
            identifier = text(partial(native.job_property, job, 0), "job ID")
            expected = []
            for index in range(2):
                samples = text(partial(native.results, job, index, 0), "samples")
                assert samples is not None
                values = samples.split(",")
                assert len(values) == 64
                assert all(len(value) == 3 and set(value) <= {"0", "1"} for value in values)
                expected.append(samples)
            assert set(expected[0].split(",")) <= {"000", "011"}
            assert set(expected[1].split(",")) == {"001"}
        assert identifier is not None
        with native.session(simulator_parameters) as fresh:
            check(native.init(fresh), "fresh initialization")
            retrieved = ctypes.c_void_p()
            check(native.retrieve_job(fresh, identifier.encode(), ctypes.byref(retrieved)), "retrieval")
            try:
                for index, samples in enumerate(expected):
                    assert text(partial(native.results, retrieved, index, 0), "retrieved samples") == samples
            finally:
                native.job_free(retrieved)
