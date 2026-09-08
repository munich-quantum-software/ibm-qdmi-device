# Development and testing

## Environment

Use uv for dependency management and Nox for automation. Install development
dependencies without building the project:

```console
uv sync --locked --only-group dev
```

Use separate directories under `build/` for native, wheel, documentation, and
installed-package builds. Do not run two Nox package builds concurrently in the
same checkout. All tests are offline with respect to quantum backends;
dependency installation may download packages.

## Native checks

```console
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native --config Release
ctest --test-dir build/native -C Release --output-on-failure
```

Use `Debug` in both configuration and build commands for a debug build. The
native check compiles QDMI headers as C and C++ and links the shared library. It
does not exercise device behavior.

Test installation, relocation, and an installed-package consumer:

```console
cmake -P test/install.cmake
```

Enable Linux sanitizer checks in a separate build with
`-DIBM_QDMI_SANITIZERS="address;undefined" -DCMAKE_BUILD_TYPE=Debug`. Enable
native coverage with `-DIBM_QDMI_ENABLE_COVERAGE=ON`.

## Python checks

The Python package derives its version from the `project()` declaration in
`CMakeLists.txt`. Update that version for both native and Python releases.

```console
uvx nox -s tests-3.14 -- test/python/test_package.py
uvx nox -s tests minimums
```

Nox tests Python 3.11 through 3.14. The minimums sessions resolve minimum direct
dependencies and restore `uv.lock` afterward. Tests inspect installed package
metadata, headers, CMake exports, and shared-library loading.

Build an sdist and a wheel from that sdist:

```console
uv run --only-group build python -m build --outdir build/dist
```

Install the resulting wheel into a fresh environment with
`uv pip install --python <environment-python> <wheel-path>`, install the test
dependency group, and run `pytest test/python` using that interpreter. CI also
builds and tests platform wheels with cibuildwheel.

## Lint

```console
uvx nox -s lint
```

This runs the complete prek hook set, including formatting, spelling, license
headers, metadata, lockfile, workflow security, Ruff, and ty. Hooks can change
files; inspect the changes and rerun until clean. To check new untracked files
before staging, use `uvx prek run --files <paths>`.

For C++ files, reproduce `.github/workflows/cpp-linter.yml` with its Clang
version and a Ninja compilation database. Check every line of each changed file
with clang-format and clang-tidy, including native tests. Do not restrict checks
to changed lines.

## Documentation

Install Doxygen on `PATH`, then run:

```console
uvx nox --non-interactive -s docs
uvx nox --non-interactive -s docs -- -b linkcheck
```

The session builds the package in `build/docs/`, generates standalone Doxygen
HTML, and builds Sphinx with warnings treated as errors. HTML output is in
`docs/_build/html/`, with the generated C interface under `cpp/`.

## Automation setup

CI validates builds and produces artifacts without backend credentials. Read the
Docs configuration is included, but hosting must be provisioned separately.
Release workflows publish only after a GitHub release is published and the
`pypi` environment and PyPI trusted publisher have been configured. Manual CD
runs only build artifacts. Enable Codecov uploads by setting the repository
variable `CODECOV_ENABLED` to `true` after configuring the service.
