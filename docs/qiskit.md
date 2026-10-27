# Qiskit integration

{py:class}`~ibm.qdmi.qiskit.IBMBackend` adapts the installed native device
through MQT Core's `QDMIBackend` and `QDMIJob`. See the
[MQT Core Qiskit guide](https://mqt.readthedocs.io/projects/core/en/latest/qdmi/qdmi_backend.html)
for parameter binding, batches, primitives, and result handling. Install the IBM
extra:

```console
uv pip install "ibm-qdmi[qiskit]"
```

Importing the adapter is offline. Constructing a remote backend reads live
metadata; remote execution creates paid quantum jobs. The examples below require
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

For local development, install the optional mock support on a platform supported
by Qiskit Aer:

```console
uv pip install 'ibm-qdmi[mock]'
```

```python
backend = IBMBackend(backend_name="fake_manila")
```

The backend uses Runtime's bundled
[fake device snapshots](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/fake-provider)
and runs QASM3 Sampler jobs and Executor programs through the installed native
device. The same transpilation, Sampler, Estimator, and Executor interfaces work
locally; PennyLane's `IBMDevice` and offloader workers accept `backend_name` as
well. No IBM account is needed. `IBM_QUANTUM_BACKEND=fake_manila` also selects a
fake for `ibm.default`; explicit connection settings instead select a remote
service. Unknown fake names fail locally. See `python -m examples.runtime_mock`
for a complete example.

Fakes are snapshots, not current calibrations. Use small targets: simulation
cost can grow exponentially with qubit count. Aer wheel availability limits
supported platforms and Python versions. The local Sampler rejects enabled
dynamical decoupling and twirling. One service per target stays alive until
process exit, so jobs can be retrieved from another backend object while that
process runs. The service binds to `127.0.0.1` with a temporary credential;
include that address in `no_proxy` if an HTTP proxy is configured.

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

The backend uses QPY, preserving conditions, global phase, classical registers,
and physical indices. Direct QDMI submissions also accept OpenQASM 3 with
physical indices and conditional operations. Results preserve circuit names,
metadata, classical register boundaries, and bit order. Unsupported
instructions, unbound parameters, invalid site tuples, and scheduled delays fail
before submission.

Backends advertising `if_else` support conditional execution through QPY and
OpenQASM 3. Conditions compare one classical bit or a register of at most 32
bits with an integer. Both branches preserve physical qubit mappings:

```python
circuit = QuantumCircuit(2, 2)
circuit.h(0)
circuit.measure(0, 0)
with circuit.if_test((circuit.clbits[0], True)):
    circuit.x(1)
circuit.measure(1, 1)
compiled = transpile(circuit, backend, optimization_level=1)
counts = backend.run(compiled, shots=128).result().get_counts()
```

Ideal samples are `00` and `11`. Nested conditionals, measurements or resets
inside branches, loops, switches, classical expressions, and `Store` are
unsupported. The whole batch is validated before submission. See IBM's
[dynamic-circuit limits](https://quantum.cloud.ibm.com/docs/en/guides/execute-dynamic-circuits#quantum-compute-limitations).

`shots` must be positive and defaults to 1,024. Set `memory=True` to retrieve
ordered samples, including leading zeros. Compatible circuits share one Sampler
V2 job with a 60-second QPU execution cap, independent of queue time. Direct
QDMI callers can change the [execution-time cap](api.md#jobs-and-results) and
[dynamical decoupling](api.md#dynamical-decoupling).

For retrieval, use `backend.device.retrieve_job_by_id(identifier)` with the
original backend and IBM instance. Retrieval submits no new work and returns a
native QDMI job. Remote inputs do not retain Python circuit names or metadata.
Timeouts and freeing local handles do not cancel remote jobs; cancel explicitly
when abandoning pending work. See
[native job contracts](api.md#jobs-and-results).

`backend.sampler()` and `backend.estimator()` use Qiskit's backend primitives.
Each expanded native job has its own execution cap. Agree on a total budget
before running parameter sweeps or observable sets. IBM Runtime sessions,
batching modes, mitigation controls, and provider-specific Runtime primitives
are outside this interface.

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
