# Dependencies

Versions below follow
[CMake](https://github.com/munich-quantum-software/ibm-qdmi-device/blob/main/cmake/ExternalDependencies.cmake)
and
[pyproject.toml](https://github.com/munich-quantum-software/ibm-qdmi-device/blob/main/pyproject.toml).
`uv.lock` records the resolved Python environment.

## Native dependencies

CPR, zlib-ng, and nlohmann/json are compiled into the device library. curl is
linked statically on Linux and Windows; macOS uses the system library. QDMI
supplies interface headers, including the generated IBM declarations installed
with the development package; no QDMI driver library is linked into the device.

| Dependency      | Version                         | License                        | Purpose                        |
| :-------------- | :------------------------------ | :----------------------------- | :----------------------------- |
| [QDMI]          | 1.4.0                           | Apache-2.0 WITH LLVM-exception | Device interface and headers   |
| [nlohmann/json] | 3.12.0                          | MIT                            | JSON parsing and serialization |
| [CPR]           | 1.15.1                          | MIT                            | C++ HTTP client                |
| [curl]          | 8.23.0; system version on macOS | curl                           | HTTP transport                 |
| [zlib-ng]       | 2.3.3                           | Zlib                           | QPY compression                |
| [OpenSSL]       | ≥3; Linux                       | Apache-2.0                     | TLS                            |

Linux wheels bundle OpenSSL; native builds use the installed OpenSSL development
package. Windows uses Schannel and macOS uses system curl's TLS implementation.
Updating a bundled library requires rebuilding the wheel.

## Python package and integrations

The base package requires Python 3.11 or newer and has no Python runtime
dependencies. Extras install the following packages into the user's environment;
they are **not bundled** in the IBM wheel. MQT Core's extras supply Qiskit and
PennyLane and define their supported versions.

| Dependency           | Version            | License    | Purpose                                                                           |
| :------------------- | :----------------- | :--------- | :-------------------------------------------------------------------------------- |
| [MQT Core]           | [package metadata] | MIT        | QDMI driver and adapters for `qiskit`, `executor`, `mock`, and `pennylane` extras |
| [Qiskit IBM Runtime] | ~=0.50.0           | Apache-2.0 | Executor encoding and fake metadata in the `executor` and `mock` extras           |

See [installation](installation.md#python-package) to select extras.

[CPR]: https://github.com/libcpr/cpr
[curl]: https://curl.se/
[MQT Core]: https://mqt.readthedocs.io/projects/core/
[nlohmann/json]: https://github.com/nlohmann/json
[OpenSSL]: https://openssl-library.org/
[QDMI]: https://github.com/Munich-Quantum-Software-Stack/qdmi
[Qiskit IBM Runtime]: https://github.com/Qiskit/qiskit-ibm-runtime
[zlib-ng]: https://github.com/zlib-ng/zlib-ng

[package metadata]: https://github.com/munich-quantum-software/ibm-qdmi-device/blob/main/pyproject.toml
