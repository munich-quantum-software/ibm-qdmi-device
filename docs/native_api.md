# C/C++ API reference

The native library exposes the QDMI device interface with the `IBM_` symbol
prefix. Public headers include `ibm_qdmi/device.h` and
`ibm-qdmi-device/constants.h`.

<!-- Doxygen HTML is generated alongside the Sphinx documentation. -->
<!-- rumdl-disable MD033 -->
The declarations below are generated from the public headers. The
<a href="cpp/index.html">standalone Doxygen reference</a> remains available and
also includes the upstream QDMI client declarations.
<!-- rumdl-enable MD033 -->

See the [usage guide](api.md) for supported properties, session configuration,
and job behavior. Follow [native installation](installation.md#native-package)
to link a downstream application.

<!-- MyST directives embed declarations from the generated Doxygen XML. -->
<!-- rumdl-disable MD040 -->

## Device lifecycle

```{doxygengroup} device_interface
:members:
```

## Device sessions

```{doxygengroup} device_session_interface
:members:
```

## Device queries

```{doxygengroup} device_query_interface
:members:
```

## Device jobs

```{doxygengroup} device_job_interface
:members:
```

## Client lifecycle

```{doxygengroup} client_interface
:members:
```

## Client sessions

```{doxygengroup} client_session_interface
:members:
```

## Client queries

```{doxygengroup} client_query_interface
:members:
```

## Client jobs

```{doxygengroup} client_job_interface
:members:
```

## IBM handle types

```{doxygenfile} ibm_qdmi/types.h
```

## Client handle types

```{doxygenfile} include/qdmi/types.h
```

## QDMI constants

```{doxygenfile} include/qdmi/constants.h
```

## IBM constants

```{doxygenfile} ibm-qdmi-device/constants.h
```

<!-- rumdl-enable MD040 -->
