# Runnable examples

The examples use finite shots and default to MQT Core's local QDMI simulator.
Run them from a source checkout with the example dependencies installed:

```console
uv sync --group examples
uv run --group examples python -m examples.native_job
uv run --group examples python -m examples.qiskit_workloads --workload bell
uv run --group examples python -m examples.qiskit_workloads --workload benchmark
uv run --group examples python -m examples.qiskit_workloads --workload h2
uv run --group examples python -m examples.pennylane_qaoa
```

Each command prints JSON. Use `--shots` to select a positive shot count; the
default is 128. `native_job` also accepts `--timeout` in seconds, defaults to
60, and attempts cancellation if its wait or result retrieval fails.

## Native QDMI jobs

`examples/native_job.py` opens a QDMI device, submits a full-width OpenQASM 3
program with one measured X gate, waits for completion, and reads counts. It
accesses the native job interface directly through MQT Core's bindings. The
expected result is `{"1": 128}` with the default shot count. The simulator uses
a one-qubit program; IBM uses the full physical register.

See the [native API contract](api.md) for session configuration, result sizing,
job states, and cancellation semantics. Releasing a local job handle does not
cancel a remote job.

`examples/native/execute.c` demonstrates the same lifecycle with the QDMI C ABI.
Build it against a native installation containing both runtime and development
components:

```console
cmake -S examples/native -B build/example -DCMAKE_PREFIX_PATH=/path/to/install
cmake --build build/example --config Release
```

Running `ibm-qdmi-execute` without arguments prints help and makes no requests.
To submit a hardware job, provide `IBM_QUANTUM_API_KEY` and
`IBM_QUANTUM_INSTANCE_CRN` in the environment, then invoke
`ibm-qdmi-execute --run ibm_berlin` (or `ibm_aachen`). This program submits one
16-shot job with a 60-second execution limit and a bounded wait. Use
`--timeout 1..60` to shorten the wait. It attempts cancellation after a timeout
or execution failure and always releases local handles. The optional
`--test-port` accepts a port from 1 to 65535 and connects only to `127.0.0.1`
for synthetic tests. Session initialization loads credentials through the native
library's environment support.

## Qiskit sampling and benchmarks

The Bell example transpiles a two-qubit circuit to the selected target and runs
the shared sampler primitive. Counts contain only `00` and `11`.

The benchmark example asks MQT Bench to map a three-qubit GHZ circuit to that
same target. Counts contain only `000` and `111` on an ideal simulator. Hardware
noise can produce other outcomes. These programs retain physical layouts and use
the serializer described in the [Qiskit guide](qiskit.md).

## H₂ energy estimation

The H₂ example prepares one parameterized trial state and evaluates the
two-qubit Hamiltonian from
[IBM Quantum Learning's variational examples](https://quantum.cloud.ibm.com/learning/en/courses/variational-algorithm-design/examples-and-applications).
It applies the transpiled layout to the observable before calling the shared
estimator, with precision `1 / sqrt(shots)`. The output is an energy estimate in
hartrees. This example performs one evaluation; it does not optimize the state
or calculate a molecular Hamiltonian from a geometry. The fixed Hamiltonian
keeps the example portable without a chemistry dependency.

## PennyLane QAOA

The QAOA example evaluates one layer for the two-vertex MaxCut problem and
samples its state. It runs two finite-shot QNodes, one for the cut-value
expectation and one for counts. The objective lies between zero and one. This is
a fixed-parameter evaluation, without an optimization loop or gradient jobs.

## Selecting IBM hardware

Hardware access is explicit. Configure credentials and the instance as described
in [Qiskit guide](qiskit.md#select-a-backend), then select both the IBM backend
and a catalogue device:

```console
uv run --group examples python -m examples.qiskit_workloads --backend ibm --device ibm.berlin --workload bell --shots 128
```

Use `ibm.aachen` for Aachen or `ibm.default` with a configured backend name. The
same options apply to all examples. Hardware jobs may incur charges; the shot
count does not bound the total execution time or cost of a workload. Estimator
workloads can submit several circuits. Configure native execution limits through
the device API as needed.

The documentation build never executes these programs. The `examples` Nox
session checks local simulation and the IBM library against a synthetic loopback
service, without IBM credentials or live access.
