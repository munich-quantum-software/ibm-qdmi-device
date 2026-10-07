# IBM on Slurm

MQT Core provides the shared Slurm license adapter and optional SPANK component.
Follow
[Core's deployment guide](https://mqt.readthedocs.io/projects/core/en/latest/qdmi/slurm.html)
for installation roles, Slurm license counts, and plugstack configuration. The
SPANK component requires Slurm 25.11 or newer and is installed separately from
`ibm-qdmi` on submission and compute nodes.

## Provider setup

Install `ibm-qdmi[qiskit,pennylane]` in the job environment on compute nodes, or
install the [native Runtime](installation.md) and the required Python adapters.
Publish a site catalogue with an absolute library path, the `IBM` prefix, and
one concrete IBM backend per license. For example:

```json
{
  "schema-version": 1,
  "qdmi": {
    "devices": [{
      "id": "ibm.berlin",
      "library": "/opt/ibm/lib/libibm-qdmi-device.so",
      "prefix": "IBM",
      "session": {"custom1": "ibm_berlin"}
    }]
  }
}
```

Set `MQT_CORE_QDMI_CONFIG_FILE` to that catalogue, either in the job environment
or through Core's `qdmi_config_file` plugstack option. Configure a Slurm license
with the same ID. Request exactly one license, `ibm.berlin` or `ibm.berlin:1`. A
concrete catalogue backend takes precedence over `IBM_QUANTUM_BACKEND`.

Provide `IBM_QUANTUM_API_KEY` and `IBM_QUANTUM_INSTANCE_CRN` in the job's
private environment through the site's credential mechanism. The catalogue can
instead supply the native `auth-file` session parameter for a private API-key
file and `custom2` for the instance CRN. See [session configuration](api.md). Do
not put API keys in Slurm command-line options or plugstack configuration. The
controller needs neither provider libraries nor IBM credentials.

## Use the selected device

In a job submitted with `sbatch --licenses=ibm.berlin`, open the selected handle
once and pass it to the IBM adapter:

```python
from mqt.core.qdmi import slurm
from qiskit import QuantumCircuit, transpile
from ibm.qdmi.qiskit import IBMBackend

backend = IBMBackend(device=slurm.open_device_from_license())
circuit = QuantumCircuit(2)
circuit.h(0)
circuit.cx(0, 1)
circuit.measure_all()
compiled = transpile(circuit, backend)
counts = backend.run(compiled, shots=128).result().get_counts()
```

For PennyLane, use `IBMDevice(device=slurm.open_device_from_license(), wires=2)`
from `ibm.qdmi.pennylane`. Both adapters retain the selected session and
library. Slurm admission does not grant IBM access or cap circuit submissions or
spending.

The [offloader](offloading.md) separately accepts an explicit backend name; its
`licenses` argument requests scheduler resources and does not select the IBM
backend. Use the handle-based path above when the catalogue must determine the
backend.

Core's optional launch validation requires the same provider runtime, catalogue,
and credentials to exist before its hook runs. For environments activated inside
a batch script, administrators must leave automatic validation disabled; run
`mqt-core-qdmi-check --device ibm.berlin` after activation instead. The checker
must be installed in that environment. A successful check is a readiness
snapshot, not a reservation or a guarantee that submission will succeed.

## Offline integration tests

The provider fixture runs Qiskit and PennyLane against IBM's existing synthetic
HTTP service through Core's shared cluster. Native and wheel modes run without
IBM credentials or QPU submissions. See `test/slurm/README.md` in the source
tree.
