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
metadata; remote execution creates paid quantum jobs and requires authorized IBM
access.

## Select a backend

For an on-premises Quantum System API service, provide the protocol and storage
configuration explicitly:

```python
import os
from ibm.qdmi.qiskit import IBMBackend

backend = IBMBackend(
    backend_name=os.environ["IBM_QUANTUM_BACKEND"],
    api_key=os.environ["IBM_QUANTUM_API_KEY"],
    instance_crn=os.environ["IBM_QUANTUM_INSTANCE_CRN"],
    base_url=os.environ["IBM_QUANTUM_SYSTEM_URL"],
    auth_url=os.environ["IBM_QUANTUM_AUTH_URL"],
    access_mode="quantum-system",
    storage_config=os.environ["IBM_QUANTUM_STORAGE_CONFIG"],
)
```

These environment names configure this example; endpoint and storage values are
passed as explicit session settings. `IBMDevice` accepts the same arguments. See
[Quantum System configuration](api.md#quantum-system-api) for the private
storage file and supported features. Ordinary cloud construction stays
unchanged.

Use this backend in the execution example below.

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

For local development, install the optional mock support:

```console
uv pip install 'ibm-qdmi[mock]'
```

```python
backend = IBMBackend(backend_name="fake_manila")
```

The backend uses Runtime's bundled
[fake device snapshots](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/fake-provider)
and runs QPY or OpenQASM 3 Sampler jobs and Executor programs through the
installed native device. The same transpilation, Sampler, Estimator, and
Executor interfaces work locally; PennyLane's `IBMDevice` accepts `backend_name`
as well. No IBM account is needed. `IBM_QUANTUM_BACKEND=fake_manila` also
selects a fake for `ibm.default`; explicit connection settings instead select a
remote service. Unknown fake names fail locally.

OpenQASM 3 input is parsed by MQT Core. Classical output bits must be assigned
before they are returned; uninitialized bits have no implicit zero value.

Fake metadata supplies connectivity and calibration properties; MQT Core samples
ideal circuits without noise. Use small workloads: simulation can grow
exponentially with circuit size. The mock rejects server-side Sampler decoupling
and twirling. Literal delays advance the circuit without changing its ideal
state. The mock checks circuits against the selected device’s instruction set
and rejects nonliteral delays. Executor jobs on the mock require per-shot qubit
initialization and cannot return scheduler timing or stretch values. The mock
returns classified Executor measurements. Requests are limited to 16 MiB.
Pending jobs can be cancelled; running simulations finish normally. One loopback
service per fake stays alive until process exit, so another backend object can
retrieve its jobs. The service binds to `127.0.0.1` with a temporary credential;
include that address in `no_proxy` if an HTTP proxy is configured.

## Compile and execute

Follow MQT Core's
[compile-and-run guide](https://mqt.readthedocs.io/projects/core/en/latest/qdmi/qdmi_backend.html)
with the selected IBM backend:

```python
from qiskit import QuantumCircuit

circuit = QuantumCircuit(2, 2, name="bell", metadata={"experiment": "example"})
circuit.h(0)
circuit.cx(0, 1)
circuit.measure([0, 1], [0, 1])
compiled = backend.compile(circuit)
job = backend.run(compiled, shots=128, memory=True)
result = job.result()
counts = result.get_counts()
shots = result.get_memory()
```

Cloud sessions use QPY, preserving conditions, global phase, classical
registers, and physical indices. Quantum System sessions use OpenQASM 3. Direct
QDMI submissions also accept OpenQASM 3 with physical indices and conditional
operations. Results preserve circuit names, metadata, classical register
boundaries, and bit order. Unsupported instructions, unbound parameters, and
invalid site tuples fail before submission.

`run()` validates and serializes native instructions; it does not compile or
route them. Qiskit's `transpile(circuit, backend)` uses the same target as the
Executor primitives, including native `delay` on devices that advertise it.

Submit scheduled circuits with literal delays through `backend.run()`. Qiskit
converts numeric SI durations to backend ticks during transpilation. Until an
MQT Core release includes delay serialization, install the pinned revision from
the IBM QDMI device checkout with `uv sync --locked --no-dev --extra qiskit`.

```python
from qiskit import QuantumCircuit, transpile

circuit = QuantumCircuit(1, 1)
circuit.x(0)
circuit.delay(32, 0, unit="ns")
circuit.measure(0, 0)
scheduled = transpile(circuit, backend, scheduling_method="alap")
job = backend.run(scheduled, shots=128, memory=True)
shots = job.result().get_memory()
```

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
compiled = backend.compile(circuit)
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

This path submits independent jobs. Runtime session/batch contexts and the
`local_mode` option are unsupported; use a fake backend for local simulation.
The Python adapter rejects nondefault environment and simulator options before
submission. It uses the native 60-second execution cap and requires
`max_execution_time` to remain unset. Native callers can set the cap through the
custom job parameter. Execution and experimental payload options are encoded by
IBM's library and validated by the service. Shots come from the program and
apply to every configuration, not to the program's total workload.

## Executor-backed Sampler and Estimator

Install `ibm-qdmi[executor]` to use IBM Runtime's client-side primitives with
your `IBMBackend`. Use `executor_sampler()` for counts and
`executor_estimator()` for expectation values. Both accept compiled Qiskit
circuits and use the backend's existing QDMI session.

This example samples a Bell circuit and estimates its `ZZ` expectation value.
Add measurements for the Sampler. For the Estimator, apply the compiled
circuit's layout to the observable so it acts on the right physical qubits.

```python
from mqt.core.mlir import OutputFormat, compile_program
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp

bell = QuantumCircuit(2)
bell.h(0)
bell.cx(0, 1)
measured = bell.measure_all(inplace=False)
sample_isa, estimate_isa = compile_program([measured, bell], target=backend.device, output=OutputFormat.QISKIT)

sampler = backend.executor_sampler()
sample = sampler.run([sample_isa], shots=128).result(timeout=300)[0]
counts = sample.join_data().get_counts()

estimator = backend.executor_estimator(options={"resilience_level": 0})
observable = SparsePauliOp("ZZ").apply_layout(estimate_isa.layout)
estimate = estimator.run([(estimate_isa, observable)], precision=0.125).result(timeout=300)[0]
expectation_value = estimate.data.evs
```

On a fake backend, the counts contain only `00` and `11`, and the expectation
value is `1.0`. `join_data()` combines all classical registers in circuit order.
For counts from one register, use `sample.data[register_name].get_counts()`.

Pass a dictionary or an IBM Runtime options model as `options`. Leave
`max_execution_time` unset to use the 60-second QPU cap. To enable dynamical
decoupling, set `sampler.options.dynamical_decoupling.enable = True` (or the
same option on the Estimator). Runtime uses the backend's sampling interval and
gate durations to schedule the pulses. This requires a backend with timing and
delay instructions and a circuit without control flow.

The example disables Estimator error mitigation with `resilience_level=0`. For
mitigation options and methods that require a separate noise learning job, see
[IBM's client-side Estimator guide](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/executor-estimator).
