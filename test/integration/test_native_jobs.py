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
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pytest

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

    from native_support import Native
    from offline_service import Service

PROGRAM = b"OPENQASM 3; qubit[2] q; bit[2] z; bit a; z[0] = measure q[1]; a = measure q[0];"


def configure(native: Native, job: ctypes.c_void_p) -> None:
    """Configure one static three-shot job."""
    shots = ctypes.c_size_t(3)
    data = ctypes.create_string_buffer(PROGRAM)
    sizes = (ctypes.c_size_t * 1)(len(data))
    programs = (ctypes.c_void_p * 1)(ctypes.cast(data, ctypes.c_void_p))
    assert native.set_programs(job, 1, 1, sizes, programs) == 0
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
            for prop in (0, 1, 5):
                assert native.job_property(job, prop, 0, None, None) == -10
            assert native.job_property(job, 999999995, 0, None, None) == -9
            assert native.results(job, 0, 0, 0, None, None) == -6
            assert native.job_property(job, 2, 0, None, None) == -9
            configure(native, job)
            count = ctypes.c_size_t()
            assert native.job_property(job, 5, ctypes.sizeof(count), ctypes.byref(count), None) == 0
            assert count.value == 1
            assert native.submit(job) == 0
            assert native.submit(job) == -10
            assert native.job_set(job, 2, 0, None) == -10
            status = ctypes.c_int()
            assert native.job_check(job, ctypes.byref(status)) == 0
            assert status.value == 4
            assert native.wait(job, 1) == 0
            assert native.cancel(job) == -7
            required = ctypes.c_size_t()
            assert native.results(job, 0, 0, 0, None, ctypes.byref(required)) == 0
            assert required.value == len("101,000,101") + 1
            buffer = ctypes.create_string_buffer(required.value)
            assert native.results(job, 0, 0, 1, buffer, None) == -7
            assert native.results(job, 0, 0, len(buffer), buffer, None) == 0
            assert buffer.value == b"101,000,101"
            assert native.results(job, 0, 1, len(buffer), buffer, None) == 0
            assert buffer.value == b"000,101"
            counts = (ctypes.c_size_t * 2)()
            assert native.results(job, 0, 2, ctypes.sizeof(counts), counts, None) == 0
            assert list(counts) == [1, 2]
            assert native.results(job, 0, 3, 0, None, None) == -9
            assert sum(path.endswith("/results") for path, _, _ in job_service.requests) == 1
            retrieved = ctypes.c_void_p()
            assert native.retrieve_job(session, b"synthetic-job", ctypes.byref(retrieved)) == 0
            try:
                assert native.submit(retrieved) == -10
                assert native.results(retrieved, 0, 0, len(buffer), buffer, None) == 0
                assert buffer.value == b"101,000,101"
            finally:
                native.job_free(retrieved)
    submissions = [json.loads(body) for path, _, body in job_service.requests if path == "/v1/jobs"]
    assert len(submissions) == 1
    assert submissions[0]["cost"] == 60
    assert submissions[0]["params"]["pubs"][0] == [PROGRAM.decode(), None, 3]


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
            assert native.wait(job, 1) == 0
            status = ctypes.c_int()
            assert native.job_check(job, ctypes.byref(status)) == 0
            assert status.value == 6
            assert native.results(job, 0, 0, 0, None, None) == -10
    assert sum(path == "/v1/jobs" for path, _, _ in job_service.requests) == 1


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


@pytest.mark.parametrize("blocked", ["status", "retrieval", "results"])
def test_independent_session_requests_progress(native: Native, job_service: Service, blocked: str) -> None:
    """Blocked HTTP calls allow independent metadata and job results to proceed."""
    entered = Event()
    release = Event()
    paths = {
        "status": "/v1/backends/ibm_test/status",
        "retrieval": "/v1/jobs/slow-job",
        "results": "/v1/jobs/slow-job/results",
    }
    job_service.data["slow-job"] = {**job_service.data["synthetic-job"], "id": "slow-job"}

    def block(path: str) -> None:
        if path == paths[blocked]:
            entered.set()
            assert release.wait(5)

    with native.session(job_service.parameters) as session:
        assert native.init(session) == 0
        slow = ctypes.c_void_p()
        assert native.retrieve_job(session, b"slow-job", ctypes.byref(slow)) == 0
        retrieved = ctypes.c_void_p()
        try:
            with native.job(session) as fast:
                configure(native, fast)
                assert native.submit(fast) == 0
                job_service.before_respond = block

                def request() -> int:
                    if blocked == "status":
                        return native.device(session, 2, 0, None, None)
                    if blocked == "retrieval":
                        return native.retrieve_job(session, b"slow-job", ctypes.byref(retrieved))
                    return native.results(slow, 0, 0, 0, None, None)

                def independent() -> tuple[int, int]:
                    return native.device(session, 0, 0, None, None), native.results(fast, 0, 0, 0, None, None)

                with ThreadPoolExecutor(max_workers=2) as pool:
                    pending = pool.submit(request)
                    try:
                        assert entered.wait(5)
                        assert pool.submit(independent).result(timeout=2) == (0, 0)
                    finally:
                        release.set()
                    assert pending.result(timeout=5) == 0
        finally:
            native.job_free(slow)
            if retrieved.value is not None:
                native.job_free(retrieved)
    assert sum(path == "/auth" for path, _, _ in job_service.requests) == 1
    assert sum(path == "/v1/jobs/synthetic-job/results" for path, _, _ in job_service.requests) == 1


def test_concurrent_results_share_job_cache(native: Native, job_service: Service) -> None:
    """Concurrent readers of one job make a single result request."""
    with native.session(job_service.parameters) as session:
        assert native.init(session) == 0
        with native.job(session) as job:
            configure(native, job)
            assert native.submit(job) == 0
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: native.results(job, 0, 0, 0, None, None), range(12)))
            assert results == [0] * 12
    assert sum(path.endswith("/results") for path, _, _ in job_service.requests) == 1


def test_wait_deadline_includes_job_lock(native: Native, job_service: Service) -> None:
    """A wait deadline bounds contention with another operation on the same job."""
    entered = Event()
    release = Event()

    def block(path: str) -> None:
        if path.endswith("/results"):
            entered.set()
            assert release.wait(5)

    with native.session(job_service.parameters) as session:
        assert native.init(session) == 0
        with native.job(session) as job:
            configure(native, job)
            assert native.submit(job) == 0
            job_service.before_respond = block
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = pool.submit(native.results, job, 0, 0, 0, None, None)
                try:
                    assert entered.wait(5)
                    assert pool.submit(native.wait, job, 1).result(timeout=2) == -11
                finally:
                    release.set()
                assert pending.result(timeout=5) == 0
            assert native.wait(job, 1) == 0


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
        data["params"]["pubs"][1] = [PROGRAM.decode(), None, 4]
    else:
        data["params"]["support_qiskit"] = True
    with native.session(job_service.parameters) as session:
        assert native.init(session) == 0
        job = ctypes.c_void_p()
        assert native.retrieve_job(session, b"synthetic-job", ctypes.byref(job)) == (-7 if change == "backend" else -9)
        assert job.value is None
        assert native.retrieve_job(session, b"../escape", ctypes.byref(job)) == -7
    assert all(path != "/v1/jobs" for path, _, _ in job_service.requests)


def _storage_signature(url: str, method: str, secret: str) -> str:
    """Compute an independent test-side SigV4 signature with the standard library.

    Returns:
        The signature expected for the supplied method and URL.
    """
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    query.pop("X-Amz-Signature")
    scope = query["X-Amz-Credential"][0].split("/", 1)[1]
    canonical_query = urlencode(sorted((key, value[0]) for key, value in query.items()), quote_via=quote, safe="-_.~")
    canonical = "\n".join([method, parsed.path, canonical_query, f"host:{parsed.netloc}\n", "host", "UNSIGNED-PAYLOAD"])
    to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        query["X-Amz-Date"][0],
        scope,
        hashlib.sha256(canonical.encode()).hexdigest(),
    ])
    signing_key = ("AWS4" + secret).encode()
    for part in scope.split("/"):
        signing_key = hmac.digest(signing_key, part.encode(), "sha256")
    return hmac.digest(signing_key, to_sign.encode(), "sha256").hex()


def test_quantum_system_storage_signatures(native: Native, service: Service, tmp_path: Path) -> None:
    """Check wire PUT, all service signatures, endpoint isolation, and method tampering."""
    secret = "synthetic-secret"  # ruff: ignore[hardcoded-password-string] -- synthetic test credential
    storage_file = tmp_path / "storage.json"
    storage_file.write_text(
        json.dumps({
            "endpoint": service.url + "/client",
            "service_endpoint": service.url.replace("127.0.0.1", "localhost") + "/qpu",
            "bucket": "synthetic",
            "region": "eu-central-1",
            "access_key": "synthetic-access",
            "secret_key": secret,
            "session_token": "synthetic+session/token",
        }),
        encoding="utf-8",
    )
    payloads: list[dict[str, Any]] = []

    def submit(_path: str, body: bytes) -> tuple[int, bytes]:
        payloads.append(json.loads(body))
        return 204, b""

    def accept_storage(path: str) -> None:
        if path.startswith("/client/"):
            service.data[path.rsplit("/", 1)[-1]] = {}

    service.respond = submit
    service.before_respond = accept_storage
    parameters = service.parameters | {999999998: "quantum-system", 999999999: str(storage_file)}
    with native.session(parameters) as session:
        assert native.init(session) == 0
        with native.job(session) as job:
            configure(native, job)
            assert native.submit(job) == 0
    assert len(service.puts) == 1
    assert len(payloads) == 1
    upload = service.url + service.puts[0]

    def check_scope(url: str) -> str:
        query = parse_qs(urlsplit(url).query)
        date = query["X-Amz-Date"][0][:8]
        assert query["X-Amz-Credential"] == [f"synthetic-access/{date}/eu-central-1/s3/aws4_request"]
        assert query["X-Amz-Security-Token"] == ["synthetic+session/token"]
        assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
        assert query["X-Amz-Expires"] == ["86400"]
        return query["X-Amz-Signature"][0]

    actual = check_scope(upload)
    assert _storage_signature(upload, "PUT", secret) == actual
    assert _storage_signature(upload, "GET", secret) != actual
    assert set(payloads[0]["storage"]) == {"input", "results", "logs"}
    for kind, descriptor in payloads[0]["storage"].items():
        url = descriptor["presigned_url"]
        assert urlsplit(url).hostname == "localhost"
        assert urlsplit(url).path.startswith("/qpu/synthetic/")
        expected = _storage_signature(url, "GET" if kind == "input" else "PUT", secret)
        assert check_scope(url) == expected
    headers = next(headers for path, headers, _body in service.requests if path == service.puts[0])
    assert {name.lower() for name in headers}.isdisjoint({"authorization", "service-crn", "ibm-api-version"})
