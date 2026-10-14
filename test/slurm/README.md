# IBM Slurm Smoke Test

Run Qiskit and PennyLane circuits through the installed IBM wheel in the
[shared Slurm playground](https://mqt.readthedocs.io/projects/core/en/latest/qdmi/slurm.html).
The job derives its device ID from its allocated license and checks which native
library was loaded. The cluster's availability monitor probes the same device
before admitting the job.

The overlay supplies synthetic credentials and loopback endpoints from
`qdmi.env` to the availability monitor and login node. Slurm transports the
submission environment to the job. A systemd service on the controller and
quantum access nodes reuses the HTTP fixture in `test/python` and simulates
submitted OpenQASM with Qiskit. There is no IBM access or hardware execution.

Set `CORE_SOURCE` to an MQT Core checkout at the revision pinned in
`.github/workflows/slurm.yml`. From this repository's root, run:

```bash
uv run --no-project "$CORE_SOURCE/test/slurm/run_integration.py" \
  --workload . --package /workload --package pytest \
  --compose-file test/slurm/compose.yml \
  --device-license ibm.berlin \
  -- python3 /workload/test/slurm/workload.py
```

The shared setup builds MQT Core and this device from source for the container
architecture and installs their wheels in one environment. It requires Docker
with Compose and cgroup v2, including Docker Desktop's Linux engine on macOS.
The runner removes its cluster and volumes after execution. See
[IBM on Slurm](../../docs/slurm.md) for deployment and job examples.
