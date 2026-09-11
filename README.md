# IBM QDMI Device

[![CI](https://img.shields.io/github/actions/workflow/status/munich-quantum-software/ibm-qdmi-device/ci.yml?branch=main&style=flat-square&logo=github&label=CI)](https://github.com/munich-quantum-software/ibm-qdmi-device/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache--2.0_WITH_LLVM--exception-blue?style=flat-square)](LICENSE)
[![C++20](https://img.shields.io/badge/C%2B%2B-20-blue?logo=cplusplus&style=flat-square)](https://isocpp.org/)
[![CMake](https://img.shields.io/badge/CMake-3.24%2B-blue?logo=cmake&style=flat-square)](https://cmake.org/)

IBM cloud backend queries through the
[Quantum Device Management Interface (QDMI)](https://github.com/Munich-Quantum-Software-Stack/QDMI).

The native library authenticates with IBM Quantum Platform and exposes backend,
site, and operation metadata through QDMI. Job execution and device discovery
are not implemented. See [API status](docs/api.md) for supported queries and
session configuration.

## Build from source

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
- `python/ibm/qdmi/`: Python package and version metadata.
- `test/`: native unit tests and Python tests using a loopback IBM service.
- `docs/`: Sphinx and Doxygen documentation sources.
- `.github/`: CI, packaging, and repository automation.

See [contributing](docs/contributing.md), [support](docs/support.md), and
[security](docs/security.md). Agent instructions are in [AGENTS.md](AGENTS.md).

## License

Licensed under [Apache-2.0 WITH LLVM-exception](LICENSE). The project follows
the conventions of [QDMI on IQM](https://github.com/iqm-finland/QDMI-on-IQM) and
the
[Amazon Braket QDMI Device](https://github.com/munich-quantum-software/amazon-braket-qdmi-device).
