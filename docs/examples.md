---
file_format: mystnb
kernelspec:
  name: python3
  display_name: Python 3
---

# Runnable examples

The examples use finite shots and default to MQT Core's local QDMI simulator.
The showcase includes full
[Quantum-Selected Configuration Interaction (QSCI)][qsci] for H₂ and seven
[MQT Bench][mqt-bench] algorithm families. The workloads use the shared Qiskit
sampler and estimator primitives through QDMI.

The scripts live in the repository, rather than the installed Python package.
Clone the repository and run commands from its root:

```console
git clone https://github.com/munich-quantum-software/ibm-qdmi-device.git
cd ibm-qdmi-device
```

Install the example dependencies and run the portable examples:

```console
uv sync --group examples
uv run --group examples python -m examples.native_job
uv run --group examples python -m examples.qiskit_workloads --workload bell
uv run --group examples python -m examples.mqt_bench --benchmark ghz
uv run --group examples python -m examples.qiskit_workloads --workload h2
uv run --group examples python -m examples.pennylane_qaoa
```

The basic native, Qiskit, and PennyLane commands print JSON. The showcase
runners log circuit sizes, execution progress, counts, and validation summaries.
Use `--shots` to select a positive shot count. Basic examples default to 128;
the tables below give showcase defaults. `native_job` also accepts `--timeout`
in seconds, defaults to 60, and attempts cancellation if its wait or result
retrieval fails.

## Execute in the documentation

These cells call the same example functions on MQT Core's local simulator. They
always select `sim`, require no IBM credentials, and submit no hardware jobs.
The build caches successful execution and fails if a cell raises an error.

<!-- MyST code-cell directives execute as notebook cells. -->
<!-- rumdl-disable MD040 -->

```{code-cell} python
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd().parent))

from examples.common import open_backend
from examples.native_job import run
from examples.qiskit_workloads import estimate_h2, sample_bell

backend = open_backend("sim", None)
counts = run(backend.device, shots=128, qubits=1)
assert counts == {"1": 128}
counts
```

```{code-cell} python
counts = sample_bell(backend, shots=128)
assert set(counts) <= {"00", "11"}
assert sum(counts.values()) == 128
counts
```

```{code-cell} python
energy = estimate_h2(backend, shots=128)
assert -2.0 < energy < -1.0
energy
```

<!-- rumdl-enable MD040 -->

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

## MQT Bench showcase

`examples/mqt_bench.py` generates a benchmark at MQT Bench's mapped level using
the selected backend's target. It runs the resulting circuit through
`backend.sampler(default_shots=shots)` and reads the benchmark's classical
register. Mapping and sampling preserve logical measurement order, even when
hardware routing changes physical qubit positions.

| `--benchmark` | Program                        | Default qubits | Default shots | Distribution check                                     |
| ------------- | ------------------------------ | -------------: | ------------: | ------------------------------------------------------ |
| `ghz`         | GHZ entanglement               |              3 |          1024 | Equal all-zero and all-one outcomes                    |
| `dj`          | Deutsch–Jozsa oracle           |              4 |          1024 | All-one outcome on the query register                  |
| `qft`         | Quantum Fourier transform      |              3 |          1024 | Uniform computational-basis distribution               |
| `graphstate`  | Graph-state preparation        |              4 |          1024 | Uniform computational-basis distribution               |
| `wstate`      | W-state preparation            |              3 |          1024 | Uniform single-excitation outcomes                     |
| `grover`      | Grover search                  |              7 |          8192 | Marked-state probability after amplitude amplification |
| `qpe`         | Exact quantum phase estimation |              5 |          8192 | Concentration in the most frequent outcome             |

GHZ and W states demonstrate different forms of multipartite entanglement.
Deutsch–Jozsa queries an oracle; Grover amplifies a marked search result. The
Fourier transform and phase estimation are building blocks for quantum
algorithms. Graph states also support measurement-based quantum computation.

The runner compares measured distributions with ideal probabilities using
Hellinger fidelity. QPE reports modal concentration; this diagnostic alone
cannot establish that the dominant phase is correct. These are
computational-basis checks, not complete state tomography. Finite sampling and
hardware noise can reduce the reported scores.

Select a family and optionally override its size and shot count:

```console
uv run --group examples python -m examples.mqt_bench --benchmark ghz --num-qubits 20 --shots 8192
uv run --group examples python -m examples.mqt_bench --benchmark dj
uv run --group examples python -m examples.mqt_bench --benchmark qft
uv run --group examples python -m examples.mqt_bench --benchmark graphstate
uv run --group examples python -m examples.mqt_bench --benchmark wstate
uv run --group examples python -m examples.mqt_bench --benchmark grover
uv run --group examples python -m examples.mqt_bench --benchmark qpe
```

`--benchmark` defaults to `ghz`. `--num-qubits` requires at least two qubits,
and the selected backend must support the requested width. Deutsch–Jozsa and
Grover include an ancillary qubit in that width; QPE includes its eigenstate
qubit. The runner selects each program's correct result register.

### Execute a GHZ benchmark

This cell runs the same public runner on the local simulator. Its twenty-qubit
GHZ distribution contains only all-zero and all-one strings.

<!-- rumdl-disable MD040 -->

```{code-cell} python
from examples.mqt_bench import run as run_benchmark

counts = run_benchmark(backend, "ghz", shots=8192, num_qubits=20)
assert set(counts) <= {"0" * 20, "1" * 20}
assert sum(counts.values()) == 8192
counts
```

<!-- rumdl-enable MD040 -->

### Benchmark source

```{literalinclude} ../examples/mqt_bench.py
:language: python
:caption: examples/mqt_bench.py
:start-at: from __future__
```

## H₂ QSCI showcase

`examples/qsci_h2.py` follows the complete quantum chemistry workflow:

1. PySCF builds H₂ at a bond length of 1 Å in the STO-3G basis.
2. Qiskit Nature maps its electronic Hamiltonian to four qubits with
   Jordan–Wigner encoding.
3. A Hartree–Fock state initializes a unitary coupled-cluster singles and
   doubles (UCCSD) ansatz.
4. The variational quantum eigensolver (VQE) optimizes that ansatz using the
   backend estimator and L-BFGS-B.
5. The backend sampler measures the optimized circuit in logical orbital order.
6. QSCI retains the most frequent states with one alpha and one beta electron.
7. Classical diagonalization finds the lowest energy in that selected subspace;
   nuclear repulsion gives the total energy.

The reduced Hamiltonian comes from the same molecular integrals and logical
qubit operator used by VQE. For this four-qubit molecule, projecting its
16-by-16 matrix is inexpensive. Larger molecules require sparse matrix-element
construction instead of a full matrix.

The reference total energy is approximately **−1.101150 hartree**. The runner
logs the VQE electronic energy, sampled counts, QSCI total energy, and absolute
difference from that reference. A finite iteration limit does not guarantee VQE
convergence. Missing determinants can raise the QSCI energy; the cutoff limits
the selected subspace, and nuclear repulsion is added once.

### Chemistry dependencies and execution

[Qiskit Nature][qiskit-nature] and [PySCF][pyscf] provide the molecular model.
PySCF supports Linux and macOS. On Windows, run this example in a supported
Linux environment, such as WSL. The portable benchmark and basic examples remain
available on Windows.

Use Python 3.11–3.13 with the optional `chemistry` dependency group:

```console
uv run --python 3.13 --group chemistry python -m examples.qsci_h2 --backend sim
uv run --python 3.13 --group chemistry python -m examples.qsci_h2 --shots 256 --maxiter 5 --cutoff 4
```

| Option      | Default | Meaning                                                 |
| ----------- | ------: | ------------------------------------------------------- |
| `--shots`   |    8192 | Sampler shots and estimator precision `1 / sqrt(shots)` |
| `--maxiter` |      30 | Maximum L-BFGS-B iterations                             |
| `--cutoff`  |      10 | Maximum number of valid sampled determinants            |

All three values must be positive. Qiskit rounds the estimator shot count up
from `1 / precision**2` for each measurement circuit and groups compatible
observables. Therefore, `--shots` is **not a total VQE shot budget**. Each
optimizer evaluation can require several circuits, and an iteration can require
several evaluations. The final sampling call uses the requested shot count.

VQE applies the transpiled layout to the observable internally. Final sampling
adds measurements before mapping, so QSCI receives logical spin-orbital
bitstrings rather than physical hardware indices.

### QSCI source

```{literalinclude} ../examples/qsci_h2.py
:language: python
:caption: examples/qsci_h2.py
:start-at: from __future__
```

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
uv run --group examples python -m examples.mqt_bench --backend ibm --device ibm.berlin --benchmark ghz --shots 128
uv run --python 3.13 --group chemistry python -m examples.qsci_h2 --backend ibm --device ibm.berlin --shots 256 --maxiter 5 --cutoff 4
```

Use `ibm.aachen` for Aachen or `ibm.default` with a configured backend name. The
same options apply to all examples. Hardware jobs may incur charges; the shot
count does not bound the total execution time or cost of a workload. Estimator
workloads can submit several circuits. Configure native execution limits through
the device API as needed.

## Offline validation

The documentation executes only the simulator cells above. The full chemistry
workflow runs in a separate session with PySCF, outside the documentation build:

```console
uvx nox -s examples
uvx nox -s chemistry
uvx nox -s docs -- -D nb_execution_mode=force
```

The `examples` session exercises all seven benchmarks, QSCI post-processing, and
the VQE/sampler integration. It also checks basic examples against a synthetic
IBM loopback service. The `chemistry` session builds the molecular Hamiltonian
and runs the complete H₂ workflow on a local simulator using Python 3.13. Linux
CI runs both sessions without IBM credentials. On Windows, the chemistry session
skips because PySCF is unavailable.

[mqt-bench]: https://mqt.readthedocs.io/projects/bench/
[qiskit-nature]: https://qiskit-community.github.io/qiskit-nature/
[qsci]: https://arxiv.org/abs/2302.11320
[pyscf]: https://pyscf.org/user/install.html
