# Copyright (c) 2025 - 2026 IQM Finland Oy
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

# ruff:file-ignore[subprocess-without-shell-equals-true]
"""Offload Qiskit workloads (sampling and estimation) using Slurm."""

from __future__ import annotations

import base64
import contextlib
import os
import pickle  # ruff:ignore[suspicious-pickle-import]
import subprocess
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, cast

_IMPORT_ERROR: ImportError | None = None
try:
    from qiskit import qpy, transpile
    from qiskit_algorithms import VQE
    from qiskit_algorithms.optimizers import SciPyOptimizer

    from ._backends import TRANSPILE_OPTIMIZATION_LEVEL, build_estimator, build_sampler
except ImportError as e:
    _IMPORT_ERROR = e

if TYPE_CHECKING:
    from qiskit.circuit import QuantumCircuit
    from qiskit.primitives import BitArray, PrimitiveResult, SamplerPubResult
    from qiskit.quantum_info import SparsePauliOp
    from qiskit_algorithms import VQEResult

_DEFAULT_PARTITION = "quantum"
_DEFAULT_NODES = 1


def extract_counts(primitive_result: PrimitiveResult[SamplerPubResult]) -> dict[str, int]:
    """Extract joint counts from the native sampler's single submitted circuit.

    Returns:
        Joint bitstrings in Qiskit's register order, mapped to shot counts.

    Raises:
        RuntimeError: If the result is empty or has no classical registers with counts.
    """
    if not primitive_result:
        msg = "Primitive result contained no pubs."
        raise RuntimeError(msg)
    try:
        return cast("BitArray", primitive_result[0].join_data()).get_counts()
    except (TypeError, ValueError) as e:
        msg = f"Could not extract measurement counts: {e}"
        raise RuntimeError(msg) from e


def _get_jobs_dir() -> Path:
    """Return IBM_JOBS_DIR or ~/.qdmi_jobs without creating it."""
    return Path(os.getenv("IBM_JOBS_DIR") or Path.home() / ".qdmi_jobs")


def _new_job_dir() -> Path:
    """Create and return a fresh per-call job directory on the shared jobs filesystem.

    Returns:
        Path to the newly created job directory.
    """
    jobs_dir = _get_jobs_dir()
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_dir = jobs_dir / uuid.uuid4().hex
    job_dir.mkdir(mode=0o700, exist_ok=False)
    return job_dir


def _licenses_arg(licenses: str | None) -> list[str]:
    """Return the optional Slurm license request."""
    return [f"--licenses={licenses}"] if licenses else []


def _resolve_partition(partition: str | None) -> str:
    """Return the explicit partition, site default, or quantum partition."""
    return partition or os.getenv("IBM_SLURM_PARTITION") or _DEFAULT_PARTITION


def _run_srun(
    command: list[str],
    job_dir: Path,
    *,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run *command* via `srun` and return the completed process.

    Failed jobs retain their inputs at *job_dir* for debugging.

    Returns:
        The completed process, with captured stdout/stderr.

    Raises:
        RuntimeError: If the Slurm job times out or returns a non-zero exit
            code.
    """
    try:
        process = subprocess.run(command, capture_output=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        msg = f"Slurm job timed out after {timeout}s (job inputs kept at {job_dir} for debugging)"
        raise RuntimeError(msg) from e
    if process.returncode != 0:
        stderr = process.stderr.decode().strip()
        msg = f"Error while submitting job to Slurm: {stderr} (job inputs kept at {job_dir} for debugging)"
        raise RuntimeError(msg)
    return process


def _load_pickled_result(process: subprocess.CompletedProcess[bytes]) -> object:
    """Load a base64-encoded pickle from a trusted Slurm worker.

    The submitting process and worker must use compatible environments.

    Returns:
        The worker's native Qiskit result.

    Raises:
        RuntimeError: If the worker output is empty or cannot be decoded.
    """
    stdout = process.stdout.strip()
    if not stdout:
        msg = "No output from the job."
        raise RuntimeError(msg)
    try:
        return pickle.loads(base64.b64decode(stdout, validate=True))  # ruff:ignore[suspicious-pickle-usage]
    except Exception as e:
        msg = f"Error parsing the output: {e}"
        raise RuntimeError(msg) from e


def _validate_positive(**values: int) -> None:
    """Reject invalid counts before allocating a job or opening a backend.

    Raises:
        ValueError: A count is not a positive integer.
    """
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            msg = f"{name} must be a positive integer."
            raise ValueError(msg)


def sample(
    qc: QuantumCircuit,
    shots: int = 1024,
    *,
    local: bool = False,
    simulator: bool = False,
    timeout: float | None = None,
    backend_name: str | None = None,
    licenses: str | None = None,
    partition: str | None = None,
    nodes: int = _DEFAULT_NODES,
) -> dict[str, int]:
    """Sample from a quantum circuit.

    Run in this process with ``local=True`` or submit a blocking Slurm job.
    Slurm workers need a shared ``IBM_JOBS_DIR`` and compatible environments.

    Args:
        qc: The quantum circuit to run.
        shots: The number of shots to run. Default is 1024.
        local: Run in this process instead of Slurm.
        simulator: Use MQT Core's DDSIM backend.
        timeout: Slurm wait limit in seconds; does not cancel remote execution.
        backend_name: IBM backend, overriding ``IBM_QUANTUM_BACKEND``;
            ignored for simulation.
        licenses: Slurm license request in ``name[:count]`` syntax.
        partition: Slurm partition; defaults to ``IBM_SLURM_PARTITION`` or ``quantum``.
        nodes: Slurm allocation size. The worker runs as one task.

    Returns:
        A dictionary of measurement counts.

    Raises:
        ImportError: If Qiskit or the QDMI backend plugins are not installed.
        RuntimeError: Propagated from job submission or result decoding.
    """  # ruff:ignore[docstring-extraneous-exception]
    if _IMPORT_ERROR is not None:
        msg = (
            "Failed to import Qiskit and QDMI backend plugins. "
            "Ensure that `ibm-qdmi` is installed with the `qiskit` extra, e.g., via `uv pip install ibm-qdmi[qiskit]`."
        )
        raise ImportError(msg) from _IMPORT_ERROR
    _validate_positive(shots=shots, nodes=nodes)
    if local:
        sampler = build_sampler(simulator=simulator, backend_name=backend_name)
        qc_for_execution = transpile(qc, sampler.backend, optimization_level=TRANSPILE_OPTIMIZATION_LEVEL)
        job = sampler.run([(qc_for_execution,)], shots=shots)
        return extract_counts(job.result())

    job_dir = _new_job_dir()

    qc_path = job_dir / "qc.qpy"
    with qc_path.open("wb") as f:
        qpy.dump(qc, f)

    job_name = "sample_sim" if simulator else "sample_qc"
    command = [
        "srun",
        f"--job-name={job_name}",
        f"--nodes={nodes}",
        "--ntasks=1",
        f"--partition={_resolve_partition(partition)}",
        *_licenses_arg(licenses),
        "ibm-sampler",
        str(qc_path.absolute()),
        "--shots",
        str(shots),
    ]
    if backend_name is not None:
        command.extend(["--backend-name", backend_name])
    if simulator:
        command.append("--simulator")

    process = _run_srun(command, job_dir, timeout=timeout)

    result = _load_pickled_result(process)

    qc_path.unlink(missing_ok=True)
    with contextlib.suppress(OSError):
        job_dir.rmdir()

    return cast("dict[str, int]", result)


def estimate(
    ansatz: QuantumCircuit,
    operator: SparsePauliOp,
    maxiter: int = 80,
    *,
    local: bool = False,
    simulator: bool = False,
    timeout: float | None = None,
    backend_name: str | None = None,
    licenses: str | None = None,
    partition: str | None = None,
    nodes: int = _DEFAULT_NODES,
) -> VQEResult:
    """Estimate the optimal parameters for a given ansatz circuit and operator.

    Run in this process with ``local=True`` or submit a blocking Slurm job.
    Slurm workers need a shared ``IBM_JOBS_DIR`` and compatible environments.
    Pickled operators and results require trusted workers and storage.

    Args:
        ansatz: The ansatz circuit to run.
        operator: The operator to run.
        maxiter: The maximum number of iterations for the optimization.
            Default is 80.
        local: Run in this process instead of Slurm.
        simulator: Use MQT Core's DDSIM backend.
        timeout: Slurm wait limit in seconds; does not cancel remote execution.
        backend_name: IBM backend, overriding ``IBM_QUANTUM_BACKEND``;
            ignored for simulation.
        licenses: Slurm license request in ``name[:count]`` syntax.
        partition: Slurm partition; defaults to ``IBM_SLURM_PARTITION`` or ``quantum``.
        nodes: Slurm allocation size. The worker runs as one task.

    Returns:
        The VQE result, including the optimal parameters and eigenvalue.

    Raises:
        ImportError: If Qiskit or the QDMI backend plugins are not installed.
        RuntimeError: If there is an error while submitting the job to Slurm or parsing the output.
    """  # ruff:ignore[docstring-extraneous-exception]
    if _IMPORT_ERROR is not None:
        msg = (
            "Failed to import Qiskit and QDMI backend plugins. "
            "Ensure that `ibm-qdmi` is installed with the `qiskit` extra, e.g., via `uv pip install ibm-qdmi[qiskit]`."
        )
        raise ImportError(msg) from _IMPORT_ERROR
    _validate_positive(maxiter=maxiter, nodes=nodes)
    if local:
        estimator = build_estimator(simulator=simulator, backend_name=backend_name)
        mapped = transpile(ansatz, estimator.backend, optimization_level=TRANSPILE_OPTIMIZATION_LEVEL)
        # Retain Qiskit's tolerance without its removed SciPy iprint option.
        optimizer = SciPyOptimizer(method="L-BFGS-B", options={"maxiter": maxiter, "ftol": 10 * sys.float_info.epsilon})
        vqe = VQE(estimator, mapped, optimizer)
        return vqe.compute_minimum_eigenvalue(operator=operator)

    job_dir = _new_job_dir()

    qc_path = job_dir / "ansatz.qpy"
    with qc_path.open("wb") as f:
        qpy.dump(ansatz, f)

    operator_path = job_dir / "operator.pkl"
    with operator_path.open("wb") as f:
        pickle.dump(operator, f)

    job_name = "estim_sim" if simulator else "estim_qc"
    command = [
        "srun",
        f"--job-name={job_name}",
        f"--nodes={nodes}",
        "--ntasks=1",
        f"--partition={_resolve_partition(partition)}",
        *_licenses_arg(licenses),
        "ibm-estimator",
        str(qc_path.absolute()),
        str(operator_path.absolute()),
        "--maxiter",
        str(maxiter),
    ]
    if backend_name is not None:
        command.extend(["--backend-name", backend_name])
    if simulator:
        command.append("--simulator")

    process = _run_srun(command, job_dir, timeout=timeout)

    result = _load_pickled_result(process)

    qc_path.unlink(missing_ok=True)
    operator_path.unlink(missing_ok=True)
    with contextlib.suppress(OSError):
        job_dir.rmdir()

    return cast("VQEResult", result)
