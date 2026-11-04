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

"""Serve IBM fake metadata and ideal MQT Core simulation through native QDMI.

Run ``python -m ibm.qdmi.mock --backend-name fake_manila`` for native clients.
The first stdout line contains synthetic QDMI session parameters as JSON.
"""

from __future__ import annotations

import argparse
import atexit
import base64
import io
import json
import secrets
import uuid
import zlib
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Lock, Thread
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

if TYPE_CHECKING:
    from collections.abc import Sequence

    import numpy as np
    from mqt.core.typing import QDMISessionParameters
    from qiskit import QuantumCircuit

_CRN = "crn:v1:bluemix:public:quantum-computing:us-east:a:local::"
_MAX_BODY = 16 * 1024 * 1024
_SERVICES: dict[str, tuple[HTTPServer, QDMISessionParameters]] = {}
_LOCK = Lock()


def _sample(circuit: QuantumCircuit, shots: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Sample ideal circuits with correlated classical registers.

    Returns:
        Boolean arrays indexed by shot and register bit.
    """
    import numpy as np  # ruff: ignore[import-outside-top-level]
    from mqt.core.mlir import sample  # ruff: ignore[import-outside-top-level]

    histogram = sample(circuit, shots=shots, seed=int(rng.integers(1, 2**32)))
    memory = [bits for bits, count in histogram.items() for _ in range(count)]
    rng.shuffle(memory)
    bits = np.array([[bit == "1" for bit in sample[::-1]] for sample in memory], dtype=bool)
    return {register.name: bits[:, [circuit.find_bit(bit).index for bit in register]] for register in circuit.cregs}


def _simulate(request: dict[str, Any]) -> dict[str, Any]:
    """Execute the native Sampler or Executor payload using MQT Core.

    Returns:
        Results in the IBM wire format.

    Raises:
        ValueError: A noise model is requested.
    """
    import numpy as np  # ruff: ignore[import-outside-top-level]
    from qiskit import qasm3, qpy  # ruff: ignore[import-outside-top-level]

    params = request["params"]
    rng = np.random.default_rng(7)
    if request["program_id"] == "sampler":
        results = []
        for source, _, shots in params["pubs"]:
            if isinstance(source, str):
                circuit = qasm3.loads(source)
            else:
                (circuit,) = qpy.load(io.BytesIO(zlib.decompress(base64.b64decode(source["__value__"], validate=True))))
            data = _sample(circuit, shots, rng)
            results.append({
                "data": {
                    name: {
                        "samples": [
                            hex(int.from_bytes(row.tobytes(), "little"))
                            for row in np.packbits(bits, axis=-1, bitorder="little")
                        ],
                        "num_bits": bits.shape[-1],
                    }
                    for name, bits in data.items()
                }
            })
        return {"results": results}

    from ibm_quantum_schemas.common import CompressedTensorModel  # ruff: ignore[import-outside-top-level]
    from ibm_quantum_schemas.executor.version_2_0 import ParamsModel, QuantumProgramResultModel  # ruff: ignore[import-outside-top-level]
    from qiskit_ibm_runtime.fake_provider.executor.broadcast_sample import broadcast_sample  # ruff: ignore[import-outside-top-level]
    from qiskit_ibm_runtime.quantum_program.converters import quantum_program_from_2_0  # ruff: ignore[import-outside-top-level]
    from samplomatic.quantum_program import CircuitItem, SamplexItem  # ruff: ignore[import-outside-top-level]

    program, options = quantum_program_from_2_0(ParamsModel.model_validate(params))
    if options.simulator.layer_noise_model:
        msg = "The mock supports ideal simulation only."
        raise ValueError(msg)
    outputs = []
    for item in program.items:
        if isinstance(item, SamplexItem):
            item.samplex.finalize()
            data = broadcast_sample(item.samplex, item.samplex_arguments, item.shape, rng)
            bindings = data.pop("parameter_values")
        else:
            assert isinstance(item, CircuitItem)
            data = {}
            bindings = item.circuit_arguments
        for register in item.circuit.cregs:
            data[register.name] = np.empty((*item.shape, program.shots, len(register)), dtype=bool)
        for index in np.ndindex(item.shape):
            circuit = item.circuit.assign_parameters(bindings[index])
            for name, samples in _sample(circuit, program.shots, rng).items():
                data[name][index] = samples
        outputs.append({
            "results": {name: CompressedTensorModel.from_numpy(value) for name, value in data.items()},
            "metadata": {},
        })
    return QuantumProgramResultModel.model_validate({
        "data": outputs,
        "metadata": {"chunk_timing": []},
        "passthrough_data": params["quantum_program"].get("passthrough_data"),
        "semantic_role": params["quantum_program"].get("semantic_role"),
    }).model_dump(mode="json")


@dataclass
class _Job:
    request: dict[str, Any]
    future: Future[dict[str, Any]]


class _Runtime:
    """Keep fake metadata and local jobs for one backend."""

    def __init__(self, name: str) -> None:
        try:
            from qiskit_ibm_runtime import fake_provider  # ruff: ignore[import-outside-top-level]
            from qiskit_ibm_runtime.fake_provider.fake_backend import FakeBackendV2  # ruff: ignore[import-outside-top-level]
        except ImportError as error:
            msg = "Install 'ibm-qdmi[mock]' to use fake backends."
            raise ImportError(msg) from error
        for backend in vars(fake_provider).values():
            if isinstance(backend, type) and issubclass(backend, FakeBackendV2) and backend.backend_name == name:
                self.backend = backend()
                break
        else:
            msg = f"Unknown fake backend: {name}."
            raise ValueError(msg)
        self.token = secrets.token_urlsafe(32)
        self.jobs: dict[str, _Job] = {}
        self.executor = ThreadPoolExecutor(max_workers=1)

    def respond(self, method: str, path: str, body: bytes) -> tuple[int, Any]:
        """Handle the REST subset used by the native device.

        Returns:
            HTTP status and response data.
        """
        if path == "/auth" and method == "POST":
            if parse_qs(body.decode()).get("apikey") != [self.token]:
                return 401, {}
            return 200, {"access_token": self.token, "expires_in": 86400, "token_type": "Bearer"}
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
            request = json.loads(body)
            if request["backend"] != self.backend.name or request["program_id"] not in {"sampler", "executor"}:
                return 400, {}
            if request["program_id"] == "sampler":
                params = request["params"]
                options = params.get("options", {})
                if (
                    params["version"] != 2
                    or params.get("support_qiskit", True)
                    or not params["pubs"]
                    or options.get("dynamical_decoupling", {}).get("enable", False)
                    or any(options.get("twirling", {}).values())
                    or options.get("execution", {}).get("meas_type", "classified") != "classified"
                ):
                    return 400, {}
                for source, bindings, shots in params["pubs"]:
                    if (
                        bindings not in (None, [])
                        or isinstance(shots, bool)
                        or not isinstance(shots, int)
                        or shots <= 0
                        or not (
                            isinstance(source, str)
                            or (
                                isinstance(source, dict)
                                and source.get("__type__") == "QuantumCircuit"
                                and isinstance(source.get("__value__"), str)
                            )
                        )
                    ):
                        return 400, {}
            identifier = "mock-" + uuid.uuid4().hex
            self.jobs[identifier] = _Job(request, self.executor.submit(_simulate, request))
            return 200, {"id": identifier, "backend": self.backend.name}
        parts = path.split("/")
        if len(parts) not in {4, 5} or parts[1:3] != ["v1", "jobs"] or parts[3] not in self.jobs:
            return 404, {}
        job = self.jobs[parts[3]]
        if method == "POST" and len(parts) == 5 and parts[4] == "cancel":
            return (204 if job.future.cancel() else 409), {}
        if method != "GET":
            return 404, {}
        if job.future.cancelled():
            status = "Cancelled"
        elif job.future.done():
            status = "Failed" if job.future.exception() else "Completed"
        else:
            status = "Running" if job.future.running() else "Queued"
        if len(parts) == 5:
            if parts[4] != "results":
                return 404, {}
            return (200, job.future.result()) if status == "Completed" else (409, {})
        return 200, {
            "id": parts[3],
            "backend": self.backend.name,
            "program": {"id": job.request["program_id"]},
            "params": job.request["params"],
            "state": {"status": status},
        }


def _server(name: str, port: int = 0) -> tuple[HTTPServer, QDMISessionParameters]:
    """Create an authenticated loopback service.

    Returns:
        The server and synthetic native session settings.
    """
    from qiskit_ibm_runtime import RuntimeEncoder  # ruff: ignore[import-outside-top-level]

    runtime = _Runtime(name)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # ruff: ignore[builtin-argument-shadowing]
            """Keep request contents out of logs."""

        def respond(self) -> None:
            """Validate framing and translate request errors into HTTP responses."""
            try:  # ruff: ignore[too-many-statements-in-try-clause] -- one HTTP error boundary
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= _MAX_BODY or self.headers.get("Transfer-Encoding"):
                    self.send_error(413)
                    return
                path = urlsplit(self.path).path
                if path != "/auth" and self.headers.get("Authorization") != f"Bearer {runtime.token}":
                    self.send_error(401)
                    return
                status, data = runtime.respond(self.command, path, self.rfile.read(size))
                content = json.dumps(data, cls=RuntimeEncoder).encode()
            except (KeyError, TypeError, ValueError):
                status, content = 400, b"{}"
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

    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    return server, {
        "base_url": url,
        "auth_url": url + "/auth",
        "token": runtime.token,
        "custom1": name,
        "custom2": _CRN,
    }


def _shutdown() -> None:
    for server, _ in _SERVICES.values():
        server.shutdown()
        server.server_close()
    _SERVICES.clear()


atexit.register(_shutdown)


def connection(name: str) -> QDMISessionParameters:
    """Reuse one local service per fake backend for this process.

    Returns:
        Synthetic native session settings.
    """
    with _LOCK:
        if name not in _SERVICES:
            server, parameters = _server(name)
            Thread(target=server.serve_forever, daemon=True).start()
            _SERVICES[name] = server, parameters
        return _SERVICES[name][1].copy()


def main(argv: Sequence[str] | None = None) -> None:
    """Run a standalone loopback mock until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-name", default="fake_manila")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        server, parameters = _server(args.backend_name, args.port)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(parameters), flush=True)  # ruff: ignore[print] -- native client startup protocol
    with server, suppress(KeyboardInterrupt):
        server.serve_forever()


if __name__ == "__main__":
    main()
