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

The `ibm-qdmi-device_Runtime` component installs the shared library and device
catalogue. The `ibm-qdmi-device_Development` component installs headers, link
artifacts, and CMake package configuration. Install both to build a downstream
consumer.

Consumers use `find_package(ibm-qdmi-device 0.1 REQUIRED CONFIG)` and link
`ibm-qdmi-device::ibm-qdmi-device`. Set `CMAKE_PREFIX_PATH` to the installation
prefix. Headers use the `ibm_qdmi/` include directory.

The exported target carries `QDMI_DEVICE_ID`, `QDMI_DEVICE_PREFIX`, and
`QDMI_MANIFEST_NAME` properties. See the [usage guide](api.md) for the supported
interface and a query example.

## Python package

```console
uv venv
uv pip install .
```

Select an optional framework integration from the same checkout:

```console
uv pip install '.[qiskit]'
uv pip install '.[pennylane]'
```

The `pennylane` extra also installs Qiskit for circuit serialization. See the
[dependency overview](dependencies.md) for native libraries and Python extras.

The `ibm-qdmi` distribution installs the `ibm.qdmi` namespace. Its `data/`
directory contains the native runtime and development components. The package
includes typing metadata and exposes `ibm.qdmi.__version__`. See the
[Python package guide](python_package.md) for installed paths and CLI options.

## Device discovery

The relocatable `ibm-qdmi-device.qdmi.json` catalogue lives beside the shared
library. It contains `ibm.default`, `ibm.berlin`, and `ibm.aachen`. Concrete
entries set only the backend name. The generic entry requires an explicit
backend. Supply credentials and the instance CRN when opening a session; the
catalogue contains neither.

MQT Core users can set `MQT_CORE_QDMI_CONFIG_FILE` to the catalogue path before
importing its driver. The driver resolves the library relative to that file.
Move the catalogue and library together when relocating a native installation.

`ibm-qdmi --catalog_path` prints the installed catalogue path without loading a
device or contacting IBM. See the
[information CLI](python_package.md#command-line-interface) for the remaining
options and the equivalent `python -m ibm.qdmi` interface.

See [development](development.md) for wheel and source-distribution checks.
