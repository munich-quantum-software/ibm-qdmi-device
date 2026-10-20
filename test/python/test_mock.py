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

"""Official Runtime fakes exercised through the installed native QDMI device."""

from __future__ import annotations

import gc
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from urllib.parse import urlsplit

import numpy as np
import pennylane as qml
import pytest
from mqt.core.qdmi import Job
from mqt.core.qdmi.builtin_driver import open_device
from qiskit import QuantumCircuit, transpile
from qiskit.circuit import ClassicalRegister, Instruction, Parameter, QuantumRegister
from qiskit.primitives import BitArray, PrimitiveResult
from qiskit.quantum_info import SparsePauliOp
from qiskit_ibm_runtime import QuantumProgram, RuntimeDecoder, RuntimeEncoder
from qiskit_ibm_runtime.executor_sampler.prepare import prepare
from qiskit_ibm_runtime.fake_provider import FakeManilaV2
from qiskit_ibm_runtime.options_models.sampler import SamplerOptions
from qiskit_ibm_runtime.results import QuantumProgramResult
from samplomatic import build
from samplomatic.transpiler import generate_boxing_pass_manager

from ibm.qdmi import _mock_runtime  # ruff: ignore[import-private-name]
from ibm.qdmi._backends import build_sampler  # ruff: ignore[import-private-name]
from ibm.qdmi._catalogue import session_parameters  # ruff: ignore[import-private-name]
from ibm.qdmi.mock import _Runtime  # ruff: ignore[import-private-name]
from ibm.qdmi.pennylane import IBMDevice
from ibm.qdmi.qiskit import IBMBackend

pytestmark = pytest.mark.mock
pytest.importorskip("qiskit_aer")


def test_mock_round_trip_without_cloud_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """A named fake runs real circuits and supports retrieval through another session."""
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "must-not-be-used")
    monkeypatch.setenv("IBM_QUANTUM_INSTANCE_CRN", "must-not-be-used")
    backend = IBMBackend(backend_name="fake_manila")
    assert backend.num_qubits == 5
    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure_all()
    compiled = transpile(circuit, backend, seed_transpiler=7)
    job = backend.run([compiled, compiled], shots=64, memory=True)
    result = job.result()
    for index in range(2):
        assert sum(result.get_counts(index).values()) == 64
        assert dict(Counter(result.get_memory(index))) == result.get_counts(index)
        assert set(result.get_counts(index)) <= {"00", "01", "10", "11"}
        assert result.get_counts(index).get("00", 0) + result.get_counts(index).get("11", 0) > 48
    fresh = IBMBackend(backend_name="fake_manila")
    retrieved = fresh.device.retrieve_job_by_id(job.job_id())
    assert retrieved.get_shots(0) == result.get_memory(0)


def test_unknown_fake_fails_locally() -> None:
    """A misspelled fake cannot fall through to hardware."""
    with pytest.raises(ValueError, match="Unknown fake backend"):
        IBMBackend(backend_name="fake_does_not_exist")


@pytest.mark.filterwarnings("ignore:The SamplerV2 class is deprecated:DeprecationWarning")
def test_mock_accepts_runtime_qpy_encoding() -> None:
    """Runtime-encoded circuits work when a native device advertises QPY."""
    circuit = QuantumCircuit(5, 1)
    circuit.x(0)
    circuit.measure(0, 0)
    source = json.loads(json.dumps(circuit, cls=RuntimeEncoder))
    runtime = _Runtime("fake_manila")
    identifier = runtime.submit({
        "backend": "fake_manila",
        "program_id": "sampler",
        "params": {"version": 2, "support_qiskit": False, "pubs": [[source, None, 4]]},
    })
    result = runtime.result(runtime.jobs[identifier])
    assert result["results"][0]["data"]["c"]["samples"] == ["0x1"] * 4


@pytest.mark.parametrize("source", [None, [], {}, {"__type__": "settings", "__value__": {}}])
def test_mock_rejects_other_runtime_types(source: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only circuit encodings may reach the Runtime decoder."""

    def unexpected_decode(_decoder: object, _source: object) -> None:
        pytest.fail("Unsupported source reached the Runtime decoder")

    monkeypatch.setattr(RuntimeDecoder, "object_hook", unexpected_decode)
    runtime = _Runtime("fake_manila")
    with pytest.raises(ValueError, match="Unsupported Sampler circuit"):
        runtime.submit({
            "backend": "fake_manila",
            "program_id": "sampler",
            "params": {"version": 2, "support_qiskit": False, "pubs": [[source, None, 4]]},
        })


@pytest.mark.parametrize("override", ["api_key", "instance_crn", "base_url", "auth_url"])
def test_fake_connection_overrides_select_remote_service(override: str) -> None:
    """Explicit connections can target services with fake-prefixed backend names."""
    parameters = session_parameters(
        backend_name="fake_lagos",
        api_key="synthetic" if override == "api_key" else None,
        instance_crn="synthetic" if override == "instance_crn" else None,
        base_url="http://127.0.0.1:8290" if override == "base_url" else None,
        auth_url="http://127.0.0.1:8290/identity/token" if override == "auth_url" else None,
    )
    assert parameters["custom1"] == "fake_lagos"
    assert parameters["base_url"] == ("http://127.0.0.1:8290" if override == "base_url" else None)


def test_mock_metadata_and_environment_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """The generic environment selector uses official metadata without IAM access."""
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "fake_manila")
    backend = IBMBackend()
    official = FakeManilaV2()
    assert backend.num_qubits == official.num_qubits
    assert set(backend.coupling_map.get_edges()) == set(official.coupling_map.get_edges())
    assert {"x", "sx", "rz", "cx", "measure"} <= set(backend.target.operation_names)


def test_register_order_binding_and_primitives() -> None:
    """Native sampling preserves unequal registers and binds parameter sweeps."""
    backend = IBMBackend(backend_name="fake_manila")
    qubits = QuantumRegister(2)
    left = ClassicalRegister(1, "left")
    right = ClassicalRegister(2, "right")
    circuit = QuantumCircuit(qubits, left, right)
    theta = Parameter("theta")
    circuit.rx(theta, 0)
    circuit.measure(0, right[1])
    circuit.measure(1, left[0])
    compiled = transpile(circuit, backend, seed_transpiler=7)
    result = backend.run([compiled, compiled], parameter_values=[{theta: 0}, {theta: np.pi}], shots=128).result()
    assert result.get_counts(0).get("00 0", 0) > 100
    assert result.get_counts(1).get("10 0", 0) > 100
    sampler_result = backend.sampler().run([compiled.assign_parameters({theta: 0})], shots=16).result()
    joint = sampler_result[0].join_data()
    assert isinstance(joint, BitArray)
    assert sum(joint.get_counts().values()) == 16
    observable = SparsePauliOp("Z")
    one = QuantumCircuit(1)
    compiled_one = transpile(one, backend, seed_transpiler=7)
    estimator_result = (
        backend.estimator().run([(compiled_one, observable.apply_layout(compiled_one.layout))], precision=0.1).result()
    )
    assert float(estimator_result[0].data["evs"]) > 0.7


def test_executor_simulates_circuit_and_samplex_items() -> None:
    """Executor runs real parameterized items and preserves shaped correction arrays."""
    circuit = QuantumCircuit(1, 1)
    circuit.rz(Parameter("theta"), 0)
    circuit.measure(0, 0)
    program = QuantumProgram(shots=8, passthrough_data={"experiment": "local"})
    arguments = np.array([[0.0], [np.pi / 2]])
    program.append_circuit_item(circuit, circuit_arguments=arguments)
    boxed = generate_boxing_pass_manager(enable_gates=False, enable_measures=True).run(circuit)
    template, samplex = build(boxed)
    program.append_samplex_item(
        template, samplex=samplex, samplex_arguments={"parameter_values": arguments}, shape=(2, 2)
    )
    backend = IBMBackend(backend_name="fake_manila")
    executor = backend.executor()
    job = executor.run(program)
    result = job.result(timeout=30)
    assert isinstance(result, QuantumProgramResult)
    assert result[0]["c"].shape == (2, 8, 1)
    assert result[1]["c"].shape == (2, 2, 8, 1)
    assert "measurement_flips.c" in result[1]
    assert result.passthrough_data == {"experiment": "local"}
    retrieved = IBMBackend(backend_name="fake_manila").executor().retrieve_job(job.job_id()).result(timeout=30)
    np.testing.assert_array_equal(retrieved[1]["c"], result[1]["c"])


def test_mock_pennylane_and_offloader() -> None:
    """Framework helpers share the same native mock selection."""
    device = IBMDevice(wires=1, backend_name="fake_manila")

    @qml.qnode(device, shots=128)
    def circuit() -> qml.measurements.MeasurementProcess:
        qml.PauliX(0)
        return qml.sample(wires=0)

    assert np.mean(circuit()) > 0.8
    assert build_sampler(simulator=False, backend_name="fake_manila").backend.num_qubits == 5


def test_mock_job_outlives_backend() -> None:
    """A native job retains access to its local service after backend collection."""
    backend = IBMBackend(backend_name="fake_manila")
    circuit = QuantumCircuit(1, 1)
    circuit.measure(0, 0)
    job = backend.run(circuit, shots=8)
    del backend
    gc.collect()
    assert sum(job.result().get_counts().values()) == 8


def test_standalone_service_and_parent_cleanup() -> None:
    """Native clients can use printed session parameters; EOF stops the child."""
    process = subprocess.Popen(
        [sys.executable, "-m", "ibm.qdmi.mock", "--backend-name", "fake_manila", "--parent-pipe"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert process.stdout is not None
        parameters = json.loads(process.stdout.readline())
        assert parameters["base_url"].startswith("http://127.0.0.1:")
        backend = IBMBackend(device=open_device("ibm.default", **parameters))
        circuit = QuantumCircuit(1, 1)
        circuit.measure(0, 0)
        assert sum(backend.run(circuit, shots=8).result().get_counts().values()) == 8
        assert process.stdin is not None
        process.stdin.close()
        assert process.wait(timeout=10) == 0
    finally:
        _mock_runtime._stop(process)  # ruff: ignore[private-member-access] -- verify service cleanup


def test_missing_mock_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing Aer fails before opening a native session or child process."""
    monkeypatch.setitem(sys.modules, "qiskit_aer", None)
    with pytest.raises(ImportError, match=r"ibm-qdmi\[mock\]"):
        IBMBackend(backend_name="fake_manila")


def test_parent_loss_stops_active_workers() -> None:
    """An orphan cannot keep simulating after the owning parent pipe closes."""
    script = """
import time
from concurrent.futures import ThreadPoolExecutor
from ibm.qdmi.mock import main
pool = ThreadPoolExecutor()
pool.submit(time.sleep, 30)
main(['--backend-name', 'fake_manila', '--parent-pipe'])
"""
    process = subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed worker probe
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert json.loads(process.stdout.readline())["custom1"] == "fake_manila"
        assert process.stdin is not None
        process.stdin.close()
        assert process.wait(timeout=3) == 0
    finally:
        _mock_runtime._stop(process)  # ruff: ignore[private-member-access] -- verify service cleanup


def test_executor_semantic_role_decoding() -> None:
    """Client-side Sampler programs retain Runtime post-processing after QDMI transport."""
    backend = IBMBackend(backend_name="fake_manila")
    circuit = QuantumCircuit(1)
    circuit.measure_all()
    compiled = transpile(circuit, backend, seed_transpiler=7)
    program, options = prepare(
        [compiled],
        SamplerOptions(twirling={"enable_gates": False, "enable_measure": False}),
        shots=16,
        add_tags=True,
        backend=FakeManilaV2(),
    )
    program._semantic_role = "sampler_v2"  # ruff: ignore[private-member-access] -- Runtime's semantic-role contract
    result = backend.executor(options=options).run(program).result(timeout=30)
    assert isinstance(result, PrimitiveResult)
    assert sum(result[0].data.meas.get_counts().values()) == 16


def test_mock_concurrent_sessions() -> None:
    """Independent native sessions share one service without losing job identity."""

    def run(index: int) -> tuple[str, int]:
        backend = IBMBackend(backend_name="fake_manila")
        circuit = QuantumCircuit(1, 1)
        circuit.measure(0, 0)
        job = backend.run(circuit, shots=8 + index)
        return job.job_id(), sum(job.result().get_counts().values())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert len({identifier for identifier, _ in results}) == 2
    assert [shots for _, shots in results] == [8, 9]


def test_startup_failure_reaps_child(monkeypatch: pytest.MonkeyPatch) -> None:
    """A child that exits before readiness never becomes a cached connection."""
    original = subprocess.Popen
    children = []

    def fail(*_args: object, **_kwargs: object) -> subprocess.Popen[str]:
        child = original(
            [sys.executable, "-c", "print('not-json')"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        children.append(child)
        return child

    monkeypatch.setattr(_mock_runtime.subprocess, "Popen", fail)
    with pytest.raises(RuntimeError, match="failed to start"):
        _mock_runtime.connection("fake_bogota")
    assert len(children) == 1
    assert children[0].poll() is not None


def test_executor_failure_and_cancellation() -> None:
    """Simulator errors fail native jobs; cancellation follows the real local job state."""
    backend = IBMBackend(backend_name="fake_manila")
    circuit = QuantumCircuit(1, 1)
    circuit.append(Instruction("invalid_mock_instruction", 1, 0, []), [0])
    circuit.measure(0, 0)
    program = QuantumProgram(shots=8)
    program.append_circuit_item(circuit)
    job = backend.executor().run(program)
    with pytest.raises(RuntimeError):
        job.result(timeout=30)
    assert job.status() == Job.Status.FAILED
    valid = QuantumCircuit(1, 1)
    valid.measure(0, 0)
    sampler = backend.run(valid, shots=8)
    if sampler.cancel():
        assert sampler.cancelled()
    else:
        assert sum(sampler.result().get_counts().values()) == 8


def test_local_http_validation() -> None:
    """The loopback boundary rejects malformed requests and unknown resources."""
    parameters = _mock_runtime.connection("fake_manila")
    token = parameters["token"]
    assert token is not None
    endpoint = urlsplit(parameters["base_url"])
    source = 'OPENQASM 3; include "stdgates.inc"; qubit[1] q; bit[1] c; c[0] = measure q[0];'
    params = {"version": 2, "support_qiskit": False, "pubs": [[source, None, 4]]}
    request = {"backend": "fake_manila", "program_id": "sampler", "params": params}
    backend = IBMBackend(backend_name="fake_manila")
    circuit = QuantumCircuit(1, 1)
    circuit.measure(0, 0)
    job = backend.run(circuit, shots=4)
    job.result()
    cases = [
        ("POST", "/v1/jobs", {**request, "backend": "wrong"}, {}, 400),
        ("POST", "/v1/jobs", {**request, "program_id": "unknown"}, {}, 400),
        ("POST", "/v1/jobs", {**request, "params": {**params, "version": 1}}, {}, 400),
        ("POST", "/v1/jobs", {**request, "params": {**params, "pubs": []}}, {}, 400),
        ("POST", "/v1/jobs", {**request, "params": {**params, "pubs": [[source, None, True]]}}, {}, 400),
        (
            "POST",
            "/v1/jobs",
            {**request, "params": {**params, "options": {"dynamical_decoupling": {"enable": True}}}},
            {},
            400,
        ),
        ("POST", "/v1/jobs", {**request, "params": {**params, "pubs": [["invalid qasm", None, 4]]}}, {}, 500),
        ("POST", "/v1/jobs", {}, {}, 400),
        ("GET", "/v1/jobs/unknown", {}, {}, 404),
        ("GET", f"/v1/jobs/{job.job_id()}/unknown", {}, {}, 404),
        ("POST", f"/v1/jobs/{job.job_id()}/unknown", {}, {}, 404),
        ("GET", "/v1/backends/fake_manila/unknown", {}, {}, 404),
        ("GET", "/unknown", {}, {"Authorization": "wrong"}, 401),
        ("POST", "/v1/jobs", {}, {"Content-Length": str(16 * 1024 * 1024 + 1)}, 413),
        ("POST", "/v1/jobs", {}, {"Content-Length": "invalid"}, 400),
    ]
    for method, path, payload, extra_headers, expected in cases:
        connection = HTTPConnection("127.0.0.1", endpoint.port, timeout=10)
        try:
            connection.request(
                method,
                path,
                body=json.dumps(payload),
                headers={
                    "Authorization": "Bearer " + token,
                    **extra_headers,
                },
            )
            response = connection.getresponse()
            assert response.status == expected, path
            response.read()
        finally:
            connection.close()


def test_stopped_service_does_not_replace_existing_jobs() -> None:
    """A dead service cannot silently restart with an empty job registry."""
    _mock_runtime.connection("fake_belem")
    process, _ = _mock_runtime._SERVICES["fake_belem"]  # ruff: ignore[private-member-access] -- simulate a crashed child
    process.terminate()
    process.wait(timeout=5)
    with pytest.raises(RuntimeError, match="stopped"):
        _mock_runtime.connection("fake_belem")


def test_unresponsive_service_is_reaped() -> None:
    """Cleanup kills a child that does not observe the closed parent pipe."""
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    _mock_runtime._stop(process)  # ruff: ignore[private-member-access] -- exercise bounded cleanup
    assert process.poll() is not None
