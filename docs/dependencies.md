# Dependencies

`uv.lock` records the resolved Python environment. Native dependency versions
are configured in CMake.

## Native dependencies

[ExternalDependencies.cmake](https://github.com/munich-quantum-software/ibm-qdmi-device/blob/main/cmake/ExternalDependencies.cmake)
configures QDMI headers, nlohmann/json, CPR, and GoogleTest. The build fetches
static CPR, uses SDK curl on macOS, and fetches curl elsewhere. Linux builds
require OpenSSL development headers. GoogleTest is required only for native
tests and is not installed with the device. See
[installation](installation.md#building-from-source) for the runtime and
development components and [development](development.md#python-checks) for wheel
builds.

## Python package and integrations

The base package bundles the native library and requires Python 3.11 or newer.
It declares no mandatory Python runtime dependencies. Optional integrations
install MQT Core in the Python environment; they are not bundled into this
project's wheel.

| Extra       | Requirement                                             | Purpose                                     |
| :---------- | :------------------------------------------------------ | :------------------------------------------ |
| `qiskit`    | `mqt-core[qiskit]~=4.1.1`                               | Qiskit backend and primitives               |
| `executor`  | `mqt-core[qiskit]~=4.1.1`, `qiskit-ibm-runtime~=0.50.0` | Executor programs through QDMI              |
| `pennylane` | `mqt-core[pennylane,qiskit]~=4.1.1`                     | PennyLane devices and circuit serialization |

Follow [Python installation](installation.md#python-package) to select extras.
MQT Core defines their transitive Qiskit and PennyLane requirements.

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
