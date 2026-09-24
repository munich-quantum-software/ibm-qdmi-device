# IBM QDMI Device

<!-- rumdl-disable MD033 -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/_static/logo-mqsc-dark.svg">
  <img src="docs/_static/logo-mqsc-light.svg" alt="Munich Quantum Software Company" width="280">
</picture>
<!-- rumdl-enable MD033 -->

[![CI](https://img.shields.io/github/actions/workflow/status/munich-quantum-software/ibm-qdmi-device/ci.yml?branch=main&style=flat-square&logo=github&label=CI)](https://github.com/munich-quantum-software/ibm-qdmi-device/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache--2.0_WITH_LLVM--exception-blue?style=flat-square)](LICENSE)
[![C++20](https://img.shields.io/badge/C%2B%2B-20-blue?logo=cplusplus&style=flat-square)](https://isocpp.org/)
[![CMake](https://img.shields.io/badge/CMake-3.24%2B-blue?logo=cmake&style=flat-square)](https://cmake.org/)
![OS](https://img.shields.io/badge/os-linux%20%7C%20macos%20%7C%20windows-blue?style=flat-square)
[![pre-commit.ci](https://results.pre-commit.ci/badge/github/munich-quantum-software/ibm-qdmi-device/main.svg)](https://results.pre-commit.ci/latest/github/munich-quantum-software/ibm-qdmi-device/main)
[![codecov](https://img.shields.io/codecov/c/github/munich-quantum-software/ibm-qdmi-device?style=flat-square&logo=codecov)](https://codecov.io/gh/munich-quantum-software/ibm-qdmi-device)

IBM quantum execution through the
[Quantum Device Management Interface (QDMI)](https://github.com/Munich-Quantum-Software-Stack/QDMI).

The native library authenticates with IBM Quantum Platform and exposes backend,
site, and operation metadata through QDMI. It submits native OpenQASM 3
circuits, manages jobs, and returns ordered shots and histograms. Live metadata
validation has passed; quantum execution has not yet been validated on hardware.
See the [usage guide](docs/api.md) for the supported interface and
configuration. The optional [Qiskit integration](docs/qiskit.md) supports
transpilation, execution, ordered memory, and sampler and estimator primitives.

Start with [installation](docs/installation.md), then follow the
[runnable examples](docs/examples.md) for native QDMI jobs, Bell sampling, MQT
Bench circuits, H₂ energy estimation, and PennyLane QAOA. Examples default to
local simulation and require an explicit IBM device selection for hardware.

## Where to start

| Task                                        | Guide                                                     |
| ------------------------------------------- | --------------------------------------------------------- |
| Install native or Python packages           | [Installation](docs/installation.md)                      |
| Select a device and locate the catalogue    | [Device discovery](docs/installation.md#device-discovery) |
| Locate Python package files and use the CLI | [Python package](docs/python_package.md)                  |
| Configure sessions and manage jobs          | [QDMI API](docs/api.md)                                   |
| Transpile and execute Qiskit circuits       | [Qiskit](docs/qiskit.md)                                  |
| Execute PennyLane QNodes                    | [PennyLane](docs/pennylane.md)                            |
| Run complete workloads                      | [Examples](docs/examples.md)                              |
| Build, test, and contribute                 | [Development](docs/development.md)                        |

## Build and install

A C++20 compiler, CMake 3.24 or newer, and Git are required. CMake downloads the
pinned QDMI headers, CPR/curl, JSON dependencies, and GoogleTest when tests are
enabled. Linux builds also require OpenSSL development headers.

```console
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native --config Release
ctest --test-dir build/native -C Release --output-on-failure
```

To install the Python package from this checkout with Python 3.11 or newer:

```console
uv venv
uv pip install .
```

See [installation](docs/installation.md) for native installation and package
contents, and [development](docs/development.md) for validation commands.

## Project layout

- `src/` and `include/`: native implementation and public IBM constants.
- `cmake/`: native build and installation configuration.
- `python/ibm/qdmi/`: Python package, installed paths, and information CLI.
- `test/`: native unit tests and Python tests using a loopback IBM service.
- `examples/`: runnable native and framework workloads.
- `docs/`: Sphinx and Doxygen documentation sources.
- `.github/`: CI, packaging, and repository automation.

See [contributing](docs/contributing.md), [support](docs/support.md), and
[security](docs/security.md). Agent instructions are in [AGENTS.md](AGENTS.md).

## License

Licensed under [Apache-2.0 WITH LLVM-exception](LICENSE).
