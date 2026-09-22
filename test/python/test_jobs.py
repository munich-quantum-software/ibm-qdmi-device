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

"""Job lifecycle and result contracts through the installed C ABI."""

from __future__ import annotations

import ctypes
import json
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from native_support import Native
    from offline_service import Service

PROGRAM = b"OPENQASM 3; qubit[2] q; bit[2] z; bit a; z[0] = measure q[1]; a = measure q[0];"


def configure(native: Native, job: ctypes.c_void_p) -> None:
    """Configure one static three-shot job."""
    fmt = ctypes.c_int(1)
    shots = ctypes.c_size_t(3)
    assert native.job_set(job, 0, ctypes.sizeof(fmt), ctypes.byref(fmt)) == 0
    assert native.job_set(job, 1, len(PROGRAM) + 1, PROGRAM) == 0
    assert native.job_set(job, 2, ctypes.sizeof(shots), ctypes.byref(shots)) == 0


@pytest.fixture
def job_service(service: Service) -> Service:
    """Supply synthetic submission, status, and result responses.

    Returns:
        The configured offline service.
    """
    service.data.update({
        "jobs": {"id": "synthetic-job", "backend": "ibm_test"},
        "synthetic-job": {
            "id": "synthetic-job",
            "backend": "ibm_test",
            "program": {"id": "sampler"},
            "state": {"status": "Completed"},
            "params": {"version": 2, "support_qiskit": False, "pubs": [[PROGRAM.decode(), None, 3]]},
        },
        "results": {
            "results": [
                {
                    "data": {
                        "z": {"num_bits": 2, "samples": ["0x1", "0x0", "0x1"]},
                        "a": {"num_bits": 1, "samples": ["0x1", "0x0", "0x1"]},
                    }
                }
            ],
        },
    })
    return service


def test_job_lifecycle_and_retrieval(native: Native, job_service: Service) -> None:
    """Exercise symbols, size queries, result caching, and read-only retrieval."""
    with native.session(job_service.parameters) as session:
        assert native.init(session) == 0
        with native.job(session) as job:
            assert native.submit(job) == -10
            for prop in (0, 1, 2):
                assert native.job_property(job, prop, 0, None, None) == -10
            assert native.job_property(job, 999999995, 0, None, None) == -9
            assert native.results(job, 0, 0, None, None) == -7
            configure(native, job)
            assert native.submit(job) == 0
            assert native.submit(job) == -10
            assert native.job_set(job, 2, 0, None) == -10
            status = ctypes.c_int()
            assert native.job_check(job, ctypes.byref(status)) == 0
            assert status.value == 4
            assert native.wait(job, 1) == 0
            assert native.cancel(job) == -7
            required = ctypes.c_size_t()
            assert native.results(job, 0, 0, None, ctypes.byref(required)) == 0
            assert required.value == len("101,000,101") + 1
            buffer = ctypes.create_string_buffer(required.value)
            assert native.results(job, 0, 1, buffer, None) == -7
            assert native.results(job, 0, len(buffer), buffer, None) == 0
            assert buffer.value == b"101,000,101"
            assert native.results(job, 1, len(buffer), buffer, None) == 0
            assert buffer.value == b"000,101"
            counts = (ctypes.c_size_t * 2)()
            assert native.results(job, 2, ctypes.sizeof(counts), counts, None) == 0
            assert list(counts) == [1, 2]
            assert native.results(job, 3, 0, None, None) == -9
            assert sum(path.endswith("/results") for path, _, _ in job_service.requests) == 1
            retrieved = ctypes.c_void_p()
            assert native.retrieve_job(session, b"synthetic-job", ctypes.byref(retrieved)) == 0
            try:
                assert native.submit(retrieved) == -10
                assert native.results(retrieved, 0, len(buffer), buffer, None) == 0
                assert buffer.value == b"101,000,101"
            finally:
                native.job_free(retrieved)
    submissions = [json.loads(body) for path, _, body in job_service.requests if path == "/v1/jobs"]
    assert len(submissions) == 1
    assert submissions[0]["cost"] == 60
    assert submissions[0]["params"]["pubs"][0] == [PROGRAM.decode(), None, 3]


def test_job_retains_session_and_validates_handles(native: Native, job_service: Service) -> None:
    """Freeing a session leaves its jobs usable and never cancels remotely."""
    job = ctypes.c_void_p()
    with native.session(job_service.parameters) as session:
        assert native.create_job(session, ctypes.byref(job)) == -10
        assert native.init(session) == 0
        assert native.create_job(session, None) == -7
        assert native.create_job(session, ctypes.byref(job)) == 0
    try:
        configure(native, job)
        assert native.submit(job) == 0
        assert native.wait(job, 1) == 0
        assert native.finalize() == -1
        assert native.job_check(job, None) == -7
        assert native.submit(ctypes.c_void_p(1)) == -7
        assert native.results(job, -1, 0, None, None) == -7
    finally:
        native.job_free(job)
    assert native.submit(job) == -7
    native.job_free(job)
    assert all(not path.endswith("/cancel") for path, _, _ in job_service.requests)


def test_configuration_validation(native: Native, job_service: Service) -> None:
    """Reject invalid values without changing valid configuration."""
    with native.session(job_service.parameters) as session:
        assert native.init(session) == 0
        with native.job(session) as job:
            nonnull = ctypes.c_size_t(1)
            for parameter in (0, 1, 2, 999999995, 999999996):
                assert native.job_set(job, parameter, 0, ctypes.byref(nonnull)) == -7
            assert native.job_set(job, 999999995, 0, None) == 0
            assert native.job_set(job, 999999996, 0, None) == -9
            assert native.job_set(job, -1, 0, None) == -7
            for value in (0, 10801):
                seconds = ctypes.c_uint64(value)
                assert native.job_set(job, 999999995, 8, ctypes.byref(seconds)) == -7
            seconds = ctypes.c_uint64(42)
            assert native.job_set(job, 999999995, 1, ctypes.byref(seconds)) == -7
            assert native.job_set(job, 999999995, 8, ctypes.byref(seconds)) == 0
            zero = ctypes.c_size_t(0)
            assert native.job_set(job, 2, ctypes.sizeof(zero), ctypes.byref(zero)) == -7
            fmt = ctypes.c_int(0)
            assert native.job_set(job, 0, ctypes.sizeof(fmt), ctypes.byref(fmt)) == -9
            configure(native, job)
            assert native.job_set(job, 1, len(PROGRAM), PROGRAM) == -7
            assert native.submit(job) == 0
    submitted = next(json.loads(body) for path, _, body in job_service.requests if path == "/v1/jobs")
    assert submitted["cost"] == 42


@pytest.mark.parametrize("failure", [401, 403, 500])
def test_failed_submission_is_not_retried(native: Native, job_service: Service, failure: int) -> None:
    """HTTP failure freezes a handle and cannot submit a duplicate job."""
    job_service.errors["jobs"] = failure
    with native.session(job_service.parameters) as session:
        assert native.init(session) == 0
        with native.job(session) as job:
            configure(native, job)
            assert native.submit(job) == (-8 if failure in {401, 403} else -1)
            assert native.submit(job) == -10
            assert native.wait(job, 1) == -1
    assert sum(path == "/v1/jobs" for path, _, _ in job_service.requests) == 1


def test_wait_timeout_and_cancellation(native: Native, job_service: Service) -> None:
    """Timeout leaves the job queued; cancellation is an explicit request."""
    job_service.data["synthetic-job"]["state"]["status"] = "Queued"
    job_service.errors["cancel"] = 204
    with native.session(job_service.parameters) as session:
        assert native.init(session) == 0
        with native.job(session) as job:
            configure(native, job)
            assert native.wait(job, 1) == -10
            assert native.submit(job) == 0
            assert native.results(job, 0, 0, None, None) == -7
            started = time.monotonic()
            assert native.wait(job, 1) == -11
            assert time.monotonic() - started < 2
            assert all(not path.endswith("/cancel") for path, _, _ in job_service.requests)
            assert native.cancel(job) == 0
            assert native.wait(job, 1) == 0
            assert native.results(job, 0, 0, None, None) == -7


def test_request_timeout_does_not_retry_submission(native: Native, job_service: Service) -> None:
    """The session's HTTP timeout bounds a submission and freezes its handle."""

    def delayed_submission(_path: str, _body: bytes) -> tuple[int, dict[str, str]]:
        time.sleep(1)
        return 200, {"id": "synthetic-job", "backend": "ibm_test"}

    job_service.respond = delayed_submission
    with native.session({**job_service.parameters, 999999997: "200"}) as session:
        assert native.init(session) == 0
        with native.job(session) as job:
            configure(native, job)
            assert native.submit(job) == -11
            assert native.submit(job) == -10
    assert sum(path == "/v1/jobs" for path, _, _ in job_service.requests) == 1


@pytest.mark.parametrize("change", ["backend", "program", "private", "pubs", "encoding"])
def test_retrieval_rejects_incompatible_jobs(native: Native, job_service: Service, change: str) -> None:
    """A failed retrieval publishes no local handle and submits nothing."""
    data = job_service.data["synthetic-job"]
    if change == "backend":
        data["backend"] = "ibm_other"
    elif change == "program":
        data["program"]["id"] = "estimator"
    elif change == "private":
        data["private"] = True
    elif change == "pubs":
        data["params"]["pubs"] *= 2
    else:
        data["params"]["support_qiskit"] = True
    with native.session(job_service.parameters) as session:
        assert native.init(session) == 0
        job = ctypes.c_void_p()
        assert native.retrieve_job(session, b"synthetic-job", ctypes.byref(job)) == (-7 if change == "backend" else -9)
        assert job.value is None
        assert native.retrieve_job(session, b"../escape", ctypes.byref(job)) == -7
    assert all(path != "/v1/jobs" for path, _, _ in job_service.requests)
