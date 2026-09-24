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

# ruff: file-ignore[subprocess-without-shell-equals-true]
"""Offline checks for local execution and the Slurm worker protocol."""

from __future__ import annotations

import base64
import math
import pickle  # ruff:ignore[suspicious-pickle-import]
import runpy
import shutil
import subprocess
import sys
import sysconfig
from functools import partial
from typing import TYPE_CHECKING

import pytest
from offline_service import CRN
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, qpy
from qiskit.circuit import Parameter
from qiskit.primitives import BackendEstimatorV2, BackendSamplerV2, DataBin, PrimitiveResult, SamplerPubResult
from qiskit.quantum_info import SparsePauliOp
from qiskit_algorithms import VQEResult
from qiskit_service import open_backend

from ibm.qdmi import (
    _backends,  # ruff: ignore[import-private-name] -- exercise shared primitive construction
    estimator,
    offloader,
    sampler,
)
from ibm.qdmi.qiskit import IBMBackend

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import ModuleType

    from qiskit_service import RuntimeProxy


@pytest.mark.parametrize(
    ("builder", "primitive_type"),
    [(_backends.build_sampler, BackendSamplerV2), (_backends.build_estimator, BackendEstimatorV2)],
)
def test_ibm_primitive_selection(
    runtime: RuntimeProxy,
    monkeypatch: pytest.MonkeyPatch,
    builder: Callable[..., BackendSamplerV2 | BackendEstimatorV2],
    primitive_type: type[BackendSamplerV2 | BackendEstimatorV2],
) -> None:
    """Builders open the selected IBM backend and expose its native primitives."""
    url = runtime.snapshot()["url"]
    monkeypatch.setattr(
        _backends,
        "IBMBackend",
        partial(IBMBackend, api_key="synthetic-key", instance_crn=CRN, base_url=url, auth_url=f"{url}/auth"),
    )
    primitive = builder(simulator=False, backend_name="ibm_test")
    assert isinstance(primitive, primitive_type)
    assert isinstance(primitive.backend, IBMBackend)
    assert primitive.backend.name == "ibm_test"
    assert not runtime.snapshot()["submissions"]


def test_missing_optional_dependency(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Both APIs explain a missing extra before opening a backend or writing inputs."""
    monkeypatch.setitem(sys.modules, "qiskit", None)
    monkeypatch.setenv("IBM_JOBS_DIR", str(tmp_path))
    module = runpy.run_path(str(offloader.__file__))
    for function, args in (("sample", (None,)), ("estimate", (None, None))):
        with pytest.raises(ImportError, match=r"ibm-qdmi\[qiskit\]") as error:
            module[function](*args)
        assert error.value.__cause__ is module["_IMPORT_ERROR"]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (PrimitiveResult([]), "no pubs"),
        (PrimitiveResult([SamplerPubResult(DataBin())]), "Could not extract measurement counts"),
    ],
)
def test_invalid_sampler_result(result: PrimitiveResult[SamplerPubResult], message: str) -> None:
    """Empty results and missing measurement registers cannot produce fabricated counts."""
    with pytest.raises(RuntimeError, match=message):
        offloader.extract_counts(result)


def test_local_sample_registers() -> None:
    """Joint counts preserve classical register order on the local simulator."""
    circuit = QuantumCircuit(QuantumRegister(2), ClassicalRegister(1, "a"), ClassicalRegister(1, "b"))
    circuit.x(1)
    circuit.measure([0, 1], [0, 1])
    assert offloader.sample(circuit, shots=7, local=True, simulator=True) == {"10": 7}


@pytest.mark.parametrize("worker", ["sample", "estimate"])
def test_slurm_roundtrip(
    worker: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The submitted QPY files run through real worker entry functions offline."""
    circuit = QuantumCircuit(1)
    circuit.ry(Parameter("theta") if worker == "estimate" else 0, 0)
    if worker == "sample":
        circuit.measure_all()
    monkeypatch.setenv("IBM_JOBS_DIR", str(tmp_path))
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "sentinel-secret")
    monkeypatch.setenv("IBM_QUANTUM_INSTANCE_CRN", "sentinel-crn")
    monkeypatch.setenv("IBM_SLURM_PARTITION", "site-default")

    def run(
        command: list[str], *, capture_output: bool, check: bool, timeout: float | None
    ) -> subprocess.CompletedProcess[bytes]:
        assert capture_output
        assert not check
        assert timeout == 30
        executable = "ibm-sampler" if worker == "sample" else "ibm-estimator"
        index = command.index(executable)
        assert command[:index] == [
            "srun",
            "--job-name=sample_sim" if worker == "sample" else "--job-name=estim_sim",
            "--nodes=2",
            "--ntasks=1",
            "--partition=explicit",
            "--licenses=ibm:1",
        ]
        assert "sentinel-secret" not in command
        assert "sentinel-crn" not in command
        assert command[-3:] == ["--backend-name", "ibm_test", "--simulator"]
        entry = sampler.main if worker == "sample" else estimator.main
        entry(command[index + 1 :])
        return subprocess.CompletedProcess(command, 0, capsys.readouterr().out.encode(), b"")

    monkeypatch.setattr(subprocess, "run", run)
    if worker == "sample":
        assert offloader.sample(
            circuit,
            shots=7,
            simulator=True,
            backend_name="ibm_test",
            timeout=30,
            nodes=2,
            partition="explicit",
            licenses="ibm:1",
        ) == {"0": 7}
    else:
        result = offloader.estimate(
            circuit,
            SparsePauliOp("Z"),
            maxiter=1,
            simulator=True,
            backend_name="ibm_test",
            timeout=30,
            nodes=2,
            partition="explicit",
            licenses="ibm:1",
        )
        assert isinstance(result, VQEResult)
        assert result.optimal_parameters
        assert result.optimizer_result is not None
        assert result.optimal_circuit is not None
        assert result.eigenvalue is not None
        assert math.isfinite(result.eigenvalue.real)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("worker", ["sample", "estimate"])
@pytest.mark.parametrize("failure", ["exit", "timeout", "empty", "malformed"])
def test_slurm_failure_preserves_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, worker: str, failure: str
) -> None:
    """Transport and decoding failures retain per-job input files."""

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 1)
        return subprocess.CompletedProcess(
            command, 1 if failure == "exit" else 0, b"malformed" if failure == "malformed" else b"", b"worker failed"
        )

    monkeypatch.setenv("IBM_JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", run)
    if worker == "sample":
        with pytest.raises(RuntimeError):
            offloader.sample(QuantumCircuit(1), simulator=True)
    else:
        with pytest.raises(RuntimeError):
            offloader.estimate(QuantumCircuit(1), SparsePauliOp("Z"), simulator=True)
    (job_dir,) = tmp_path.iterdir()
    assert len(list(job_dir.iterdir())) == (1 if worker == "sample" else 2)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_counts_submit_nothing(value: int, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Invalid counts fail before serialization or backend construction."""
    monkeypatch.setenv("IBM_JOBS_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="shots"):
        offloader.sample(QuantumCircuit(1), shots=value)
    with pytest.raises(ValueError, match="maxiter"):
        offloader.estimate(QuantumCircuit(1), SparsePauliOp("Z"), maxiter=value)
    with pytest.raises(ValueError, match="nodes"):
        offloader.sample(QuantumCircuit(1), nodes=value)
    assert not list(tmp_path.iterdir())


def test_ibm_vqe_layout_and_execution_cap(runtime: RuntimeProxy, monkeypatch: pytest.MonkeyPatch) -> None:
    """VQE transpiles a parameterized ansatz and keeps the native execution cap."""
    backend = open_backend(runtime)
    monkeypatch.setattr(offloader, "build_estimator", lambda **_kwargs: backend.estimator(default_precision=0.25))
    original_transpile = offloader.transpile
    monkeypatch.setattr(
        offloader,
        "transpile",
        lambda circuit, target, **kwargs: original_transpile(circuit, target, initial_layout=[4], **kwargs),
    )
    circuit = QuantumCircuit(1)
    circuit.ry(Parameter("theta"), 0)
    result = offloader.estimate(circuit, SparsePauliOp("Z"), maxiter=1, local=True)
    assert isinstance(result, VQEResult)
    assert result.optimal_circuit is not None
    assert result.optimal_circuit.num_qubits == backend.num_qubits
    submissions = runtime.snapshot()["submissions"]
    assert submissions
    assert all(request["cost"] == 60 for request in submissions)


@pytest.mark.parametrize("module", [sampler, estimator])
def test_worker_backend_selection(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Worker arguments select IBM directly without forwarding credentials."""
    circuit_path = tmp_path / "circuit.qpy"
    with circuit_path.open("wb") as stream:
        qpy.dump(QuantumCircuit(1), stream)
    observable_path = tmp_path / "operator.pkl"
    observable_path.write_bytes(pickle.dumps(SparsePauliOp("Z")))
    calls = []
    function = "sample" if module is sampler else "estimate"
    monkeypatch.setattr(module, function, lambda *_args, **kwargs: calls.append(kwargs) or {"0": 3})
    argv = [str(circuit_path)]
    argv += ["--shots", "3"] if module is sampler else [str(observable_path), "--maxiter", "1"]
    module.main([*argv, "--backend-name", "ibm_selected"])
    assert calls[0]["backend_name"] == "ibm_selected"
    assert calls[0]["local"] is True
    assert calls[0]["simulator"] is False
    assert pickle.loads(base64.b64decode(capsys.readouterr().out)) == {"0": 3}  # ruff:ignore[suspicious-pickle-usage]


@pytest.mark.parametrize("worker", ["ibm-sampler", "ibm-estimator"])
def test_installed_worker(worker: str, tmp_path: Path) -> None:
    """Installed console entry points execute local simulator workloads."""
    executable = shutil.which(worker, path=sysconfig.get_path("scripts"))
    assert executable is not None
    circuit = QuantumCircuit(1)
    circuit.ry(Parameter("theta") if worker == "ibm-estimator" else 0, 0)
    if worker == "ibm-sampler":
        circuit.measure_all()
    path = tmp_path / "circuit.qpy"
    with path.open("wb") as stream:
        qpy.dump(circuit, stream)
    command = [executable, str(path)]
    if worker == "ibm-sampler":
        command += ["--shots", "3"]
    else:
        observable = tmp_path / "operator.pkl"
        observable.write_bytes(pickle.dumps(SparsePauliOp("Z")))
        command += [str(observable), "--maxiter", "1"]
    process = subprocess.run([*command, "--simulator"], check=True, capture_output=True, timeout=60)
    result = pickle.loads(base64.b64decode(process.stdout))  # ruff:ignore[suspicious-pickle-usage]
    if worker == "ibm-sampler":
        assert result == {"0": 3}
    else:
        assert isinstance(result, VQEResult)
        assert result.eigenvalue is not None
        assert math.isfinite(result.eigenvalue.real)


@pytest.mark.parametrize("partition_env", [None, "site-quantum"])
def test_slurm_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, partition_env: str | None) -> None:
    """Site partition defaults preserve one worker and omit optional arguments."""
    monkeypatch.setenv("IBM_JOBS_DIR", str(tmp_path))
    monkeypatch.delenv("IBM_SLURM_PARTITION", raising=False)
    if partition_env is not None:
        monkeypatch.setenv("IBM_SLURM_PARTITION", partition_env)

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert f"--partition={partition_env or 'quantum'}" in command
        assert "--nodes=1" in command
        assert "--ntasks=1" in command
        assert "--backend-name" not in command
        assert not any(arg.startswith("--licenses") for arg in command)
        return subprocess.CompletedProcess(command, 0, base64.b64encode(pickle.dumps({"0": 1})), b"")

    monkeypatch.setattr(subprocess, "run", run)
    assert offloader.sample(QuantumCircuit(1), simulator=True) == {"0": 1}
