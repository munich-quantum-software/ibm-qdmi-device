# IBM on Slurm

Run IBM workloads in your site's QDMI environment. Request the Slurm license for
a device, then open that device through the QDMI Client Interface. Slurm
schedules the classical resources and device access; the IBM device
implementation authenticates with IBM and submits the quantum circuits.

## Submit a job

Save this workload as `bell.py`. It uses MQT Core's builtin QDMI driver and the
IBM Qiskit adapter:

```{code-block} python
:caption: bell.py

import os

from mqt.core.qdmi import builtin_driver as qdmi_driver
from qiskit import QuantumCircuit, transpile

from ibm.qdmi.qiskit import IBMBackend

device_id = os.environ["SLURM_JOB_LICENSES"].removesuffix(":1")
backend = IBMBackend(device=qdmi_driver.open_device(device_id))
circuit = QuantumCircuit(2)
circuit.h(0)
circuit.cx(0, 1)
circuit.measure_all()
compiled = transpile(circuit, backend)
print(backend.run(compiled, shots=128).result().get_counts())
```

Submit it to your site's quantum access partition, named `quantum` here:

```bash
srun --partition=quantum --licenses=ibm.berlin python bell.py
```

This example requests one device license. Slurm exposes its ID, optionally with
the count `:1`, in `SLURM_JOB_LICENSES`. Applications using several devices
should receive their catalogue IDs explicitly.

For PennyLane, pass the selected device to the IBM adapter:

```python
from ibm.qdmi.pennylane import IBMDevice

adapter = IBMDevice(device=qdmi_driver.open_device(device_id), wires=2)
```

See the [PennyLane guide](pennylane.md) for circuits and result handling.

These commands submit work to IBM hardware using your account. Slurm licenses
neither authorize IBM access nor limit the quantum execution time charged by
IBM.

## Configure IBM access

Provide `IBM_QUANTUM_API_KEY` and `IBM_QUANTUM_INSTANCE_CRN` through your site's
credential mechanism before submission. Slurm exports the submission environment
to the job. Keep API keys out of command-line arguments, committed scripts, and
Slurm configuration. A site catalogue can instead use the `auth-file` session
parameter for a private API-key file readable on the quantum access nodes; see
[session configuration](api.md).

The installed catalogue includes `ibm.berlin` and `ibm.aachen`, which select
concrete backends. Use `ibm.default` with `IBM_QUANTUM_BACKEND` for a backend
chosen in the submission environment. A concrete catalogue entry takes
precedence over that environment default.

## Prepare the cluster

Administrators install the [Python package and adapters](installation.md) in one
workload environment shared by the login and quantum access nodes. The package
advertises its installed catalogue to MQT Core's builtin driver; applications do
not need to register its devices. Site-specific session settings can go in
`/etc/mqt-core/qdmi.json`. For example, a partial definition adds an instance
CRN while retaining the installed library and backend:

```json
{
  "schema-version": 1,
  "qdmi": {
    "devices": [{
      "id": "ibm.berlin",
      "session": {"custom2": "<site-instance-crn>"}
    }]
  }
}
```

Register the same catalogue ID as a Slurm license. For example,
`Licenses=ibm.berlin:2` permits two concurrent allocations. The count is a site
policy, independent of IBM queues and quotas. A shared `quantum` partition can
provide access to all configured QDMI devices from the same environment.

[MQT Core's Slurm playground](https://mqt.readthedocs.io/projects/core/en/latest/qdmi/slurm.html)
demonstrates this layout with login, classical compute, and quantum access
nodes, shared files, and accounting. Its availability monitor reserves device
licenses while the device is unavailable. Configure the monitor's environment
with site-owned IBM credentials, separately from users' credentials. Its
readiness check is a snapshot of that identity's access, not a reservation in
IBM's queue or a guarantee that a later submission succeeds.

The guide covers installation from PyPI, a Git revision, or local sources,
including builds for Linux and Docker Desktop on Apple Silicon. Add `ibm-qdmi`
to the playground's package list; its shared environment already includes the
Qiskit and PennyLane dependencies. For an existing cluster, follow the guide's
[deployment instructions](https://mqt.readthedocs.io/projects/core/en/latest/qdmi/slurm.html#deploy-on-an-existing-cluster).

## Run the offline smoke test

The
[Slurm smoke test](https://github.com/munich-quantum-software/ibm-qdmi-device/tree/main/test/slurm)
runs Qiskit submission and retrieval, plus a PennyLane circuit, through the
installed IBM wheel in a real Slurm allocation. A local synthetic IBM service
simulates the submitted OpenQASM. It needs no IBM credentials and submits no
hardware jobs, so it also runs on fork pull requests. The test README provides
the local command; [live validation](development.md#live-ibm-metadata) is a
separate, explicitly authorized workflow.
