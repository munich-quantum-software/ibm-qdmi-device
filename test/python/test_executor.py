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

"""Executor encoding and decoding through the installed native transport."""

from __future__ import annotations

import runpy
import sys
from typing import TYPE_CHECKING

import numpy as np
import pytest

pytest.importorskip("qiskit_ibm_runtime")

from ibm_quantum_schemas.common import CompressedTensorModel
from ibm_quantum_schemas.executor.version_2_0 import ParamsModel, QuantumProgramResultModel
from mqt.core.qdmi import Job
from qiskit import QuantumCircuit
from qiskit.circuit import Delay, Duration, Parameter
from qiskit.circuit.classical import expr
from qiskit.quantum_info import SparsePauliOp
from qiskit_ibm_runtime import QuantumProgram
from qiskit_ibm_runtime.options_models.executor import ExecutorOptions
from qiskit_ibm_runtime.quantum_program.converters import quantum_program_from_2_0
from qiskit_ibm_runtime.results import QuantumProgramResult
from qiskit_service import open_backend
from samplomatic import build
from samplomatic.transpiler import generate_boxing_pass_manager

if TYPE_CHECKING:
    from collections.abc import Iterator

    from qiskit_service import Runtime


def test_missing_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing Runtime decoder reports the optional extra."""
    from ibm.qdmi import executor

    monkeypatch.setitem(sys.modules, "qiskit_ibm_runtime.decoders.defaults", None)
    with pytest.raises(ImportError, match=r"ibm-qdmi\[executor\]"):
        runpy.run_path(str(executor.__file__))


def program() -> QuantumProgram:
    """Build a parameter sweep and a measurement-twirled samplex item.

    Returns:
        A small program with both supported item types.
    """
    circuit = QuantumCircuit(1, 1)
    circuit.rz(Parameter("theta"), 0)
    circuit.measure(0, 0)
    result = QuantumProgram(shots=3)
    arguments = np.array([[0.0], [1.0]])
    result.append_circuit_item(circuit, circuit_arguments=arguments)
    boxed = generate_boxing_pass_manager(enable_gates=False, enable_measures=True).run(circuit)
    template, samplex = build(boxed)
    result.append_samplex_item(
        template, samplex=samplex, samplex_arguments={"parameter_values": arguments}, shape=(2, 2)
    )
    return result


def test_executor_round_trip_preserves_shapes_and_corrections(runtime: Runtime) -> None:
    """Real encoders and decoders preserve both item kinds and correction arrays."""
    samples = np.array([[[False], [True], [False]], [[True], [False], [True]]])
    randomized = np.stack([samples, ~samples])
    flips = np.array([[[[False]], [[True]]], [[[True]], [[False]]]])
    output = QuantumProgramResultModel.model_validate({
        "data": [
            {"results": {"c": CompressedTensorModel.from_numpy(samples)}, "metadata": {}},
            {
                "results": {
                    "c": CompressedTensorModel.from_numpy(randomized),
                    "measurement_flips.c": CompressedTensorModel.from_numpy(flips),
                },
                "metadata": {},
            },
        ],
        "metadata": {"chunk_timing": []},
        "passthrough_data": {"experiment": "synthetic"},
    })
    runtime.set_executor_result(output.model_dump(mode="json"))
    backend = open_backend(runtime)
    executor = backend.executor()
    job = executor.run(program())
    result = job.result(timeout=10)
    assert isinstance(result, QuantumProgramResult)
    np.testing.assert_array_equal(result[0]["c"], samples)
    np.testing.assert_array_equal(result[1]["c"], randomized)
    np.testing.assert_array_equal(result[1]["measurement_flips.c"], flips)
    assert result.passthrough_data == {"experiment": "synthetic"}
    assert job.status() == Job.Status.DONE
    submitted = runtime.snapshot()["submissions"]
    assert len(submitted) == 1
    assert submitted[0]["program_id"] == "executor"
    assert submitted[0]["cost"] == 60
    assert submitted[0]["params"]["schema_version"] == "v2.0"
    assert [item["item_type"] for item in submitted[0]["params"]["quantum_program"]["items"]] == ["circuit", "samplex"]
    retrieved = open_backend(runtime).executor().retrieve_job(job.job_id())
    np.testing.assert_array_equal(retrieved.result(timeout=10)[1]["c"], randomized)
    assert len(runtime.snapshot()["submissions"]) == 1


def test_executor_timeout_cancel_and_submission_failure(runtime: Runtime) -> None:
    """A timed-out wait leaves the job available for explicit cancellation."""
    runtime.set_state("Queued", 0)
    executor = open_backend(runtime).executor()
    job = executor.run(program())
    with pytest.raises(TimeoutError):
        job.result(timeout=1)
    assert job.status() == Job.Status.QUEUED
    job.cancel()
    assert job.status() == Job.Status.CANCELED
    assert runtime.snapshot()["cancellations"] == [job.job_id()]
    runtime.set_state("Queued", 2)
    with pytest.raises(RuntimeError):
        executor.run(program())
    assert len(runtime.snapshot()["submissions"]) == 2


@pytest.mark.parametrize("primitive", ["sampler", "estimator"])
def test_executor_dynamical_decoupling(runtime: Runtime, primitive: str) -> None:
    """Use IBM timing to insert a pair of X pulses in the submitted idle interval."""
    # X spans 32 ticks, including a fractional picosecond.
    runtime.set_configuration("dt", 0.250078125)
    runtime.set_configuration("timing_constraints", {"pulse_alignment": 16})
    runtime.set_properties({
        "qubits": [[{"name": "readout_length", "value": 64.02, "unit": "ns"}] for _ in range(2)],
        "gates": [
            {"gate": gate, "qubits": [qubit], "parameters": [{"name": "gate_length", "value": length, "unit": "ns"}]}
            for qubit in range(2)
            for gate, length in [("x", 8.0025), ("sx", 8.0025), ("rz", 0)]
        ],
    })
    backend = open_backend(runtime)
    dd = {"enable": True}
    if primitive == "sampler":
        idle_qubit = 1
        circuit = QuantumCircuit(2)
        circuit.x([0, 1])
        circuit.barrier()
        for _ in range(4):
            circuit.x(0)
        circuit.barrier()
        circuit.measure_all()
        backend.executor_sampler(options={"dynamical_decoupling": dd}).run([circuit], shots=8)
    else:
        idle_qubit = 0
        circuit = QuantumCircuit(1)
        circuit.x(0)
        circuit.delay(128, 0)
        backend.executor_estimator(options={"dynamical_decoupling": dd, "resilience_level": 0}).run(
            [(circuit, SparsePauliOp("Z"))], precision=0.5
        )

    (submission,) = runtime.snapshot()["submissions"]
    encoded = ParamsModel.model_validate(submission["params"])
    prepared, _ = quantum_program_from_2_0(encoded)
    (item,) = prepared.items
    operations = [entry.operation for entry in item.circuit.data if entry.qubits == (item.circuit.qubits[idle_qubit],)]
    assert sum(operation.name == "x" for operation in operations) == 3
    delay = [operation.duration for operation in operations if isinstance(operation, Delay)]
    assert delay == [16, 32, 16]


@pytest.mark.parametrize(("dt", "message"), [(None, "sampling interval"), (0.25, "delay instructions")])
def test_executor_sampler_requires_timing_and_delay(runtime: Runtime, dt: float | None, message: str) -> None:
    """Reject decoupling before submission without the required capabilities."""
    runtime.set_configuration("dt", dt)
    runtime.set_configuration("supported_instructions", ["measure", "reset"])
    backend = open_backend(runtime)
    circuit = QuantumCircuit(1, 1)
    circuit.measure(0, 0)
    sampler = backend.executor_sampler(options={"dynamical_decoupling": {"enable": True}})
    with pytest.raises(ValueError, match=message):
        sampler.run([circuit])
    assert not runtime.snapshot()["submissions"]


def test_executor_delay_encoding(runtime: Runtime) -> None:
    """The wire preserves typed durations. Ambiguous numeric delays fail locally."""
    executor = open_backend(runtime).executor()
    circuit = QuantumCircuit(1, 1)
    circuit.delay(expr.lift(Duration.ns(5)), 0)
    circuit.measure(0, 0)
    timed = QuantumProgram(shots=4)
    timed.append_circuit_item(circuit)
    executor.run(timed)
    (submission,) = runtime.snapshot()["submissions"]
    decoded, _ = quantum_program_from_2_0(ParamsModel.model_validate(submission["params"]))
    assert decoded.items[0].circuit.data[0].operation == circuit.data[0].operation

    circuit = QuantumCircuit(1, 1)
    with circuit.if_test((circuit.clbits[0], True)):
        circuit.delay(5, 0, unit="ns")
    ambiguous = QuantumProgram(shots=4)
    ambiguous.append_circuit_item(circuit)
    with pytest.raises(ValueError, match="clock ticks"):
        executor.run(ambiguous)

    circuit = QuantumCircuit(1)
    circuit.delay(Parameter("length"), 0)
    sweep = QuantumProgram(shots=4)
    sweep.append_circuit_item(circuit, circuit_arguments=np.array([[32], [64]]))
    with pytest.raises(ValueError, match="clock ticks"):
        executor.run(sweep)
    assert len(runtime.snapshot()["submissions"]) == 1


def test_executor_primitive_job_cancel(runtime: Runtime) -> None:
    """Cancel a running primitive job through its native job ID."""
    runtime.set_state("Running", 0)
    sampler = open_backend(runtime).executor_sampler()
    circuit = QuantumCircuit(1, 1)
    circuit.measure(0, 0)
    job = sampler.run([circuit], shots=8)

    assert job.running()
    assert not job.in_final_state()
    job.cancel()
    assert job.cancelled()
    assert job.in_final_state()
    assert runtime.snapshot()["cancellations"] == [job.job_id()]


def test_executor_invalid_inputs_submit_nothing(runtime: Runtime) -> None:
    """Reject empty programs and options the native transport cannot honor."""
    backend = open_backend(runtime)
    with pytest.raises(ValueError, match="at least one"):
        backend.executor().run(QuantumProgram(shots=3))
    options = ExecutorOptions(environment={"job_tags": ["unsupported"]})
    with pytest.raises(ValueError, match="environment"):
        backend.executor(options=options).run(program())
    options = ExecutorOptions(experimental={"local_mode": True})
    with pytest.raises(ValueError, match="simulation"):
        backend.executor(options=options).run(program())
    options = ExecutorOptions(max_execution_time=10)
    with pytest.raises(ValueError, match="max_execution_time"):
        backend.executor(options=options).run(program())
    options = ExecutorOptions(simulator={"seed_simulator": 7})
    with pytest.raises(ValueError, match="simulation"):
        backend.executor(options=options).run(program())
    assert not runtime.snapshot()["submissions"]


@pytest.mark.parametrize(
    ("options", "message"),
    [({"max_execution_time": 10}, "max_execution_time"), ({"simulator": {"seed_simulator": 7}}, "simulation")],
)
def test_executor_primitives_validate_options_before_preparation(
    runtime: Runtime, options: dict[str, object], message: str
) -> None:
    """Reject transport options before Runtime validates the PUBs."""
    backend = open_backend(runtime)
    with pytest.raises(ValueError, match=message):
        backend.executor_sampler(options=options).run([])
    with pytest.raises(ValueError, match=message):
        backend.executor_estimator(options=options).run([])
    assert not runtime.snapshot()["submissions"]


def test_executor_sampler_snapshots_options_before_consuming_pubs(runtime: Runtime) -> None:
    """Option changes during iteration apply to the next submission."""
    sampler = open_backend(runtime).executor_sampler()

    def pubs() -> Iterator[QuantumCircuit]:
        sampler.options.experimental["local_mode"] = True
        circuit = QuantumCircuit(1, 1)
        circuit.measure(0, 0)
        yield circuit

    sampler.run(pubs(), shots=4)
    (submission,) = runtime.snapshot()["submissions"]
    assert not submission["params"]["options"].get("experimental", {}).get("local_mode")
    with pytest.raises(ValueError, match="simulation"):
        sampler.run([], shots=4)


def test_executor_retrieval_rejects_sampler_job(runtime: Runtime) -> None:
    """The optional decoder cannot reinterpret an ordinary sampler job."""
    backend = open_backend(runtime)
    circuit = QuantumCircuit(1, 1)
    circuit.x(0)
    circuit.measure(0, 0)
    sampler_job = backend.run(circuit, shots=3)
    with pytest.raises(ValueError, match="not an IBM Executor"):
        backend.executor().retrieve_job(sampler_job.job_id())
    assert sampler_job.result().get_counts() == {"1": 3}
    assert runtime.snapshot()["submissions"][0]["program_id"] == "sampler"
