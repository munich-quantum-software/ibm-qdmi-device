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

"""Manage local Runtime services outside the native binding's Python GIL."""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
from queue import Empty, Queue
from threading import Lock, Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mqt.core.typing import QDMISessionParameters

_SERVICES: dict[str, tuple[subprocess.Popen[str], QDMISessionParameters]] = {}
_LOCK = Lock()


def _stop(process: subprocess.Popen[str]) -> None:
    """Close the parent pipe and reap the service, including failed startups."""
    if process.stdin is not None:
        process.stdin.close()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    if process.stdout is not None:
        process.stdout.close()


def _shutdown() -> None:
    """Retain services until exit so native jobs outlive their Python backend."""
    for process, _ in _SERVICES.values():
        _stop(process)
    _SERVICES.clear()


atexit.register(_shutdown)


def connection(name: str) -> QDMISessionParameters:
    """Start one local service per target and return synthetic session parameters.

    Returns:
        Synthetic session parameters targeting the local service.

    Raises:
        ImportError: The mock extra is missing.
        ValueError: The requested fake backend does not exist.
        RuntimeError: The service cannot start.
    """
    try:
        import qiskit_aer  # ruff: ignore[import-outside-top-level, unused-import]
        from qiskit.providers.exceptions import QiskitBackendNotFoundError  # ruff: ignore[import-outside-top-level]
        from qiskit_ibm_runtime.fake_provider import FakeProviderForBackendV2  # ruff: ignore[import-outside-top-level]
    except ImportError as error:
        msg = "Install 'ibm-qdmi[mock]' on a platform supported by Qiskit Aer to use fake backends."
        raise ImportError(msg) from error
    with _LOCK:
        if name in _SERVICES:
            process, parameters = _SERVICES[name]
            if process.poll() is not None:
                msg = "The local mock service stopped; existing jobs are no longer available."
                raise RuntimeError(msg)
            return parameters.copy()
        try:
            FakeProviderForBackendV2().backend(name)
        except QiskitBackendNotFoundError as error:
            msg = f"Unknown fake backend: {name}."
            raise ValueError(msg) from error
        process = subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-m", "ibm.qdmi.mock", "--backend-name", name, "--parent-pipe"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env={key: value for key, value in os.environ.items() if not key.startswith("IBM_QUANTUM_")},
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        ready: Queue[str] = Queue()
        stdout = process.stdout
        assert stdout is not None
        Thread(target=lambda: ready.put(stdout.readline()), daemon=True).start()
        try:
            parameters: QDMISessionParameters = json.loads(ready.get(timeout=60))
        except (Empty, ValueError) as error:
            _stop(process)
            msg = "The local mock service failed to start. Run 'python -m ibm.qdmi.mock' for diagnostics."
            raise RuntimeError(msg) from error
        _SERVICES[name] = (process, parameters)
        return parameters.copy()
