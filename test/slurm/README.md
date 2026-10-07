# IBM workload for Core's Slurm fixture

MQT Core owns the Slurm cluster, SPANK component, provider installation, generic
transport tests, and cleanup. This directory supplies the IBM catalogue and
adapter workload. The server reuses `test/python/offline_service.py` and
`qiskit_service.py`; it runs on each node's loopback interface with synthetic
credentials and never contacts IBM.

Set `CORE_SOURCE` to a checkout of Core's shared Slurm fixture and `CORE_DIST`
to a directory containing the released Linux `mqt_core-4.0.0` wheel for the
Docker host architecture. Use rootful Docker with cgroup v2 on a disposable
host.

```sh
PROVIDER_INSTALL_MODE=native uv run --no-project \
  "$CORE_SOURCE/test/slurm/run_integration.py" \
  --workload . --dist "$CORE_DIST" \
  --setup-script test/slurm/setup.sh \
  --compose-file test/slurm/compose.yml \
  --device-license ibm.fixture \
  --qdmi-config-file /opt/provider-catalogue.json \
  --reference IBM_QUANTUM_API_KEY=synthetic-key \
  --reference IBM_QUANTUM_INSTANCE_CRN=crn:v1:bluemix:public:quantum-computing:us-east:a:instance:: \
  --reference IBM_QUANTUM_BACKEND=ignored_backend \
  -- python3 /workload/test/slurm/probe.py
```

Repeat with `PROVIDER_INSTALL_MODE=wheel`. Both modes install the Python
adapters; native mode selects the separate Runtime library, and wheel mode
selects the bundled library. Core checks the loaded library and runs each
workload with explicit configuration and shared SPANK injection as a non-root
job user. The IBM workload checks concrete backend selection despite an
inherited backend override, Qiskit submission/retrieval, PennyLane results, and
missing credentials. See [IBM on Slurm](../../docs/slurm.md) for deployment.
