# IBM QDMI Device

**IBM QDMI Device** connects IBM Quantum Platform to the
[Quantum Device Management Interface (QDMI)](https://github.com/Munich-Quantum-Software-Stack/QDMI).
It lets applications query backends and run quantum circuits through a shared
device interface.

The C++20 library handles API-key authentication, calibration queries, and the
job lifecycle. It submits OpenQASM 3 circuits and returns ordered shots and
histograms. The Python package includes the native library and optional Qiskit
and PennyLane integrations.

Live metadata validation has passed. Quantum execution remains unverified on
hardware until the [gated live checks](development.md#gated-quantum-execution)
succeed. The examples default to local simulation.

## Where to start

| I want to…                                   | Start here                            |
| :------------------------------------------- | :------------------------------------ |
| Install the native library or Python package | [Installation](installation.md)       |
| Run circuits from Python / Qiskit            | [Qiskit integration](qiskit.md)       |
| Execute PennyLane QNodes                     | [PennyLane integration](pennylane.md) |
| Run example workloads                        | [Examples](examples.md)               |
| Configure native sessions and manage jobs    | [Usage guide](api.md)                 |
| Locate installed files and discover devices  | [Python package](python_package.md)   |
| Build and test the project                   | [Development](development.md)         |
| Contribute a change                          | [Contributing](contributing.md)       |

## API reference

The generated references document the [native declarations](native_api.md) and
the {doc}`Python package <python-api/ibm/qdmi/index>`. For configuration,
supported properties, and job behavior, start with the [usage guide](api.md).

<!-- MyST directives use fenced blocks rather than code languages. -->
<!-- rumdl-disable MD040 -->

```{toctree}
:maxdepth: 1
:caption: User Guide

installation
examples
qiskit
pennylane
Usage guide <api>
python_package
CHANGELOG
```

```{toctree}
:maxdepth: 1
:caption: Developer Guide

dependencies
development
contributing
support
security
```

```{toctree}
:maxdepth: 1
:caption: API Reference

native_api
python-api/ibm/qdmi/index
```

<!-- rumdl-enable MD040 -->
