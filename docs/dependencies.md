# Dependencies

This page distinguishes native dependencies, optional Python integrations, and
development tools. The build configuration defines the supported versions;
`uv.lock` records the resolved Python environment.

## Native dependencies

CMake's defaults are defined in
[ExternalDependencies.cmake](https://github.com/munich-quantum-software/ibm-qdmi-device/blob/main/cmake/ExternalDependencies.cmake).
Compatible installed packages can satisfy its `find_package` checks; otherwise,
CMake downloads the configured sources.

| Dependency      | Default version | Purpose                                           |
| :-------------- | :-------------- | :------------------------------------------------ |
| QDMI            | 1.4.0           | Interface headers and device declarations         |
| nlohmann/json   | 3.12.0          | JSON parsing and serialization                    |
| CPR             | 1.14.2          | HTTP requests through libcurl                     |
| AWS SDK for C++ | 1.11.700        | S3 URL signing; only core/S3 components are built |
| GoogleTest      | 1.17.0          | Native tests, when enabled                        |
| zlib | zlib-ng 2.1.3 | QPY compression and decompression |

The default build uses static CPR, curl, and zlib dependencies. An installed CPR
build also requires an installed zlib development package. Linux builds require
OpenSSL development headers; macOS wheels use Apple's native TLS backend.
GoogleTest is not installed with the device. See
[installation](installation.md#building-from-source) for the runtime and
development components and [development](development.md#python-checks) for wheel
builds.

## Python package and integrations

The base package bundles the native library and requires Python 3.11 or newer.
It declares no mandatory Python runtime dependencies. Optional integrations
install MQT Core in the Python environment; they are not bundled into this
project's wheel.

| Extra       | Requirement                                        | Purpose                                     |
| :---------- | :------------------------------------------------- | :------------------------------------------ |
| `qiskit`    | MQT Core with Qiskit                               | Qiskit backend and primitives               |
| `executor`  | MQT Core with Qiskit, `qiskit-ibm-runtime~=0.50.0` | Executor programs through QDMI              |
| `pennylane` | MQT Core with PennyLane and Qiskit                 | PennyLane devices and circuit serialization |

Follow [Python installation](installation.md#python-package) to select extras.
MQT Core is pinned to commit `e4cd6cfbe0efbd1d57dd34c9da6a16d7e08f9394`. Its
source build downloads LLVM/MLIR when needed. Core defines the transitive Qiskit
and PennyLane requirements. Replace this Git dependency with a released Core
version before publishing to PyPI.

## Build and development tools

[pyproject.toml](https://github.com/munich-quantum-software/ibm-qdmi-device/blob/main/pyproject.toml)
defines the build backend and dependency groups. These tools are not runtime
requirements of the installed device.

| Group      | Main tools                                                   | Purpose                                    |
| :--------- | :----------------------------------------------------------- | :----------------------------------------- |
| `build`    | scikit-build-core, build                                     | CMake integration and Python packaging     |
| `test`     | pytest, coverage and parallel-test plugins, MQT Core, PyYAML | Offline package and adapter tests          |
| `docs`     | Sphinx, Furo, MyST-NB, AutoAPI, Copybutton, Design           | Documentation and Python API generation    |
| `examples` | Test dependencies and MQT Bench                              | Runnable simulation and framework examples |
| `dev`      | Build, test, and example dependencies, Nox, Qiskit Nature    | Development and type checking              |

Native builds also require a C++20 compiler, CMake 3.24 or newer, and Git.
Documentation builds additionally require Doxygen on `PATH`; see
[documentation development](development.md#documentation) for the pinned version
and commands. Nox installs dependency groups for each session.
