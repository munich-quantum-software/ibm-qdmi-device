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

"""Serve official Qiskit Runtime fake backends through the native IBM transport.

Run ``python -m ibm.qdmi.mock --backend-name fake_manila`` for native clients.
The first stdout line contains synthetic QDMI session parameters as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import uuid
from contextlib import suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.util import find_spec
from threading import Lock, Thread
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qiskit_ibm_runtime.fake_provider.fake_backend import FakeBackendV2

_TOKEN = secrets.token_urlsafe(32)
_CRN = "crn:v1:bluemix:public:quantum-computing:us-east:a:local::"
_SEED = 7
_MAX_BODY = 16 * 1024 * 1024


def _backend_type(name: str) -> type[FakeBackendV2]:
    """Resolve a bundled fake without loading unrelated snapshots.

    Returns:
        The requested Runtime backend class.

    Raises:
        ImportError: The mock extra is missing.
        ValueError: The requested fake backend does not exist.
    """
    if find_spec("qiskit_aer") is None or find_spec("qiskit_ibm_runtime") is None:
        msg = "Install 'ibm-qdmi[mock]' on a platform supported by Qiskit Aer to use fake backends."
        raise ImportError(msg)
    from qiskit_ibm_runtime import fake_provider  # ruff: ignore[import-outside-top-level]
    from qiskit_ibm_runtime.fake_provider.fake_backend import FakeBackendV2  # ruff: ignore[import-outside-top-level]

    for backend in vars(fake_provider).values():
        if isinstance(backend, type) and issubclass(backend, FakeBackendV2) and backend.backend_name == name:
            return backend
    msg = f"Unknown fake backend: {name}."
    raise ValueError(msg)


@dataclass
class _Job:
    request: dict[str, Any]
    primitive: Any
    output: dict[str, Any] | None = None
    failed: bool = False


class _Runtime:
    """Adapt Runtime's local primitives to the REST subset used by native QDMI."""

    def __init__(self, name: str) -> None:
        self.backend = _backend_type(name)()
        self.jobs: dict[str, _Job] = {}
        self.lock = Lock()

    def submit(self, request: dict[str, Any]) -> str:
        """Execute validated native requests using official local primitives.

        Returns:
            The local job identifier.

        Raises:
            TypeError: A Sampler circuit has an unsupported type.
            ValueError: The program or its options are unsupported.
        """
        from qiskit import qasm3  # ruff: ignore[import-outside-top-level]
        from qiskit.primitives.containers import SamplerPub  # ruff: ignore[import-outside-top-level]
        from qiskit_ibm_runtime import Executor, SamplerV2  # ruff: ignore[import-outside-top-level]

        if request["backend"] != self.backend.name:
            msg = "Wrong backend."
            raise ValueError(msg)
        params = request["params"]
        if request["program_id"] == "sampler":
            if params["version"] != 2 or params.get("support_qiskit", True):
                msg = "Unsupported Sampler encoding."
                raise ValueError(msg)
            options = params.get("options", {})
            if (
                options.get("dynamical_decoupling", {}).get("enable", False)
                or any(options.get("twirling", {}).values())
                or options.get("execution", {}).get("meas_type", "classified") != "classified"
            ):
                msg = "Unsupported local Sampler options."
                raise ValueError(msg)
            pubs = []
            for source, bindings, shots in params["pubs"]:
                if bindings not in (None, []) or isinstance(shots, bool) or not isinstance(shots, int) or shots <= 0:
                    msg = "Invalid Sampler PUB."
                    raise ValueError(msg)
                if not isinstance(source, str):
                    msg = "Unsupported Sampler circuit."
                    raise TypeError(msg)
                pubs.append(SamplerPub(qasm3.loads(source), shots=shots))
            if not pubs:
                msg = "Empty Sampler request."
                raise ValueError(msg)
            primitive = SamplerV2(mode=self.backend, options={"simulator": {"seed_simulator": _SEED}}).run(pubs)
        elif request["program_id"] == "executor":
            from ibm_quantum_schemas.executor.version_2_0 import ParamsModel  # ruff: ignore[import-outside-top-level]
            from qiskit_ibm_runtime.quantum_program.converters import (  # ruff: ignore[import-outside-top-level]
                quantum_program_from_2_0,
            )
            from samplomatic.quantum_program import SamplexItem  # ruff: ignore[import-outside-top-level]

            program, options = quantum_program_from_2_0(ParamsModel.model_validate(params))
            # Schema decoding reconstructs graphs without their sampling traversal.
            for item in program.items:
                if isinstance(item, SamplexItem):
                    item.samplex.finalize()
            options.simulator.seed_simulator = _SEED
            primitive = Executor(mode=self.backend, options=options).run(program)
        else:
            msg = "Unsupported program."
            raise ValueError(msg)
        identifier = "mock-" + uuid.uuid4().hex
        with self.lock:
            self.jobs[identifier] = _Job(request, primitive)
        return identifier

    @staticmethod
    def result(job: _Job) -> dict[str, Any]:
        """Encode real samples without changing the native result decoder.

        Returns:
            Cached IBM wire-format results.
        """
        if job.output is not None:
            return job.output
        if job.request["program_id"] == "executor":
            from ibm_quantum_schemas.common import CompressedTensorModel  # ruff: ignore[import-outside-top-level]
            from ibm_quantum_schemas.executor.version_2_0 import (  # ruff: ignore[import-outside-top-level]
                QuantumProgramResultModel,
            )
            from qiskit.primitives.primitive_job import PrimitiveJob  # ruff: ignore[import-outside-top-level]

            # Preserve raw arrays; ExecutorJob applies semantic post-processing after transport.
            result = PrimitiveJob.result(job.primitive)
            params = job.request["params"]["quantum_program"]
            output = QuantumProgramResultModel.model_validate({
                "data": [
                    {
                        "results": {name: CompressedTensorModel.from_numpy(value) for name, value in item.items()},
                        "metadata": {},
                    }
                    for item in result
                ],
                "metadata": {"chunk_timing": []},
                "passthrough_data": params.get("passthrough_data"),
                "semantic_role": params.get("semantic_role"),
            }).model_dump(mode="json")
        else:
            result = job.primitive.result()
            output = {
                "results": [
                    {
                        "data": {
                            name: {
                                "samples": [
                                    hex(int.from_bytes(row, "big") & ((1 << value.num_bits) - 1)) for row in value.array
                                ],
                                "num_bits": value.num_bits,
                            }
                            for name, value in pub.data.items()
                        }
                    }
                    for pub in result
                ]
            }
        job.output = output
        return output

    def respond(self, method: str, path: str, body: bytes) -> tuple[int, Any]:
        """Handle the bounded native API subset; unknown routes remain errors.

        Returns:
            An HTTP status and its response data.
        """
        if path == "/auth" and method == "POST":
            if parse_qs(body.decode()).get("apikey") != [_TOKEN]:
                return 401, {}
            return 200, {"access_token": _TOKEN, "expires_in": 86400, "token_type": "Bearer"}
        prefix = f"/v1/backends/{self.backend.name}/"
        if method == "GET" and path.startswith(prefix):
            resource = path.removeprefix(prefix)
            if resource == "configuration":
                config = self.backend.configuration().to_dict()
                config["coupling_map"] = config.get("coupling_map") or []
                config["supported_instructions"] = list(self.backend.target.operation_names)
                return 200, config
            if resource == "properties":
                return 200, self.backend.properties().to_dict()
            if resource == "status":
                return 200, {"state": True, "length_queue": 0}
        if path == "/v1/jobs" and method == "POST":
            identifier = self.submit(json.loads(body))
            return 200, {"id": identifier, "backend": self.backend.name}
        parts = path.split("/")
        if len(parts) not in {4, 5} or parts[1:3] != ["v1", "jobs"]:
            return 404, {}
        with self.lock:
            job = self.jobs.get(parts[3])
        if job is None:
            return 404, {}
        if method == "POST" and len(parts) == 5 and parts[4] == "cancel":
            return (204 if job.primitive.cancel() else 409), {}
        if method != "GET":
            return 404, {}
        state = job.primitive.status().name
        if state == "DONE" and not job.failed:
            try:
                self.result(job)
            except Exception:  # ruff: ignore[blind-except] -- simulator failures become failed native jobs
                job.failed = True
        if len(parts) == 5:
            if parts[4] != "results":
                return 404, {}
            if state != "DONE" or job.failed:
                return 409, {}
            return 200, job.output
        status = {
            "DONE": "Completed",
            "ERROR": "Failed",
            "CANCELLED": "Cancelled",
            "RUNNING": "Running",
            "QUEUED": "Queued",
            "INITIALIZING": "Queued",
        }[state]
        return 200, {
            "id": parts[3],
            "backend": self.backend.name,
            "program": {"id": job.request["program_id"]},
            "params": job.request["params"],
            "state": {"status": "Failed" if job.failed else status},
        }


def main(argv: Sequence[str] | None = None) -> None:
    """Run a loopback mock until interrupted or its owning parent closes stdin."""
    from qiskit_ibm_runtime import RuntimeEncoder  # ruff: ignore[import-outside-top-level]

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-name", default="fake_manila")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--parent-pipe", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        runtime = _Runtime(args.backend_name)
    except ValueError as error:
        parser.error(str(error))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # ruff: ignore[builtin-argument-shadowing]
            """Keep request contents out of logs."""

        def respond(self) -> None:
            """Validate framing and translate errors into local HTTP responses."""
            try:  # ruff: ignore[too-many-statements-in-try-clause] -- one HTTP error boundary
                size = int(self.headers.get("Content-Length", "0"))
                if size < 0 or size > _MAX_BODY or self.headers.get("Transfer-Encoding"):
                    self.send_error(413)
                    return
                path = urlsplit(self.path).path
                if path != "/auth" and self.headers.get("Authorization") != f"Bearer {_TOKEN}":
                    self.send_error(401)
                    return
                status, data = runtime.respond(self.command, path, self.rfile.read(size))
                content = json.dumps(data, cls=RuntimeEncoder).encode()
            except (KeyError, TypeError, ValueError):
                status, content = 400, b"{}"
            except Exception:  # ruff: ignore[blind-except] -- simulator errors must not expose request data
                status, content = 500, b"{}"
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            with suppress(ConnectionError):
                self.wfile.write(content)

        def do_GET(self) -> None:
            """Handle a native query."""
            self.respond()

        def do_POST(self) -> None:
            """Handle authentication, submission, or cancellation."""
            self.respond()

    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.daemon_threads = True
        url = f"http://127.0.0.1:{server.server_port}"
        print(  # ruff: ignore[print] -- stdout is the parent startup protocol
            json.dumps({
                "base_url": url,
                "auth_url": url + "/auth",
                "token": _TOKEN,
                "custom1": runtime.backend.name,
                "custom2": _CRN,
            }),
            flush=True,
        )
        if args.parent_pipe:

            def watch_parent() -> None:
                sys.stdin.buffer.read()
                server.shutdown()
                # Aer worker threads cannot keep an orphaned service alive.
                os._exit(0)

            Thread(target=watch_parent, daemon=True).start()
        with suppress(KeyboardInterrupt):
            server.serve_forever(poll_interval=0.05)


if __name__ == "__main__":
    main()
