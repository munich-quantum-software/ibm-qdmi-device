# Dependencies

Versions below follow
[CMake](https://github.com/munich-quantum-software/ibm-qdmi-device/blob/main/cmake/ExternalDependencies.cmake)
and
[pyproject.toml](https://github.com/munich-quantum-software/ibm-qdmi-device/blob/main/pyproject.toml).
`uv.lock` records the resolved Python environment.

## Native dependencies

CPR and nlohmann/json are compiled into the device library. curl is linked
statically on Linux and Windows; macOS uses the system library. QDMI supplies
interface headers, including the generated IBM declarations installed with the
development package; no QDMI driver library is linked into the device.

| Dependency      | Version                         | License                        | Purpose                        |
| :-------------- | :------------------------------ | :----------------------------- | :----------------------------- |
| [QDMI]          | 1.4.0                           | Apache-2.0 WITH LLVM-exception | Device interface and headers   |
| [nlohmann/json] | 3.12.0                          | MIT                            | JSON parsing and serialization |
| [CPR]           | 1.15.1                          | MIT                            | C++ HTTP client                |
| [curl]          | 8.23.0; system version on macOS | curl                           | HTTP transport                 |
| [OpenSSL]       | ≥3; Linux                       | Apache-2.0                     | TLS                            |

Linux wheels bundle OpenSSL; native builds use the installed OpenSSL development
package. Windows uses Schannel and macOS uses system curl's TLS implementation.
Updating a bundled library requires rebuilding the wheel.

## Python package and integrations

The base package requires Python 3.11 or newer and has no Python runtime
dependencies. Extras install the following packages into the user's environment;
they are **not bundled** in the IBM wheel. MQT Core's extras supply Qiskit and
PennyLane and define their supported versions.

| Dependency           | Version  | License    | Purpose                                                                   |
| :------------------- | :------- | :--------- | :------------------------------------------------------------------------ |
| [MQT Core]           | ~=4.1.1  | MIT        | QDMI driver and adapters for `qiskit`, `executor`, and `pennylane` extras |
| [Qiskit Algorithms]  | ≥0.4     | Apache-2.0 | VQE offloading in the `qiskit` extra                                      |
| [Qiskit IBM Runtime] | ~=0.50.0 | Apache-2.0 | Executor encoding and decoding in the `executor` extra                    |

See [installation](installation.md#python-package) to select extras.

## Build and development tools

These tools are **not shipped** in the device library or wheel. Native builds
also require a C++20 compiler, CMake 3.24 or newer, and Git. Nox installs the
Python dependency groups needed for each session; see
[development](development.md).

| Dependency          | Version     | License                    | Purpose                                                            |
| :------------------ | :---------- | :------------------------- | :----------------------------------------------------------------- |
| [scikit-build-core] | ≥1.1        | Apache-2.0                 | Python build backend and CMake integration                         |
| [build]             | ≥1.2.2      | MIT                        | Source and wheel distribution builds                               |
| [Nox]               | ≥2026.8.10  | Apache-2.0                 | Development sessions                                               |
| [GoogleTest]        | 1.18.0      | BSD-3-Clause               | Native tests                                                       |
| [pytest]            | ≥9.1.1      | MIT                        | Python tests                                                       |
| [pytest-cov]        | ≥7.1        | MIT                        | Python coverage                                                    |
| [pytest-sugar]      | ≥1.1.1      | BSD-3-Clause               | Test output                                                        |
| [pytest-xdist]      | ≥3.8        | MIT                        | Parallel tests                                                     |
| [PyYAML]            | ≥6.0.2      | MIT                        | Workflow tests                                                     |
| [cryptography]      | ≥42         | Apache-2.0 OR BSD-3-Clause | TLS test certificates                                              |
| [trustme]           | ≥1.2.1      | MIT OR Apache-2.0          | Local TLS test fixtures                                            |
| [MQT Bench]         | ≥2.2.2      | MIT                        | Benchmark examples                                                 |
| [Qiskit Nature]     | ≥0.7.2      | Apache-2.0                 | Chemistry examples; its `pyscf` extra supplies molecular integrals |
| [Doxygen]           | 1.16.1      | GPL-2.0                    | Native API reference                                               |
| [Sphinx]            | ≥9          | BSD-2-Clause               | Documentation site                                                 |
| [MyST-NB]           | ≥1.4        | BSD-3-Clause               | Markdown and executable notebook pages                             |
| [Furo]              | ≥2025.12.19 | MIT                        | Documentation theme                                                |
| [Sphinx AutoAPI]    | ≥3.6.1      | MIT                        | Python API reference                                               |
| [Sphinx Copybutton] | ≥0.5.2      | MIT                        | Code-block copy buttons                                            |
| [Sphinx Design]     | ≥0.7        | MIT                        | Documentation layout components                                    |

[build]: https://github.com/pypa/build
[CPR]: https://github.com/libcpr/cpr
[cryptography]: https://github.com/pyca/cryptography
[curl]: https://curl.se/
[Doxygen]: https://www.doxygen.nl/
[Furo]: https://github.com/pradyunsg/furo
[GoogleTest]: https://github.com/google/googletest
[MQT Bench]: https://mqt.readthedocs.io/projects/bench/
[MQT Core]: https://mqt.readthedocs.io/projects/core/
[MyST-NB]: https://github.com/executablebooks/MyST-NB
[nlohmann/json]: https://github.com/nlohmann/json
[Nox]: https://github.com/wntrblm/nox
[OpenSSL]: https://openssl-library.org/
[pytest]: https://github.com/pytest-dev/pytest
[pytest-cov]: https://github.com/pytest-dev/pytest-cov
[pytest-sugar]: https://github.com/Teemu/pytest-sugar
[pytest-xdist]: https://github.com/pytest-dev/pytest-xdist
[PyYAML]: https://github.com/yaml/pyyaml
[QDMI]: https://github.com/Munich-Quantum-Software-Stack/qdmi
[Qiskit Algorithms]: https://github.com/qiskit-community/qiskit-algorithms
[Qiskit IBM Runtime]: https://github.com/Qiskit/qiskit-ibm-runtime
[Qiskit Nature]: https://github.com/qiskit-community/qiskit-nature
[scikit-build-core]: https://github.com/scikit-build/scikit-build-core
[Sphinx]: https://github.com/sphinx-doc/sphinx
[Sphinx AutoAPI]: https://github.com/readthedocs/sphinx-autoapi
[Sphinx Copybutton]: https://github.com/executablebooks/sphinx-copybutton
[Sphinx Design]: https://github.com/executablebooks/sphinx-design
[trustme]: https://github.com/python-trio/trustme
