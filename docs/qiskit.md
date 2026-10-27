# Qiskit integration

{py:class}`~ibm.qdmi.qiskit.IBMBackend` adapts the installed native device
through MQT Core's `QDMIBackend` and `QDMIJob`. Install the optional extra:

```console
uv pip install "ibm-qdmi[qiskit]"
```

Importing the adapter is offline. Constructing a backend reads live metadata;
executing circuits creates paid quantum jobs. The examples below require
authorized IBM access and are not executed during documentation builds.

## Select a backend

Supply `IBM_QUANTUM_API_KEY` and `IBM_QUANTUM_INSTANCE_CRN` through the process
environment or a secret manager. Keep their values out of source code.

```python
from ibm.qdmi.qiskit import IBMBackend

backend = IBMBackend("ibm.berlin")
# Alternatively: IBMBackend("ibm.aachen")
# Generic selection: IBMBackend(backend_name="ibm_berlin")
```

Concrete catalogue entries select their named backend. The generic `ibm.default`
entry requires `backend_name`, an administrator's catalogue setting, or
`IBM_QUANTUM_BACKEND`. Explicit connection arguments override catalogue settings
and environment defaults. For credential precedence and trusted endpoint
overrides, see [session configuration](api.md#session-configuration).

Each construction opens a fresh session. `IBMBackend(device=device)` instead
adapts an already-open device and rejects connection overrides. `device_id` and
`provider` can supply identity metadata for that device; registered devices also
support the inherited `IBMBackend.from_device_id()` factory.

## Transpile and execute

Transpile against the backend's target, which describes its native gates,
physical connectivity, and available calibrations:

```python
from qiskit import QuantumCircuit, transpile

circuit = QuantumCircuit(2, 2, name="bell", metadata={"experiment": "example"})
circuit.h(0)
circuit.cx(0, 1)
circuit.measure([0, 1], [0, 1])
compiled = transpile(circuit, backend, optimization_level=1, seed_transpiler=7)
job = backend.run(compiled, shots=128, memory=True)
result = job.result()
counts = result.get_counts()
shots = result.get_memory()
```

Serialization preserves the full physical width and measurement destinations.
Results preserve circuit names, metadata, classical register boundaries, and bit
order. Unsupported instructions, control flow, unbound parameters, and invalid
site tuples fail before submission. Scheduled delays are unsupported.

`shots` must be positive and defaults to 1,024. Set `memory=True` to retrieve
ordered samples, including leading zeros. Compatible circuits share one Sampler
V2 job with a 60-second QPU execution cap, independent of queue time. Direct
QDMI callers can change the [execution-time cap](api.md#jobs-and-results) and
[dynamical decoupling](api.md#dynamical-decoupling).

## Parameters and batches

```python
import math

from qiskit.circuit import Parameter

theta = Parameter("theta")
parameterized = QuantumCircuit(1, 1)
parameterized.ry(theta, 0)
parameterized.measure(0, 0)
compiled = transpile(parameterized, backend, optimization_level=1)
job = backend.run(
    [compiled, compiled],
    parameter_values=[{theta: 0.0}, {theta: math.pi}],
    shots=128,
    memory=True,
)
results = job.result()
first_counts = results.get_counts(0)
second_memory = results.get_memory(1)
```

Bind circuits yourself or supply one parameter mapping or ordered value sequence
per circuit. The adapter validates and serializes the entire batch before its
first submission. A submission or result failure retains the batch handle on the
execution exception for inspection and explicit cancellation. Automatic retries
are disabled by default. `max_retries` allows bounded replacements of confirmed
failed entries. A lost response can mean IBM accepted a job; unknown outcomes
are never automatically replaced.

## Sampler and estimator

`backend.sampler()` and `backend.estimator()` return Qiskit's `BackendSamplerV2`
and `BackendEstimatorV2`. They execute through the same QDMI backend and support
parameterized PUBs. Primitive expansion can create multiple native jobs, each
with its own execution cap. Agree on a total budget before running large sweeps
or observable sets.

```python
import numpy as np

sampler = backend.sampler(default_shots=128)
sampled = sampler.run([(compiled, {theta: np.array([[0.0], [math.pi]])})]).result()
register_counts = sampled[0].data[compiled.cregs[0].name].get_counts(0)
```

The estimator uses finite shots and may expand observable measurements into
separate circuits. Apply the transpilation layout to observables:

```python
from qiskit.quantum_info import SparsePauliOp

preparation = QuantumCircuit(1)
preparation.ry(theta, 0)
mapped = transpile(preparation, backend, optimization_level=1)
observable = SparsePauliOp("Z").apply_layout(mapped.layout)
estimated = (
    backend
    .estimator()
    .run(
        [(mapped, observable, {theta: np.array([[0.0], [math.pi]])})],
        precision=0.125,
    )
    .result()
)
expectations = estimated[0].data["evs"]
standard_errors = estimated[0].data["stds"]
```

A smaller positive precision requests more shots; it does not guarantee a
hardware error bound. See Qiskit's
[backend primitive interfaces](https://quantum.cloud.ibm.com/docs/en/guides/get-started-with-backend-primitives).
IBM Runtime sessions, batching modes, mitigation controls, and provider-specific
Runtime primitives are outside this interface.

## Status, cancellation, and retrieval

Use the shared job's `status()`, `cancel()`, and `job_id()` methods.
`job.result()` waits for completion. For an explicit native timeout or
retrieval, use the device interface:

```python
identifier = job.job_id()
fresh_backend = IBMBackend("ibm.berlin")
retrieved = fresh_backend.device.retrieve_job_by_id(identifier)
retrieved.wait(900)
ordered_shots = retrieved.get_shots()
```

Retrieval makes no new submission and requires the original backend and
instance. It returns a native QDMI job; remote input does not preserve Python
circuit names or metadata. For a batch, `job_id()` identifies its first native
job. Timeout does not imply cancellation. Call `cancel()` explicitly when
abandoning pending work. Freeing local handles does not cancel remote jobs. See
[native job contracts](api.md#jobs-and-results).

## Optional Executor primitive

Install `ibm-qdmi[executor]` to submit IBM `QuantumProgram` objects through the
same native QDMI session. Executor uses the beta v2.0 schema and IBM Runtime's
encoder and decoder. Pass IBM's
[ExecutorOptions](https://quantum.cloud.ibm.com/docs/api/qiskit-ibm-runtime/options-models-executor-options)
to `backend.executor(options=...)` to configure supported execution options.

```python
from qiskit_ibm_runtime import QuantumProgram

program = QuantumProgram(shots=128)
program.append_circuit_item(compiled)
executor = backend.executor()
job = executor.run(program)
result = job.result(timeout=300)
samples = result[0][compiled.cregs[0].name]
```

Prepare circuits for the selected backend before adding circuit or Samplomatic
samplex items. Results use IBM's native representation, including dimensions,
register names, and correction metadata. Apply measurement-twirling corrections
explicitly; the adapter does not convert results into counts.

`job.status()` returns a QDMI job status. `job.cancel()` cancels the remote job.
Retrieve a job with `executor.retrieve_job(job.job_id())`, including from a
fresh backend session. A result timeout raises `TimeoutError` and leaves the
remote job active; cancel it explicitly when needed.

This path submits independent jobs. Runtime sessions, Runtime batches, and local
Executor simulation are not provided. Nondefault environment options are
rejected before submission. The Python adapter uses the native 60-second
execution cap; direct C callers can change it through the custom job parameter.
Execution and experimental payload options are encoded by IBM's library and
validated by the service. Shots come from the program and apply to every
configuration, not to the program's total workload.
