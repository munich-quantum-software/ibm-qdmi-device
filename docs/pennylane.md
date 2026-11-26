# PennyLane integration

{py:class}`~ibm.qdmi.pennylane.IBMDevice` uses MQT Core's PennyLane adapter for
compilation, job orchestration, and sample decoding. It provides `ibm.default`,
`ibm.berlin`, and `ibm.aachen` as PennyLane device names.

## Install

```console
uv pip install "ibm-qdmi[pennylane]"
```

## Configure a device

Set `IBM_QUANTUM_API_KEY` and `IBM_QUANTUM_INSTANCE_CRN` as described in
[backend configuration](qiskit.md#select-a-backend). The generic `ibm.default`
device also requires `IBM_QUANTUM_BACKEND` or an explicit `backend_name`.
Concrete catalogue IDs keep their backend selection unless `backend_name` is
supplied.

```python
import pennylane as qp

# Device construction reads IBM metadata.
device = qp.device("ibm.berlin", wires=2)
```

Supply `api_key`, `instance_crn`, and `backend_name` to override connection
settings. Omitted arguments use the native session configuration; a configured
authentication file takes precedence over `IBM_QUANTUM_API_KEY`. See
[session configuration](api.md#session-configuration).

`IBMDevice(device=opened_device, wires=2)` adapts an open QDMI device and
rejects connection overrides. Imports do not open a session or submit work.

## Run a QNode

```python
@qp.qnode(device)
def circuit():
    qp.X(0)
    return qp.counts(wires=[0, 1])


# This call submits a paid quantum job.
counts = qp.set_shots(circuit, shots=1000)()
```

The `wires` argument labels the circuit's qubits. MQT Core maps them to backend
qubits and returns samples in the order requested by each measurement. The
compiler uses the advertised gate placements and parameter ranges, including
fractional RZZ bounds.

## Supported scope

The adapter runs finite-shot QNodes and forwards custom job settings through
`job_parameters`. See the [native API](api.md) for submission limits and the
execution-time cap, and the
[MQT Core PennyLane guide](https://mqt.readthedocs.io/projects/core/en/latest/qdmi/pennylane_device.html)
for measurements, differentiation, batches, failures, and local simulation.
