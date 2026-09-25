<!-- rumdl-disable MD041 -->
(api-status)=

# Usage guide

## Native interface

The library implements IBM-prefixed QDMI 1.3.3 device
initialization/finalization, session
allocation/configuration/initialization/free, and device, site, and operation
queries, and the complete job lifecycle. The supported program format is
OpenQASM 3. Child-device enumeration is unsupported.

The [generated QDMI declaration reference](native_api.md) describes the
implemented device functions, types, and IBM-specific constants.

## Session configuration

Include `ibm_qdmi/device.h` and `ibm-qdmi-device/constants.h`. Set parameters
before initializing a session. Strings include the terminating null byte in
`size`; embedded null bytes are rejected. A null value checks support without
changing a parameter. Successful initialization freezes configuration. Failed
initialization leaves the session configurable and safe to free.

| Parameter                                           | Value                                                                                                             |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `QDMI_DEVICE_SESSION_PARAMETER_TOKEN`               | IBM Cloud API key, not an IAM bearer token; otherwise use an explicit key file, then `IBM_QUANTUM_API_KEY`.       |
| `QDMI_DEVICE_SESSION_PARAMETER_AUTHFILE`            | Optional UTF-8 path to a file containing only the API key.                                                        |
| `IBM_QDMI_DEVICE_SESSION_PARAMETER_BACKEND`         | Backend name; defaults to `IBM_QUANTUM_BACKEND`; aliases session `CUSTOM1`.                                       |
| `IBM_QDMI_DEVICE_SESSION_PARAMETER_INSTANCE_CRN`    | Instance CRN; defaults to `IBM_QUANTUM_INSTANCE_CRN`; aliases session `CUSTOM2`.                                  |
| `IBM_QDMI_DEVICE_SESSION_PARAMETER_REQUEST_TIMEOUT` | Positive decimal string of milliseconds from 1 through 2,147,483,647; default `30000`; aliases session `CUSTOM3`. |
| `QDMI_DEVICE_SESSION_PARAMETER_BASEURL`             | Optional API root ending in `/api`, without `/v1`. Defaults from the CRN region.                                  |
| `QDMI_DEVICE_SESSION_PARAMETER_AUTHURL`             | Optional full IAM token endpoint; defaults to `https://iam.cloud.ibm.com/identity/token`.                         |

Default API roots are `https://quantum.cloud.ibm.com/api` for `us-east` and
`https://eu-de.quantum.cloud.ibm.com/api` for `eu-de`. Other regions require an
explicit root. Custom endpoints must use HTTPS; HTTP is accepted only for
`localhost`, `127.0.0.1`, and `[::1]` loopback tests. Certificate verification
stays enabled, and redirects are not followed. Configure only trusted endpoints.
The API key, backend name, and instance CRN must resolve to nonempty values.
Explicit parameters take precedence over environment values, including an
explicit empty value, which fails validation. Defaults are read during session
initialization. A failed attempt does not freeze them; an initialized session
retains its configuration when the environment changes.

An explicit token takes precedence over an explicit key file. A selected key
file takes precedence over `IBM_QUANTUM_API_KEY`; an unreadable or invalid file
does not fall back to environment credentials. The library does not discover
credential files or read saved Qiskit accounts. Files contain a raw UTF-8 API
key, optionally followed by one LF or CRLF. Empty files, invalid UTF-8, embedded
newlines, and null bytes are rejected. Other whitespace is preserved. Files are
read only during initialization; IAM refresh uses the session's resolved key. An
unreadable file returns `QDMI_ERROR_PERMISSIONDENIED`; malformed content or an
empty path returns `QDMI_ERROR_INVALIDARGUMENT`.

The API key is exchanged at IAM. Backend requests use the resulting bearer
token, `Service-CRN`, and `IBM-API-Version: 2026-04-15`. Tokens and their expiry
belong to individual sessions. Refresh occurs before expiry and once after an
HTTP 401; the authenticated GET is retried once. Each HTTP request uses the
configured timeout, including IAM refresh and a GET retry. A shorter job-wait
deadline takes precedence. The default is 30 seconds; a refresh and retry may
require multiple requests. Other errors are not retried. See
[IBM authentication](https://quantum.cloud.ibm.com/docs/en/guides/cloud-setup-rest-api).

Independent device queries, job retrievals, and operations on different job
handles may perform HTTP requests concurrently. IAM refresh remains serialized
within each session, and a delayed unauthorized response cannot invalidate a
newer token. Operations on one job remain serialized to protect its state and
result cache. Job-wait deadlines include time spent waiting for the job lock or
an IAM refresh. Submission is always attempted at most once per job handle.

## Query behavior

Initialization reads backend configuration and calibration properties into a
session snapshot. Site and operation handles remain stable until that session is
freed and cannot be used with another session. Create a new session for a fresh
calibration snapshot. Status and queue queries fetch current backend status.

| Queries                      | Behavior                                                                                                                                                        |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Device name/version          | IBM backend name/version.                                                                                                                                       |
| Library version              | Implemented QDMI version, `1.3.3`.                                                                                                                              |
| Qubit count, sites, coupling | Physical indices and directed pairs from backend configuration.                                                                                                 |
| Operations                   | Native basis gates and advertised measurement/reset; signatures and site tuples from configuration or calibration metadata. Missing information is unsupported. |
| T1, T2, gate duration        | Integer picoseconds, rounded to the nearest picosecond; duration unit `ps`, scale factor `1`.                                                                   |
| Gate fidelity                | `1 - gate_error`, where IBM reports a finite error in `[0, 1]`.                                                                                                 |
| Device status                | `OFFLINE` when unavailable; otherwise `BUSY` for a nonempty queue and `IDLE` for an empty queue. Missing availability is unsupported.                           |
| Queue length                 | Nonnegative number of queued jobs.                                                                                                                              |
| Needs calibration            | `size_t` zero; the interface does not require client-triggered calibration.                                                                                     |
| Pulse support                | `QDMI_DEVICE_PULSE_SUPPORT_LEVEL_NONE`; pulse submission is unsupported.                                                                                        |

Measurement calibration uses `readout_length` and `1 - readout_error` from qubit
properties. Site-dependent duration and fidelity require a supported ordered
site tuple. Configuration tuples take precedence over calibration tuples;
contradictions fail initialization. No connectivity is inferred from gate names.
Calibration flags that mark a qubit or gate as non-operational exclude its
operation tuples and calibrations. Physical site indices, the qubit count, and
the configuration coupling map remain available. Absent operational flags do not
exclude tuples. Calibration values describe the reported gate calibration, not a
parameter-dependent model. Missing optional values, unknown units, negative
durations, overflow, and invalid fidelities return `QDMI_ERROR_NOTSUPPORTED`,
never fabricated zero values. A missing calibration endpoint (HTTP 404) permits
initialization without those optional values. Malformed structural metadata
fails initialization.

Queries honor the QDMI size-query contract. Insufficient output buffers and
invalid arguments return `QDMI_ERROR_INVALIDARGUMENT`. Uninitialized-session
queries return `QDMI_ERROR_BADSTATE`. HTTP authentication failures map to
`QDMI_ERROR_PERMISSIONDENIED`, a missing backend to `QDMI_ERROR_NOTFOUND`,
request deadlines to `QDMI_ERROR_TIMEOUT`, allocation failures to
`QDMI_ERROR_OUTOFMEM`, and other transport/server/parsing failures to
`QDMI_ERROR_FATAL`. Errors never include raw server responses or credentials.

The supported backend response shapes follow the
[IBM backend API](https://quantum.cloud.ibm.com/docs/en/api/qiskit-runtime-rest/tags/backends).
Other QDMI properties return `QDMI_ERROR_NOTSUPPORTED`.

## Query example

This C++ function accepts configuration supplied by its caller. Calling it
contacts IBM and requires authorization. Keep credentials out of source files.
The function owns the device lifecycle; free every session before finalization.

```cpp
#include <ibm-qdmi-device/constants.h>
#include <ibm_qdmi/device.h>

#include <cstring>

int queryQubitCount(const char *apiKey, const char *crn, const char *backend,
                    size_t *qubits) {
  if (!apiKey || !crn || !backend || !qubits) {
    return QDMI_ERROR_INVALIDARGUMENT;
  }
  int result = IBM_QDMI_device_initialize();
  if (result != QDMI_SUCCESS) {
    return result;
  }
  IBM_QDMI_Device_Session session = nullptr;
  result = IBM_QDMI_device_session_alloc(&session);
  const auto set = [&](QDMI_Device_Session_Parameter parameter,
                       const char *text) {
    if (result == QDMI_SUCCESS) {
      result = IBM_QDMI_device_session_set_parameter(
          session, parameter, std::strlen(text) + 1, text);
    }
  };
  set(QDMI_DEVICE_SESSION_PARAMETER_TOKEN, apiKey);
  set(IBM_QDMI_DEVICE_SESSION_PARAMETER_INSTANCE_CRN, crn);
  set(IBM_QDMI_DEVICE_SESSION_PARAMETER_BACKEND, backend);
  if (result == QDMI_SUCCESS) {
    result = IBM_QDMI_device_session_init(session);
  }
  if (result == QDMI_SUCCESS) {
    result = IBM_QDMI_device_session_query_device_property(
        session, QDMI_DEVICE_PROPERTY_QUBITSNUM, sizeof(*qubits), qubits, nullptr);
  }
  IBM_QDMI_device_session_free(session);
  const int finalized = IBM_QDMI_device_finalize();
  return result == QDMI_SUCCESS ? finalized : result;
}
```

## Jobs and results

Configure the program format and a null-terminated program before submission.
Shots default to 1,024; an explicit shot count must be positive. The custom
`IBM_QDMI_DEVICE_JOB_PARAMETER_MAX_EXECUTION_TIME` parameter takes a `uint64_t`
number of seconds from 1 through 10,800, defaulting to 60. This bounds QPU
execution time, not queue or wall-clock time. A null parameter value probes
support without changing configuration.

Programs must be static, bound OpenQASM 3 with explicit classical declarations
and indexed measurements. A quantum register must span the backend's physical
qubits; physical `$n` references are also accepted. Use backend-native
operations and route circuits before submitting them. Classical control flow,
parameter inputs, register broadcasting, and scheduled delays are unsupported.
Static unitary gate declarations support native instructions absent from
`stdgates.inc`, such as ECR and RZZ. Their local arguments cannot introduce
classical storage or control flow. The service validates native gate semantics.

Each submission creates one Sampler V2 job with one circuit and classified
measurements. Twirling is disabled; dynamical decoupling is disabled by default
and can be configured [per job](#dynamical-decoupling). Submission is never
automatically retried, including after an authentication failure or a lost
response. A failed submission freezes that handle. An ambiguous response may
mean IBM accepted the job; inspect the platform before creating a replacement.

Job ID, program, format, and shots are queryable. An unset supported property
returns `QDMI_ERROR_BADSTATE`; queue position returns `QDMI_ERROR_NOTSUPPORTED`.
A job retains its session resources; freeing a session or job handle does not
cancel a remote job. Free every job and session before device finalization.

`job_check` polls once. `job_wait` accepts a timeout in seconds, with zero
meaning no overall deadline. The deadline includes authentication and HTTP
requests. Timeout leaves the remote job active; cancellation is a separate
request. A finished or canceled job ends waiting successfully; a failed job
returns `QDMI_ERROR_FATAL`. Cancellation racing with completion returns
`QDMI_ERROR_INVALIDARGUMENT` and preserves the completed state.

Result queries return comma-separated binary shots, comma-separated histogram
keys, and a matching `size_t` count array. Strings include their terminating
null byte. Bits follow classical declaration order, with the highest bit index
on the left. Leading zeros and shot order are preserved. Results of unfinished
or canceled jobs return `QDMI_ERROR_INVALIDARGUMENT`. Results not yet available
after completion return `QDMI_ERROR_BADSTATE`; malformed results fail rather
than fabricating counts. Completed results are cached. Statevectors and
probabilities are unsupported.

Retrieval by job ID creates a read-only local handle without resubmitting. It
requires the same backend, retained input parameters, and the supported
single-circuit Sampler V2 plain-JSON contract. Private jobs and Qiskit-encoded
results are unsupported. See the
[IBM jobs API](https://quantum.cloud.ibm.com/docs/en/api/qiskit-runtime-rest/tags/jobs).

### Dynamical decoupling

Set `IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING` (job `CUSTOM2`) before
submission to configure IBM Runtime's dynamical decoupling. Its value is a
null-terminated JSON object; include the terminator in `size`.

| Field                      | Accepted values           | Default    |
| -------------------------- | ------------------------- | ---------- |
| `enable`                   | JSON boolean              | `false`    |
| `sequence_type`            | `"XX"`, `"XpXm"`, `"XY4"` | `"XX"`     |
| `extra_slack_distribution` | `"middle"`, `"edges"`     | `"middle"` |
| `scheduling_method`        | `"alap"`, `"asap"`        | `"alap"`   |
| `skip_reset_qubits`        | JSON boolean              | `false`    |

These defaults follow IBM's [dynamical-decoupling options]. Each assignment
replaces the previous object and fills omitted fields with these defaults. An
empty object resets all options. A null pointer only probes support. Malformed
JSON, unknown fields, incorrect types, and unsupported values return
`QDMI_ERROR_INVALIDARGUMENT` without changing the last valid configuration or
making a request. Configuration is frozen after submission starts and on
retrieved jobs. The execution-time cap and disabled twirling remain unchanged.

For a configurable native job:

```cpp
const char options[] = R"({"enable":true,"sequence_type":"XpXm"})";
const int status = IBM_QDMI_device_job_set_parameter(
    job, IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING,
    sizeof(options), options);
```

With MQT Core, pass the JSON string directly to the QDMI device's submission
method. This example assumes an authenticated IBM `device` and a native, bound
OpenQASM 3 `program`. Submission creates a paid job and requires an authorized
backend and budget:

```python
import json

from mqt.core.qdmi import ProgramFormat

job = device.submit_job(
    program,
    ProgramFormat.QASM3,
    num_shots=128,
    custom2=json.dumps({"enable": True, "sequence_type": "XpXm"}),
)
job.wait(900)
shots = job.get_shots()
```

The shared Qiskit `backend.run()` interface does not expose this custom option.
IBM validates compatibility with the selected backend and circuit. Service
rejection follows the normal submission error contract and is never retried.

[dynamical-decoupling options]: https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/options-dynamical-decoupling-options

## Python package

See the [Python package guide](python_package.md) for installed paths, package
metadata, and the information CLI. The optional [Qiskit integration](qiskit.md)
exposes `ibm.qdmi.qiskit.IBMBackend` through MQT Core's shared adapter.
