# Installation

Install from a source checkout. No published release is required or assumed. Use
a C++20 compiler, CMake 3.24 or newer, Git, and Python 3.11 or newer for Python
packaging. Linux builds require OpenSSL development headers. Dependency
downloads need network access; tests use synthetic data and loopback HTTP,
without IBM access or credentials.

## Native package

```console
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release -DBUILD_IBM_QDMI_TESTS=OFF
cmake --build build/native --config Release
cmake --install build/native --config Release --prefix build/install/prefix
```

The `ibm-qdmi-device_Runtime` component installs the shared library. The
`ibm-qdmi-device_Development` component installs headers, link artifacts, and
CMake package configuration. Install both to build a downstream consumer.

Consumers use `find_package(ibm-qdmi-device 0.1 REQUIRED CONFIG)` and link
`ibm-qdmi-device::ibm-qdmi-device`. Set `CMAKE_PREFIX_PATH` to the installation
prefix. Headers use the `ibm_qdmi/` include directory.

Lifecycle, session, and metadata-query functions are implemented. Job functions
remain declarations only and fail to link if called. No discovery manifest is
installed. See [API status](api.md) for the supported interface and a query
example.

## Python package

```console
uv venv
uv pip install .
```

The `ibm-qdmi` distribution installs the `ibm.qdmi` namespace. Its `data/`
directory contains the native runtime and development components. The package
includes typing metadata and exposes `ibm.qdmi.__version__`.

See [development](development.md) for wheel and source-distribution checks.
