# Qiskit integration

{py:class}`~ibm.qdmi.qiskit.IBMBackend` adapts the installed native device
through MQT Core's `QDMIBackend` and `QDMIJob`. Install the optional extra from
the source checkout:

```console
uv pip install '.[qiskit]'
```

The extra uses `mqt-core[qiskit]~=4.0.0`. The base package remains usable
without Qiskit; `qiskit-ibm-runtime` is not required. Imports do not open
sessions or contact IBM. Constructing a backend reads live metadata. Executing
circuits creates paid quantum jobs. These examples are not executed during
documentation builds. Quantum execution remains unverified live until the gated
checks pass.

## Select a backend

Supply `IBM_QUANTUM_API_KEY` and `IBM_QUANTUM_INSTANCE_CRN` through the process
environment or a secret manager. Keep their values out of source code.

```python
from ibm.qdmi.qiskit import IBMBackend

backend = IBMBackend("ibm.berlin")
# Alternatively: IBMBackend("ibm.aachen")
# Generic selection: IBMBackend(backend_name="ibm_berlin")
```

The generic `ibm.default` entry uses `backend_name`, `IBM_QUANTUM_BACKEND`, or
the administrator's registered backend default, in that order. A missing
selection fails during native session initialization before contacting IBM.
Concrete catalogue entries select their named backend. Explicit `api_key`,
`instance_crn`, and `backend_name` arguments override defaults. Normally omit
`base_url` and `auth_url`; the native library derives the region from the CRN.
Trusted endpoint overrides support applications such as loopback testing. See
[session configuration](api.md#session-configuration).

Use `IBMBackend(device=device)` to adapt an already-open IBM QDMI device. An
open device is exclusive with connection overrides. `device_id` and `provider`
may supply identity metadata, including through the inherited
`IBMBackend.from_device_id()` factory for registered devices. Registration
preserves administrator definitions in MQT Core's driver. Each normal
construction creates a fresh session.

Credentials read from the environment become explicit native session parameters
and override registered defaults. Adapt an already-open device to preserve
authentication configured directly through QDMI.

## Transpile and execute

The target uses physical indices, native gate signatures and applicable site
tuples, connectivity, and available durations and errors. Measurement and reset
appear only when advertised. Barriers are directives. Missing gate metadata is
not treated as unrestricted support.

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

Transpile against the selected backend before submission. Serialization retains
the full physical register, including idle qubits, and all measurement
destinations. It uses stable internal classical register names; Qiskit results
retain the original register names, boundaries, and classical-bit order. Global
phase does not affect classified samples and is omitted. Native instructions
outside `stdgates.inc` retain their gate declarations so that IBM can import the
program without external definitions.

`shots` must be a positive integer and defaults to 1,024. `memory` defaults to
false. Requested memory contains genuine ordered samples, including leading
zeros, and agrees with counts. Circuit names, metadata, and experiment order are
preserved. Unsupported instructions, control flow, unbound parameters, and
unsupported site tuples fail before submission. Scheduled delays are outside the
current native contract.

Each circuit creates one Sampler V2 job with a 60-second QPU execution cap,
independent of queue time. This applies separately to every circuit in a batch.
Direct QDMI callers can set the
[custom execution-time parameter](api.md#jobs-and-results) and
[dynamical-decoupling options](api.md#dynamical-decoupling). The Qiskit path
retains the shared `shots` and `memory` execution options.

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
first submission. Serialization lives in `ibm.qdmi.serializers`; backend, job,
and primitive orchestration use MQT Core. A later submission failure triggers
cancellation attempts for earlier jobs. Submission is never automatically
retried. A lost response can mean IBM accepted a job; inspect the platform
before replacing it.

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
