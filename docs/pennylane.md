# PennyLane integration

From a source checkout, install the optional adapter with
`uv pip install '.[pennylane]'`. The `IBMDevice` class reuses MQT Core's
PennyLane preprocessing, job orchestration, and sample decoding. It exports
`ibm.default`, `ibm.berlin`, and `ibm.aachen` as PennyLane device names.

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
environment. `IBMDevice(device=opened_device, wires=2)` adapts an existing QDMI
session and rejects connection overrides. Importing the adapter and inspecting
entry points do not open a session or submit work.

The wrapper uses environment credentials as explicit session parameters when
`api_key` or `instance_crn` is omitted. An environment API key therefore takes
precedence over a registered authentication file. To retain a native session's
file selection, open it through the QDMI driver and pass it as `device`; see
{doc}`api` for native credential precedence.

Wire labels map in their declared order to physical qubits starting at zero. For
example, `wires=["control", "target"]` maps those labels to physical qubits 0
and 1. Integer labels are labels, not a physical layout override. The emitted
OpenQASM always declares the full backend width, and measures only the exposed
wires using indexed assignments. Sample columns follow the requested measurement
order. The adapter validates each gate's parameters and physical placement
against backend metadata. It does not route circuits or reverse directed
couplings.

## Measurements and differentiation

Set finite shots on the QNode with `shots=128`, or use `qml.set_shots`. Analytic
execution and device-level `shots` are unsupported. Samples, counts,
probabilities, expectation values, and variances are computed from returned
samples. Shot vectors and parameter broadcasting may create several native jobs.
Parameter-shift and finite-difference differentiation use ordinary sampled jobs;
the device does not provide analytic gradients.

PennyLane decomposes operations into the advertised native basis. The IBM
adapter expresses single-qubit rotations using SX and RZ while preserving
parameters for differentiation; this includes Hadamard, RX, and RY gates. Native
ECR and RZZ remain native when the backend advertises their signatures and
placements. Incompatible operations or placements fail before any job in a
prepared batch is submitted. A submission or result failure attempts
cancellation of earlier jobs; remote cancellation can race with completion, and
submissions are never retried.

The adapter forwards compatible custom job settings through `job_parameters`;
the native parameter contracts are documented in {doc}`api`. MQT Core 4's Python
custom-parameter interface cannot encode the `uint64_t` execution-time cap.
PennyLane therefore retains the native default of 60 seconds; use the native C
interface to change that cap.

For local development without IBM access, use MQT Core's
`qml.device("mqt.ddsim.default", wires=2)` with the same finite-shot QNode API.
This simulator checks circuit logic without validating IBM connectivity or
hardware behavior.
