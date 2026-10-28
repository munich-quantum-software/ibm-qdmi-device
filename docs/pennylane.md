# PennyLane integration

This draft requires
[Core #2767](https://github.com/munich-quantum-toolkit/core/pull/2767) on top of
[Core #2886](https://github.com/munich-quantum-toolkit/core/pull/2886). Use
`uv sync --extra pennylane` from this checkout to install its exact source pin.
The {py:class}`~ibm.qdmi.pennylane.IBMDevice` class reuses MQT Core's PennyLane
preprocessing, job orchestration, and sample decoding. It exports `ibm.default`,
`ibm.berlin`, and `ibm.aachen` as PennyLane device names. See the
[MQT Core PennyLane guide](https://mqt.readthedocs.io/projects/core/en/latest/qdmi/pennylane_device.html)
for QNodes, measurements, differentiation, batches, and local simulation.

## Configure a device

Set `IBM_QUANTUM_API_KEY` and `IBM_QUANTUM_INSTANCE_CRN` as described in
[backend configuration](qiskit.md#select-a-backend). The generic `ibm.default`
device also requires `IBM_QUANTUM_BACKEND` or an explicit `backend_name`.
Concrete catalogue IDs keep their backend selection unless `backend_name` is
supplied.

```python
import pennylane as qml

# Device construction queries IBM metadata. Calling the QNode submits paid jobs.
device = qml.device("ibm.berlin", wires=2)


@qml.qnode(device, shots=128)
def circuit():
    qml.X(0)
    return qml.counts(wires=[0, 1])
```

Supply `api_key`, `instance_crn`, and `backend_name` explicitly to override the
catalogue configuration and environment defaults.
`IBMDevice(device=opened_device, wires=2)` adapts an existing QDMI session and
rejects connection overrides. Importing the adapter and inspecting entry points
do not open a session or submit work.

Omitted connection arguments use the same native configuration as a direct QDMI
session. A configured authentication file takes precedence over
`IBM_QUANTUM_API_KEY`; see
[session configuration](api.md#session-configuration).

Wire labels identify logical wires. MQT Core compiles and routes them for the
selected backend; the IBM serialization profile declares the full backend width
and reconstructs samples in the requested logical measurement order. The
compiler consumes the provider's gate placements and parameter domains,
including fractional RZZ bounds. Its current QDMI target requires the same
native one-qubit basis on every site and two-qubit basis on every topology edge.
Heterogeneous metadata fails during device construction.

## IBM gate support

PennyLane applies measurement and differentiation transforms before Core
compiles the resulting tapes into the advertised native basis. Core owns gate
synthesis, physical placement, parameter constraints, and receiver-compatible
serialization. Invalid input fails before any job in a prepared batch is
submitted. A submission or result failure raises `PennyLaneExecutionError` with
a retained `job` handle. Use that handle to inspect the batch or explicitly
cancel earlier jobs; cancellation can race with completion. Automatic retries
are disabled. Unknown submission outcomes are never automatically replaced.

The adapter forwards compatible custom job settings through `job_parameters`;
the native parameter contracts and default execution-time cap are documented in
{doc}`api`.
