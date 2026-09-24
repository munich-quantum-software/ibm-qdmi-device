<!-- rumdl-disable MD033 MD041 -->
<p align="center">
  <a href="https://mq.sc/">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/_static/logo-mqsc-dark.svg">
      <img src="docs/_static/logo-mqsc-light.svg" alt="MQSC Logo" width="40%">
    </picture>
  </a>
</p>

# IBM QDMI Device

[![License](https://img.shields.io/badge/License-Apache--2.0_w%2F_LLVM--exception-blue?logo=apache&style=flat-square)](LICENSE)
[![C++20](https://img.shields.io/badge/C%2B%2B-20-blue?logo=cplusplus&style=flat-square)](https://isocpp.org/)
[![CMake](https://img.shields.io/badge/CMake-3.24%2B-blue?logo=cmake&style=flat-square)](https://cmake.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/munich-quantum-software/ibm-qdmi-device/ci.yml?branch=main&style=flat-square&logo=github&label=CI)](https://github.com/munich-quantum-software/ibm-qdmi-device/actions/workflows/ci.yml)
[![codecov](https://img.shields.io/codecov/c/github/munich-quantum-software/ibm-qdmi-device?style=flat-square&logo=codecov)](https://codecov.io/gh/munich-quantum-software/ibm-qdmi-device)

**IBM QDMI Device** connects IBM Quantum Platform to the
[Quantum Device Management Interface (QDMI)](https://github.com/Munich-Quantum-Software-Stack/QDMI),
a vendor-neutral C API for quantum hardware. The C++20 library handles API-key
authentication, calibration queries, and the job lifecycle. It submits OpenQASM
3 circuits and returns ordered shots and histograms. Optional Qiskit and
PennyLane integrations use the same native interface.

Live metadata validation has passed; quantum execution has not yet been
validated on hardware. Examples default to local simulation.

<p align="center">
  <a href="https://ibm-qdmi-device.readthedocs.io/en/latest/">
    <img width="30%" src="https://img.shields.io/badge/documentation-blue?style=for-the-badge&logo=read%20the%20docs" alt="Documentation">
  </a>
</p>
<!-- rumdl-enable MD033 MD041 -->

## Installation

Install from a source checkout with Python 3.11 or newer, a C++20 compiler,
CMake 3.24 or newer, and Git. Linux builds also require OpenSSL development
headers.

```console
uv venv
uv pip install .          # core library and Python entry points
uv pip install '.[qiskit]'  # adds the Qiskit backend (IBMBackend)
```

For C++ projects, follow the
[native installation guide](https://ibm-qdmi-device.readthedocs.io/en/latest/installation.html#native-package)
for CMake build and installation commands.

## Where to Start

| I want to…                                   | Guide                                                                                    |
| :------------------------------------------- | :--------------------------------------------------------------------------------------- |
| Run circuits from **Python / Qiskit**        | [Qiskit Integration](https://ibm-qdmi-device.readthedocs.io/en/latest/qiskit.html)       |
| Execute **PennyLane** QNodes                 | [PennyLane Integration](https://ibm-qdmi-device.readthedocs.io/en/latest/pennylane.html) |
| Walk through end-to-end workloads            | [Examples](https://ibm-qdmi-device.readthedocs.io/en/latest/examples.html)               |
| Integrate the **C++ library** directly       | [Usage Guide](https://ibm-qdmi-device.readthedocs.io/en/latest/api.html)                 |
| Understand the Python package's entry points | [Python Package](https://ibm-qdmi-device.readthedocs.io/en/latest/python_package.html)   |
| Contribute to the project                    | [Contributing](https://ibm-qdmi-device.readthedocs.io/en/latest/contributing.html)       |

## Contributing

Contributions are welcome, including bug reports, documentation improvements,
and new features. See the
[Contributing Guide](https://ibm-qdmi-device.readthedocs.io/en/latest/contributing.html)
for the development workflow, coding standards, and pull request process.

## License

The core C++ library and Python package are licensed under the
**Apache License 2.0 with LLVM exception**. See [LICENSE](LICENSE) for the
license text.
