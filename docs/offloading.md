---
file_format: mystnb
kernelspec:
  name: python3
  display_name: Python 3
---

# Offload Qiskit workloads

Install the `qiskit` extra to use `ibm.qdmi.offloader`, `ibm-sampler`, and
`ibm-estimator`. `sample()` returns joint measurement counts. `estimate()` runs
VQE with L-BFGS-B and returns the complete Qiskit `VQEResult`.

## Local simulation

Use `local=True, simulator=True` to run without Slurm or IBM access:

The documentation executes these local simulator cells and displays their
results. Slurm and hardware examples below remain unexecuted.

<!-- rumdl-disable MD040 -->

```{code-cell} python
from qiskit import QuantumCircuit

from ibm.qdmi.offloader import sample

circuit = QuantumCircuit(2)
circuit.h(0)
circuit.cx(0, 1)
circuit.measure_all()
counts = sample(circuit, shots=128, local=True, simulator=True)
assert sum(counts.values()) == 128
assert set(counts) <= {"00", "11"}
counts
```

The estimator offloader returns a full VQE result. This short run demonstrates
the API; three optimizer iterations do not guarantee convergence to the ground
state of the Pauli-Z observable.

```{code-cell} python
import math

from qiskit.circuit import Parameter
from qiskit.quantum_info import SparsePauliOp
from qiskit_algorithms.utils import algorithm_globals

from ibm.qdmi.offloader import estimate

algorithm_globals.random_seed = 7
ansatz = QuantumCircuit(1)
ansatz.ry(Parameter("theta"), 0)
result = estimate(ansatz, SparsePauliOp("Z"), maxiter=3, local=True, simulator=True)
energy = float(result.eigenvalue.real)
assert math.isfinite(energy) and -1.0 <= energy <= 1.0
assert result.optimal_parameters is not None
{"energy": energy, "optimizer_evaluations": result.optimizer_evals}
```

<!-- rumdl-enable MD040 -->

The simulator uses MQT Core's DDSIM device. Sampling preserves joint classical
register order. VQE transpiles the parameterized ansatz and applies its layout
to the observable before optimization. Local and worker execution share this
path.

## Slurm execution

Omit `local=True` to submit one blocking `srun` task:

```python
counts = sample(circuit, shots=128, simulator=True, partition="quantum", timeout=300)
```

Install the same package and compatible Python, Qiskit, and Qiskit Algorithms
versions on the submitting host and worker. Both need access to `IBM_JOBS_DIR`,
which defaults to `~/.qdmi_jobs`. Use a private directory on a shared
filesystem. The worker exchanges QPY inputs and base64-encoded pickled results.
Estimation also uses a pickled observable. Only load files and results from
trusted workers; pickle can execute code. Successful calls remove their inputs.
Failed calls retain their per-call directory for diagnosis.

`partition` overrides `IBM_SLURM_PARTITION`, then defaults to `quantum`.
`licenses` forwards Slurm's `name[:count][,name[:count]...]` request. `nodes`
defaults to one; the worker always uses one task. The timeout limits the `srun`
process wait. It does not guarantee cancellation of an IBM job already submitted
by the worker.

## IBM execution

Set `simulator=False` only for an authorized hardware workload. This is the API
default. Supply `IBM_QUANTUM_API_KEY` and `IBM_QUANTUM_INSTANCE_CRN` through the
worker environment. Configure their propagation according to site policy.
Credentials never appear in worker arguments or serialized inputs.

`backend_name` applies to both local and offloaded calls and overrides
`IBM_QUANTUM_BACKEND`. Slurm passes it directly as the worker's `--backend-name`
argument. No scheduler plugin is required. See
[backend selection](qiskit.md#select-a-backend) for native configuration.

Each submitted circuit retains the native 60-second QPU execution cap. VQE can
submit many circuits per optimizer iteration; `maxiter` does not cap shots,
circuit submissions, or total spending. Agree on a workload budget before using
hardware. See [job contracts](api.md#jobs-and-results) for cancellation.

Workers also run directly with trusted serialized inputs:

```console
ibm-sampler circuit.qpy --shots 128 --simulator
ibm-estimator ansatz.qpy operator.pkl --maxiter 3 --simulator
```

Their standard output carries the serialized result for the calling offloader.
