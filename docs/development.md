# Development and testing

## Environment

Use uv for dependency management and Nox for automation. Install development
dependencies without building the project:

```console
uv sync --locked --only-group dev
```

Use separate directories under `build/` for native, wheel, documentation, and
installed-package builds. Do not run two Nox package builds concurrently in the
same checkout. Ordinary tests are offline with respect to quantum backends;
dependency installation may download packages. Live metadata checks require the
explicit opt-in described below.

## Native checks

```console
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native --config Release
ctest --test-dir build/native -C Release --output-on-failure
```

Use `Debug` in both configuration and build commands for a debug build. The
native check compiles QDMI headers as C and C++ and links the shared library. It
also exercises session configuration, IAM refresh, metadata parsing, and error
mapping using synthetic responses.

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
metadata, headers, CMake exports, and shared-library loading. Backend
integration tests run the installed C ABI against an ephemeral loopback HTTP
server. They verify authentication headers, error recovery, session isolation,
and property queries without contacting IBM. The synthetic fixture in
`test/fixtures/` models IBM API version `2026-04-15`; no recorded account data
is used.

Build an sdist and a wheel from that sdist:

```console
uv run --only-group build python -m build --outdir build/dist
```

Install the resulting wheel into a fresh environment with
`uv pip install --python <environment-python> <wheel-path>`, install the test
dependency group, and run `pytest test/python` using that interpreter. CI also
builds and tests platform wheels with cibuildwheel.

The Linux wheel containers install OpenSSL development files before building.
macOS wheels use Apple's native TLS backend and disable optional curl libraries
from Homebrew so that their deployment requirements do not raise the wheel's
minimum supported macOS version.

## Live IBM metadata

Live validation is separate from ordinary CI and the required-check aggregate.
It checks the installed wheel's C ABI against `ibm_berlin` (120 qubits) and
`ibm_aachen` (156 qubits). It submits no quantum jobs. A successful offline run
does not establish live compatibility; live validation remains unperformed until
a manual run succeeds after this workflow is merged.

After human merge, open **Actions → Live IBM metadata → Run workflow**. Select
the `main` branch and `both` (the default), `ibm_berlin`, or `ibm_aachen`. The
equivalent command is:

```console
gh workflow run live-metadata.yml --ref main -f backend=both
```

The workflow checks out the dispatch commit and permits only `refs/heads/main`.
The `ibm-quantum` environment must use **Selected branches and tags** with a
single **branch** rule, `main`. Keep the existing `IBM_QUANTUM_API_KEY` and
`IBM_QUANTUM_INSTANCE_CRN` environment secrets. Build and installation steps run
before the live step receives these secrets. The library derives the region from
the CRN; this workflow has no endpoint override. Runs are serialized and have a
15-minute timeout, with no schedules or automatic retries.

For an explicitly authorized local run from merged `main`, supply the same two
environment variables through a secure credential source, then run:

```console
uvx nox -s live-metadata -- both
```

The non-default session builds and installs a wheel with credentials removed
from the build environment. To use an already installed wheel and test group:

```console
python -m pytest test/python/test_live_metadata.py --run-live --ibm-backend both -n 0 --tb=line --show-capture=no
```

Live tests are skipped before credential access in ordinary pytest, Nox, and
wheel tests, even if credentials are present. Explicit live runs reject missing
credentials and invalid backend selections. Backends run sequentially, each with
one session that is freed on success or failure. Checks exercise size queries,
identity, physical indices, coupling ownership, operation metadata and site
tuples, optional calibration ranges, current status, and queue length. Busy
backends and `QDMI_ERROR_NOTSUPPORTED` for optional metadata are accepted; gate
lists and changing calibration values are not pinned.

Reports contain backend names, outcomes, and fixed diagnostic categories or QDMI
status codes. Traceback locals, exception chains, and captured output are
suppressed. Do not enable HTTP debugging, attach account data, or upload raw
responses, topology dumps, or calibration snapshots. This workflow creates no
result artifacts. Review its redacted result after dispatch. Any compatibility
fix needs a synthetic regression test and a follow-up PR; quantum execution
requires a separately agreed budget.

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
