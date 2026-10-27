# Development and testing

## Environment

Install development tools without building the project:

```console
uv sync --locked --only-group dev
```

Use separate directories under `build/` for native, wheel, documentation, and
installed-package builds. Run package builds sequentially within a checkout. Nox
installs each session's dependency groups and builds the package as needed.
Local tests use synthetic data and simulators; live checks require the explicit
flags below. CI also checks read-only IBM metadata. Dependency installation
requires network access.

## Native checks

```console
cmake --preset release
cmake --build --preset release
ctest --preset release
uvx nox -s native_tests
cmake -P test/install.cmake
```

GoogleTest exercises native components and the C API. The `native_tests` session
checks the installed ABI and real HTTP transport against a loopback server. It
runs separately from framework tests because MQT Core retains its driver library
while ABI tests own initialization and finalization. `test/install.cmake` checks
installation, relocation, and a CMake consumer.

Use the `debug` preset for a debug build. On Linux, add
`-DIBM_QDMI_SANITIZERS="address;undefined"` when configuring for sanitizer
checks. For coverage, select the instrumented library explicitly in the ABI
tests:

```console
cmake -S . -B build/coverage -DCMAKE_BUILD_TYPE=Debug -DIBM_QDMI_ENABLE_COVERAGE=ON
cmake --build build/coverage --config Debug
ctest --test-dir build/coverage -C Debug --output-on-failure
uvx nox -s native_tests -- --native-library="$PWD/build/coverage/src/libibm-qdmi-device.so"
uvx nox -s tests-3.14 -- --cov=ibm.qdmi --cov-report=xml:build/python-coverage/coverage.xml
```

Coverage runs receive no IBM credentials. Never submit hardware jobs to increase
coverage. Python coverage measures Python code; native coverage requires the
instrumented library.

## Python checks

```console
uvx nox -s tests-3.14 -- test/python/test_qiskit_backend.py
uvx nox -s tests minimums
```

Nox tests Python 3.11 through 3.15. The `minimums` sessions resolve minimum
direct dependencies and restore `uv.lock` afterward. Framework tests use the
installed device with a synthetic IBM service and local circuit simulation.
Draft PRs run `tests-3.14` and `native_tests`; review-ready PRs run all test and
minimum-version sessions. Hardware requests test a fresh candidate wheel offline
before submitting jobs.

Pytest selection and registered markers live in `pyproject.toml`:

| Selection              | Purpose                           |
| ---------------------- | --------------------------------- |
| `-m integration -n 0`  | Native ABI and loopback transport |
| `-m "not integration"` | Package and framework tests       |

The `live` and `quantum` markers require their opt-in flags even when selected.

Build a wheel from the source distribution:

```console
uv run --only-group build python -m build --outdir build/dist
```

Install it in a fresh environment with
`uv pip install --python <environment-python> <wheel-path>`, install the test
dependency group, and run the integration and package selections separately. The
package version comes from `project()` in `CMakeLists.txt`.

The native library uses ctypes, so one wheel per platform supports Python 3.11
and newer. CI builds and tests it with Python 3.13 through cibuildwheel; Nox
covers the supported Python versions. Windows ARM wheels are built and repaired,
but optional framework dependencies prevent Python wheel tests there; native
Windows ARM tests run separately.

## Live IBM metadata

CI checks `ibm_berlin` and `ibm_aachen` metadata on same-repository PRs, merge
queues, and `main`. These read-only requests submit no jobs and consume no
[QPU time](https://quantum.cloud.ibm.com/docs/en/guides/estimate-job-run-time).
Fork PRs receive no credentials. The workflow can also be dispatched on `main`:

```console
gh workflow run live-metadata.yml --ref main
```

The `ibm-quantum` environment supplies `IBM_QUANTUM_API_KEY` and
`IBM_QUANTUM_INSTANCE_CRN` only to the live step after package installation. The
library derives the API region from the CRN. Each run checks the backends
sequentially, has a 15-minute timeout, and is never retried automatically.

For a local metadata check, supply those variables securely and run:

```console
uvx nox -s live-metadata -- both
```

The session removes credentials from the wheel build environment. To check an
already installed wheel with the test dependencies:

```console
python -m pytest test/python/test_live_metadata.py --run-live --ibm-backend both -n 0 --tb=line --show-capture=no
```

Checks cover session initialization, physical indices, operations, calibration,
status, and queue queries. Optional metadata may be unsupported. Reports use
fixed diagnostic categories and QDMI status codes. Do not enable HTTP debugging
or retain raw responses, account details, topology, or calibration snapshots.
Reproduce compatibility failures with synthetic fixtures before fixing them.

## Gated quantum execution

Hardware checks require an explicit, authorized request. Dispatch the hardware
workflow on merged `main`, or add `live-qpu-tests` to a same-repository PR. Fork
PRs remain offline. Main pushes and ordinary PR updates never run hardware.

```console
gh workflow run hardware.yml --ref main
```

The `ibm-quantum` environment allows `main`, `refs/pull/*/merge`, and
`gh-readonly-queue/main/*`. Keep its protection rules enabled. Each request runs
native CTest, then builds and installs a candidate wheel. Its offline package
and ABI tests must pass before hardware validation uses that same installation.
Secrets are available only during the final test step.

Adding the label starts one fresh validation of the PR merge commit. Keeping the
label does not opt later commits into hardware checks. To request another run,
remove and add the label again after authorizing another budget. Workflow and
individual-job reruns reject hardware execution; they cannot repeat a
submission. Removing the label does not cancel jobs already submitted.

Each eligible run uses this budget:

| Setting       | Limit                                      |
| ------------- | ------------------------------------------ |
| Backends      | Berlin, then Aachen                        |
| Jobs          | One per backend                            |
| Programs      | Two per job, 64 shots each                 |
| QPU execution | 60 seconds per job                         |
| Wait          | One hour per backend, including queue time |

The circuits test a Bell pair and distinguish program order with a third qubit.
Checks compare indexed counts and memory, require at least 75% expected outcomes
and 10% for each Bell outcome, then retrieve the job in a fresh session without
resubmitting. Sampler and estimator checks remain offline.

Failures and timeouts trigger a cancellation attempt before releasing handles;
cancellation can race with completion, and runner termination can prevent
cleanup. Freeing a handle does not cancel a remote job. Runs are serialized
without automatic cancellation or retries; rerunning requires an authorized
budget. Do not make development-time hardware submissions.

The `quantum` marker requires `--run-quantum`; `--run-live` enables metadata
only. Ordinary tests skip both before reading credentials. Hardware reports
retain only backend names, outcomes, and fixed diagnostic categories. They
produce no result artifacts or logs containing job IDs, credentials, CRNs, raw
responses, topology, or calibration snapshots.

## Lint

```console
uvx nox -s lint
```

This runs the prek hooks, including formatting, spelling, license headers,
metadata, lockfile checks, workflow security, Ruff, and ty. Inspect automatic
edits and rerun until clean. Check untracked files with
`uvx prek run --files <paths>`.

For C++, use Clang 23 and the `lint` CMake preset to generate a Ninja
compilation database. The shared linter in `.github/workflows/ci.yml` runs
clang-format and clang-tidy on every line of each changed file, including tests.

## Documentation

Install Doxygen 1.16.1 on `PATH`, then run:

```console
uvx nox --non-interactive -s docs
uvx nox --non-interactive -s docs -- -b linkcheck
```

The session builds the package in `build/docs/`, generates the native reference
with Doxygen, and builds Sphinx pages in `docs/_build/html/`. The native
reference lives under `cpp/`; Python API pages come from AutoAPI. Warnings fail
the build. Edit public header comments and Python docstrings for API references.

## Automation

CI covers native and Python tests, installation, sanitizers, coverage, lint, and
source and wheel distributions. The `🚦 Check` aggregate rejects failed or
cancelled prerequisites. PRs use change detection; `main` runs the full offline
suite. Metadata checks run on every trusted CI run. Hardware validation runs
independently. The main ruleset also requires `pre-commit.ci - pr` and the Read
the Docs preview before merging.

Read the Docs publishes PR previews and `latest` from `main` using the strict
documentation session. Release workflows attest and publish distributions to
PyPI through trusted publishing after a GitHub release. The `pypi` environment
permits `v*` tags; manual CD runs only build artifacts. Coverage uploads to
Codecov use OpenID Connect. Native coverage combines CTest and the offline
transport tests; Python coverage reuses the reports from the Python test
sessions.
