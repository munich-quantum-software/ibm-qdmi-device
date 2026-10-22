# Installation

## Python package

Install the `ibm-qdmi` distribution from
[PyPI](https://pypi.org/project/ibm-qdmi/) with Python 3.11 or newer:

```console
uv venv
uv pip install ibm-qdmi
```

Select optional framework integrations with extras:

```console
uv pip install "ibm-qdmi[qiskit]"
uv pip install "ibm-qdmi[executor]"
uv pip install "ibm-qdmi[pennylane]"
```

The `executor` extra adds `qiskit-ibm-runtime` for
[Executor programs](qiskit.md#optional-executor-primitive). The `pennylane`
extra also installs Qiskit for circuit serialization. See the
[dependency overview](dependencies.md) for native libraries and Python extras.

Prebuilt wheels are available for Linux (x86_64, aarch64; glibc 2.28 or newer),
macOS (arm64, 13 or newer), and Windows (x86_64, ARM64). On other platforms, the
installer builds the source distribution, which requires the
[build tools](#building-from-source).

The `ibm-qdmi` distribution installs the `ibm.qdmi` namespace. Its `data/`
directory contains the native runtime and development components. The package
includes typing metadata and exposes `ibm.qdmi.__version__`. See the
[Python package guide](python_package.md) for installed paths and CLI options.

## Native package

The wheel includes the headers and CMake package configuration. C and C++
projects can build against an installed wheel by passing
`-DCMAKE_PREFIX_PATH="$(ibm-qdmi --cmake_dir)"` to CMake. To install the native
library without Python, build it from a source checkout as described below.

## Building from source

Building requires a C++20 compiler, CMake 3.24 or newer, Git, and Python 3.11 or
newer for Python packaging. Linux builds require OpenSSL development headers.
Dependency downloads need network access.

Clone the repository and build the native package:

```console
git clone https://github.com/munich-quantum-software/ibm-qdmi-device.git
cd ibm-qdmi-device
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

To build and install the Python package and its extras from the checkout instead
of PyPI:

```console
uv venv
uv pip install .
uv pip install ".[qiskit]"
uv pip install ".[executor]"
uv pip install ".[pennylane]"
```

## TLS certificates

Linux clients discover the host CA bundle on Debian/Ubuntu, RHEL, SUSE, and
Alpine. Install the distribution's `ca-certificates` package if it is missing.
Other platforms retain libcurl's default trust configuration.

For a private CA or nonstandard location, set `CURL_CA_BUNDLE` to a PEM bundle.
`SSL_CERT_FILE` is used when `CURL_CA_BUNDLE` is unset or empty. Invalid
explicit paths fail requests; certificate and hostname verification remain
enabled. These settings apply to both native and Python clients.

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
