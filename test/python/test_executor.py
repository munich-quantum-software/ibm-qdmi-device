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
from ibm_quantum_schemas.common import CompressedTensorModel
from ibm_quantum_schemas.executor.version_2_0 import QuantumProgramResultModel
from mqt.core.qdmi import Job
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit_ibm_runtime import QuantumProgram
from qiskit_ibm_runtime.options_models.executor import ExecutorOptions
from qiskit_ibm_runtime.results import QuantumProgramResult
from qiskit_service import open_backend
from samplomatic import build
from samplomatic.transpiler import generate_boxing_pass_manager

from ibm.qdmi import executor as adapter

if TYPE_CHECKING:
    from qiskit_service import RuntimeProxy


def test_missing_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing Runtime decoder reports the optional extra."""
    monkeypatch.setitem(sys.modules, "qiskit_ibm_runtime.decoders.quantum_program.decoder", None)
    with pytest.raises(ImportError, match=r"ibm-qdmi\[executor\]"):
        runpy.run_path(str(adapter.__file__))


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


def test_executor_round_trip_preserves_shapes_and_corrections(runtime: RuntimeProxy) -> None:
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


def test_executor_timeout_cancel_and_submission_failure(runtime: RuntimeProxy) -> None:
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


def test_executor_invalid_inputs_submit_nothing(runtime: RuntimeProxy) -> None:
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
    assert not runtime.snapshot()["submissions"]


def test_executor_retrieval_rejects_sampler_job(runtime: RuntimeProxy) -> None:
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
