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

"""PennyLane regression tests through the installed IBM library and loopback API."""

from __future__ import annotations

import gc
import math
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import numpy as np
import pennylane as qml
import pytest
from mqt.core.plugins.pennylane import PennyLaneConfigurationError, PennyLaneExecutionError, PennyLaneValidationError
from offline_service import CRN
from pennylane import numpy as pnp
from qiskit_service import remote_runtime

from ibm.qdmi.pennylane import IBMDevice

if TYPE_CHECKING:
    from collections.abc import Hashable, Iterator, Sequence

    from qiskit_service import RuntimeProxy


@pytest.fixture
def runtime() -> Iterator[RuntimeProxy]:
    """Host the real C ABI's synthetic REST peer in a separate process.

    Yields:
        The synthetic runtime and its recorded requests.
    """
    with remote_runtime() as proxy:
        yield proxy
        gc.collect()


def open_device(runtime: RuntimeProxy, wires: int | Sequence[Hashable] = 2) -> IBMDevice:
    """Open a fresh PennyLane session against the loopback service.

    Returns:
        The public IBM PennyLane device.
    """
    url = runtime.snapshot()["url"]
    return IBMDevice(
        wires=wires,
        backend_name="ibm_test",
        api_key="synthetic-key",
        instance_crn=CRN,
        base_url=url,
        auth_url=url + "/auth",
    )


@pytest.mark.parametrize("wires", [2, ["control", "target"], [4, 2]])
def test_subset_wires_and_measurement_order(runtime: RuntimeProxy, wires: int | list[str] | list[int]) -> None:
    """Wire labels map by position while QASM declares the full physical width."""
    device = open_device(runtime, wires)
    first, second = device.wires

    @qml.qnode(device, shots=7)
    def circuit() -> qml.measurements.MeasurementProcess:
        qml.X(first)
        return qml.sample(wires=[second, first])

    np.testing.assert_array_equal(circuit(), [[0, 1]] * 7)
    source = runtime.snapshot()["submissions"][0]["params"]["pubs"][0][0]
    assert "qubit[5] q;" in source
    assert "bit[2] c0;" in source
    assert "x q[0];" in source
    assert "c0[0] = measure q[0];" in source
    assert "c0[1] = measure q[1];" in source
    assert "measure q[2]" not in source
    assert device.submitted_jobs == 1


@pytest.mark.parametrize(
    ("identifier", "backend"),
    [
        ("ibm.default", "ibm_test"),
        ("ibm.berlin", "ibm_berlin"),
        ("ibm.aachen", "ibm_aachen"),
    ],
)
def test_catalogue_entrypoints(
    runtime: RuntimeProxy, monkeypatch: pytest.MonkeyPatch, identifier: str, backend: str
) -> None:
    """PennyLane resolves all installed stable IDs and honors concrete defaults."""
    runtime.set_configuration("backend_name", backend)
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "ibm_test")
    url = runtime.snapshot()["url"]
    device = qml.device(
        identifier, wires=1, api_key="synthetic-key", instance_crn=CRN, base_url=url, auth_url=url + "/auth"
    )
    assert isinstance(device, IBMDevice)
    assert device.device_id == identifier
    assert device.qdmi_device.name() == backend
    assert not runtime.snapshot()["submissions"]


def test_session_overrides_and_existing_device(runtime: RuntimeProxy, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit connection values take precedence and an open device is exclusive."""
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "wrong-key")
    monkeypatch.setenv("IBM_QUANTUM_INSTANCE_CRN", "wrong-crn")
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "wrong-backend")
    original = open_device(runtime)
    adapted = IBMDevice(device=original.qdmi_device, wires=["a", "b"])
    assert adapted.qdmi_device is original.qdmi_device
    with pytest.raises(PennyLaneConfigurationError, match="exclusive"):
        IBMDevice(device=original.qdmi_device, backend_name="ibm_test")
    assert all("wrong-key" not in body.decode() for _, _, body in runtime.snapshot()["requests"])


def test_sampled_measurements(runtime: RuntimeProxy) -> None:
    """Counts, probabilities, expectations, and variances share the sample decoder."""
    device = open_device(runtime)

    @qml.qnode(device, shots=11)
    def circuit() -> tuple[qml.measurements.MeasurementProcess, ...]:
        qml.X(0)
        return qml.counts(wires=[0, 1]), qml.probs(wires=[1, 0]), qml.expval(qml.Z(0)), qml.var(qml.Z(1))

    counts, probabilities, expectation, variance = circuit()
    assert counts == {"10": 11}
    np.testing.assert_array_equal(probabilities, [0, 1, 0, 0])
    assert expectation == -1
    assert variance == 0


def test_shot_vectors(runtime: RuntimeProxy) -> None:
    """Each shot-vector partition creates one job with the requested shot count."""
    device = open_device(runtime, 1)

    @qml.qnode(device, shots=[5, (3, 2)])
    def circuit() -> qml.measurements.MeasurementProcess:
        qml.X(0)
        return qml.counts(wires=0)

    assert circuit() == ({"1": 5}, {"1": 3}, {"1": 3})
    assert [request["params"]["pubs"][0][2] for request in runtime.snapshot()["submissions"]] == [5, 3, 3]


def test_parameter_shift_gradient(runtime: RuntimeProxy) -> None:
    """Bound parameter-shift circuits execute through the native basis."""
    device = open_device(runtime, 1)

    @qml.qnode(device, shots=31, diff_method="parameter-shift")
    def circuit(theta: float) -> qml.measurements.ExpectationMP:
        qml.RY(theta, 0)
        return qml.expval(qml.Z(0))

    theta = pnp.array(math.pi / 2, requires_grad=True)
    assert qml.grad(circuit)(theta) == pytest.approx(-1)
    assert len(runtime.snapshot()["submissions"]) >= 2


@pytest.mark.parametrize("name", ["ecr", "rzz"])
def test_native_gate_declarations(runtime: RuntimeProxy, name: str) -> None:
    """Native ECR and RZZ survive serialization with importable declarations."""
    config = runtime.snapshot()["configuration"]
    config["gates"].append({"name": name, "parameters": ["theta"] if name == "rzz" else [], "coupling_map": [[0, 1]]})
    runtime.set_configuration("gates", config["gates"])
    runtime.set_configuration("basis_gates", [*config["basis_gates"], name])
    device = open_device(runtime)

    @qml.qnode(device, shots=32)
    def circuit() -> qml.measurements.MeasurementProcess:
        if name == "ecr":
            qml.ECR([0, 1])
        else:
            qml.IsingZZ(math.pi / 4, [0, 1])
        return qml.counts(wires=[0, 1])

    assert sum(circuit().values()) == 32
    source = runtime.snapshot()["submissions"][0]["params"]["pubs"][0][0]
    assert f"gate {name}" in source
    assert "q[0], q[1]" in source


def test_invalid_batch_submits_nothing(runtime: RuntimeProxy) -> None:
    """A later unsupported directed pair is rejected before the first submission."""
    device = open_device(runtime)
    valid = qml.tape.QuantumScript([qml.X(0)], [qml.sample(wires=[0, 1])], shots=3)
    invalid = qml.tape.QuantumScript([qml.CNOT([1, 0])], [qml.sample(wires=[0, 1])], shots=3)
    with pytest.raises(PennyLaneValidationError, match="not advertised"):
        device.execute((valid, invalid))
    assert not runtime.snapshot()["submissions"]


def test_failed_batch_cancels_previous_jobs(runtime: RuntimeProxy) -> None:
    """A failed second submission cancels the first and is never retried."""
    device = open_device(runtime, 1)
    tape = qml.tape.QuantumScript([qml.X(0)], [qml.sample(wires=0)], shots=3)
    runtime.set_state("Queued", 2)
    with pytest.raises(PennyLaneExecutionError):
        device.execute((tape, tape, tape))
    assert len(runtime.snapshot()["submissions"]) == 2
    assert runtime.snapshot()["cancellations"] == ["synthetic-1"]


def test_analytic_execution_submits_nothing(runtime: RuntimeProxy) -> None:
    """Analytic measurements fail before any quantum job is submitted."""
    device = open_device(runtime, 1)

    @qml.qnode(device)
    def circuit() -> qml.measurements.MeasurementProcess:
        return qml.expval(qml.Z(0))

    with pytest.raises(PennyLaneValidationError, match="finite"):
        circuit()
    assert not runtime.snapshot()["submissions"]


def test_offline_imports() -> None:
    """Base imports stay lightweight and optional imports never open connections."""
    script = """
import socket
import sys
import ibm.qdmi
assert 'pennylane' not in sys.modules
assert 'qiskit' not in sys.modules
assert 'mqt.core' not in sys.modules
def reject_connection(*args, **kwargs):
    raise AssertionError('Import attempted a network connection')
socket.socket.connect = reject_connection
import ibm.qdmi.pennylane
from importlib.metadata import entry_points
plugins = {
    entry.name: entry.load()
    for entry in entry_points(group='pennylane.plugins') if entry.name.startswith('ibm.')
}
assert set(plugins) == {'ibm.default', 'ibm.berlin', 'ibm.aachen'}
"""
    env = {
        key: value for key, value in os.environ.items() if not key.startswith(("IBM_QUANTUM_", "MQT_CORE_QDMI_CONFIG_"))
    }
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed offline import script
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_qaoa_decomposition(runtime: RuntimeProxy) -> None:
    """Ordinary QAOA gates compile to IBM's basis with matching probabilities."""
    device = open_device(runtime)

    def circuit() -> qml.measurements.ProbabilityMP:
        qml.Hadamard(0)
        qml.Hadamard(1)
        qml.IsingZZ(0.74, wires=[0, 1])
        qml.RX(0.42, 0)
        qml.RX(0.42, 1)
        return qml.probs(wires=[0, 1])

    graph_before = qml.decomposition.enabled_graph()
    observed = qml.QNode(circuit, device, shots=1024)()
    expected = qml.QNode(circuit, qml.device("default.qubit", wires=2))()
    np.testing.assert_allclose(observed, expected, atol=0.04)
    assert qml.decomposition.enabled_graph() == graph_before
    source = runtime.snapshot()["submissions"][0]["params"]["pubs"][0][0]
    assert "sx q[0];" in source
    assert "cx q[0], q[1];" in source


def test_noncommuting_observables(runtime: RuntimeProxy) -> None:
    """Observable basis changes use the same native synthesis as user gates."""
    device = open_device(runtime, 1)

    @qml.qnode(device, shots=1024)
    def circuit() -> tuple[qml.measurements.ExpectationMP, qml.measurements.ExpectationMP]:
        qml.RY(math.pi / 2, 0)
        return qml.expval(qml.X(0)), qml.expval(qml.Y(0))

    np.testing.assert_allclose(circuit(), [1, 0], atol=0.1)
    assert len(runtime.snapshot()["submissions"]) == 2
