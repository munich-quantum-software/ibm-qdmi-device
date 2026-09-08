# IBM QDMI Device

Project scaffold for an IBM implementation of the
[Quantum Device Management Interface (QDMI)](https://github.com/Munich-Quantum-Software-Stack/QDMI).

The native library and Python package build and install. Device functions,
backend access, and device discovery are not implemented. The package cannot
execute quantum programs.

## Build from source

A C++20 compiler, CMake 3.24 or newer, and Git are required. CMake downloads the
pinned QDMI headers and, when tests are enabled, GoogleTest.

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

- `cmake/` and `src/`: native build and installation configuration.
- `python/ibm/qdmi/`: Python package and version metadata.
- `test/`: native and Python packaging checks.
- `docs/`: Sphinx and Doxygen documentation sources.
- `.github/`: CI, packaging, and repository automation.

See [contributing](docs/contributing.md), [support](docs/support.md), and
[security](docs/security.md). Agent instructions are in [AGENTS.md](AGENTS.md).

## License

Licensed under [Apache-2.0 WITH LLVM-exception](LICENSE). The scaffold follows
the conventions of [QDMI on IQM](https://github.com/iqm-finland/QDMI-on-IQM) and
the
[Amazon Braket QDMI Device](https://github.com/munich-quantum-software/amazon-braket-qdmi-device).
