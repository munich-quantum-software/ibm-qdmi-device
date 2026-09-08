# API status

## Native interface

The library implements IBM-prefixed QDMI 1.3.3 device
initialization/finalization, session
allocation/configuration/initialization/free, and device, site, and operation
queries. Job functions are declarations only. There is no discoverable device
catalogue, child-device enumeration, or executable program format yet. A driver
that requires every QDMI job symbol cannot load this partial interface.

<!-- The native API link is generated alongside the Sphinx HTML. -->
<!-- rumdl-disable MD033 -->
The <a href="cpp/index.html">generated QDMI declaration reference</a> also
describes unimplemented job functions and upstream client declarations.
<!-- rumdl-enable MD033 -->

## Session configuration

Include `ibm_qdmi/device.h` and `ibm-qdmi-device/constants.h`. Set parameters
before initializing a session. Strings include the terminating null byte in
`size`; embedded null bytes are rejected. A null value checks support without
changing a parameter. Successful initialization freezes configuration. Failed
initialization leaves the session configurable and safe to free.

| Parameter                                        | Value                                                                                     |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| `QDMI_DEVICE_SESSION_PARAMETER_TOKEN`            | Required IBM Cloud API key, not an IAM bearer token.                                      |
| `IBM_QDMI_DEVICE_SESSION_PARAMETER_BACKEND`      | Required backend name; aliases session `CUSTOM1`.                                         |
| `IBM_QDMI_DEVICE_SESSION_PARAMETER_INSTANCE_CRN` | Required instance CRN; aliases session `CUSTOM2`.                                         |
| `QDMI_DEVICE_SESSION_PARAMETER_BASEURL`          | Optional API root ending in `/api`, without `/v1`. Defaults from the CRN region.          |
| `QDMI_DEVICE_SESSION_PARAMETER_AUTHURL`          | Optional full IAM token endpoint; defaults to `https://iam.cloud.ibm.com/identity/token`. |

Default API roots are `https://quantum.cloud.ibm.com/api` for `us-east` and
`https://eu-de.quantum.cloud.ibm.com/api` for `eu-de`. Other regions require an
explicit root. Custom endpoints must use HTTPS; HTTP is accepted only for
`localhost`, `127.0.0.1`, and `[::1]` loopback tests. Certificate verification
stays enabled, and redirects are not followed. Configure only trusted endpoints.
There is no environment lookup or credential-file support inside the library.

The API key is exchanged at IAM. Backend requests use the resulting bearer
token, `Service-CRN`, and `IBM-API-Version: 2026-04-15`. Tokens and their expiry
belong to individual sessions. Refresh occurs before expiry and once after an
HTTP 401; the authenticated GET is retried once. Each HTTP request has a
30-second deadline; a refresh and retry may require multiple requests. Other
errors are not retried. See
[IBM authentication](https://quantum.cloud.ibm.com/docs/en/guides/cloud-setup-rest-api).

## Query behavior

Initialization reads backend configuration and calibration properties into a
session snapshot. Site and operation handles remain stable until that session is
freed and cannot be used with another session. Create a new session for a fresh
calibration snapshot. Status and queue queries fetch current backend status.

| Queries                      | Behavior                                                                                                                                                                   |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Device name/version          | IBM backend name/version.                                                                                                                                                  |
| Library version              | Implemented QDMI version, `1.3.3`.                                                                                                                                         |
| Qubit count, sites, coupling | Physical indices and directed pairs from backend configuration.                                                                                                            |
| Operations                   | Native basis names; arity and site tuples from explicit configuration or calibration metadata; parameter counts from gate definitions. Missing information is unsupported. |
| T1, T2, gate duration        | Integer picoseconds, rounded to the nearest picosecond; duration unit `ps`, scale factor `1`.                                                                              |
| Gate fidelity                | `1 - gate_error`, where IBM reports a finite error in `[0, 1]`.                                                                                                            |
| Device status                | `OFFLINE` when unavailable; otherwise `BUSY` for a nonempty queue and `IDLE` for an empty queue. Missing availability is unsupported.                                      |
| Queue length                 | Nonnegative number of queued jobs.                                                                                                                                         |

Site-dependent duration and fidelity require a supported ordered site tuple.
Configuration tuples take precedence over calibration tuples; contradictions
fail initialization. No connectivity is inferred from gate names. Calibration
values describe the reported gate calibration, not a parameter-dependent model.
Missing optional values, unknown units, negative durations, overflow, and
invalid fidelities return `QDMI_ERROR_NOTSUPPORTED`, never fabricated zero
values. A missing calibration endpoint (HTTP 404) permits initialization without
those optional values. Malformed structural metadata fails initialization.

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

## Python package

`ibm.qdmi.__version__` reports the installed distribution version. The package
bundles the native interface and headers but exposes no Python backend class,
command-line interface, or quantum framework integration.
