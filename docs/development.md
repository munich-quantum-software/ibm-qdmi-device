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
flags below. CI checks read-only IBM metadata in parallel with offline tests and
wheel builds. Dependency installation requires network access.

## C++ and integration checks

```console
cmake --preset release
cmake --build --preset release
ctest --preset release
uvx nox -s integration_tests
cmake -P test/install.cmake
```

GoogleTest exercises C++ components and the C API. The `integration_tests`
session checks the installed C ABI and HTTP transport against a loopback server.
It runs separately from framework tests because it owns device initialization
and finalization. `test/install.cmake` checks installation, relocation, and a
CMake consumer.

Use the `debug` preset for a debug build and `sanitizers` for Linux ASan/UBSan
checks. For coverage, select the instrumented library explicitly in the ABI
tests:

```console
cmake --preset coverage
cmake --build --preset coverage
ctest --preset coverage
uvx nox -s integration_tests -- --native-library="$PWD/build/coverage/src/libibm-qdmi-device.so"
uvx nox -s tests-3.14 -- --cov --cov-report=xml:coverage.xml
```

Coverage stays offline. The C ABI tests load the selected instrumented library
through `ctypes` and contribute to C++ coverage. Python package coverage is
collected separately.

## Python checks

```console
uvx nox -s tests-3.14 -- test/python/test_qiskit_backend.py
uvx nox -s tests minimums
```

The regular test suite exercises official Runtime fake metadata and ideal MQT
Core simulation through the native device. It needs no IBM credentials. To
expose a local service to C or C++ clients:

```console
uv run --extra mock python -m ibm.qdmi.mock --backend-name fake_manila --port 0
```

The service prints synthetic QDMI session parameters. Use them before session
initialization and never supply real credentials. Stop it with Ctrl+C; its
in-memory jobs disappear.

Nox tests Python 3.11 through 3.15. The `minimums` sessions resolve minimum
direct dependencies and restore `uv.lock` afterward.

Pytest selection and registered markers live in `pyproject.toml`:

| Selection              | Purpose                           |
| ---------------------- | --------------------------------- |
| `-m integration -n 0`  | Native ABI and loopback transport |
| `-m "not integration"` | Package and framework tests       |

The `live` and `quantum` markers require their opt-in flags even when selected.

### Quantum System simulator checks

The simulator CI job installs the Linux wheel from CI and starts pinned
[Simulated Quantum Resource](https://github.com/qrmi-community/simulated_quantum_resource)
and Moto 5.2.3 on loopback. It validates IAM, metadata, a batch of circuits,
shot/register ordering, and retrieval from a fresh session through S3. Synthetic
credentials are confined to the fixture and the local bucket. The simulator uses
noiseless execution; backend metadata remains real fake-provider metadata. A
failing simulator job fails the `🚦 Check` gate.

To reproduce, check out simulator revision
`0d547e7d329b8bd3315392e9117f116dc1661ddd` under `build/qsa-sim`. Install its
requirements and `moto[server]==5.2.3` in a separate Python 3.12 environment.
Start Moto on `127.0.0.1:9000` and create bucket `qdmi-e2e` using access key
`synthetic-access`, secret key `synthetic-secret`, and region `us-east-1`. Start
`python -m qsa_sim.app ../../test/fixtures/simulator.yaml` from the simulator
checkout. Run the native ABI and framework tests in separate processes.

```console
uvx nox -s integration_tests -- -m 'simulator and integration' --simulator-url http://127.0.0.1:8290
uvx nox -s tests-3.14 -- -m 'simulator and not integration' -n 0 --simulator-url http://127.0.0.1:8290
```

Stop both services afterward. An explicitly selected unavailable service fails;
ordinary test runs skip simulator checks. Use `--simulator-s3-url` to change the
loopback storage endpoint. Existing fixtures still cover cloud behavior and
deterministic failures. These tests neither contact IBM nor submit QPU jobs.

### Source distribution checks

Build a wheel from the source distribution:

```console
uv run --only-group build python -m build --outdir build/dist
```

Install it in a fresh environment with
`uv pip install --python <environment-python> <wheel-path>`, install the test
dependency group, and run the integration and package selections separately. The
package version comes from `project()` in `CMakeLists.txt`.

CI builds and tests wheels with Python 3.11–3.15 through cibuildwheel, excluding
free-threaded interpreters. Wheel tests use the Qiskit and PennyLane adapters;
the Nox `tests` and `minimums` sessions also exercise the optional Executor SDK.
Windows builds and tests run on x86_64 with MSVC in Release and Debug
configurations.

## Live IBM metadata

Live metadata checks query `ibm_berlin` and `ibm_aachen` without submitting jobs
or consuming
[QPU time](https://quantum.cloud.ibm.com/docs/en/guides/estimate-job-run-time).
CI runs these checks for non-fork PRs, merge queues, and `main`. To run them
manually:

```console
gh workflow run live-tests.yml --ref main -f suite=metadata
```

Supply `IBM_QUANTUM_API_KEY` and `IBM_QUANTUM_INSTANCE_CRN` securely for local
checks. CI uses the `ibm-quantum` environment and confines credentials to live
test steps.

For a local metadata check, supply those variables securely and run:

```console
uvx nox -s live-metadata -- both
```

The session removes credentials from the wheel build environment. To check an
already installed wheel with the `test-metadata` dependency group:

```console
python -m pytest test/python/test_live_metadata.py --run-live --ibm-backend both -n 0 --tb=line --show-capture=no
```

Checks cover session initialization, physical indices, operations, calibration,
status, and queue queries. Optional metadata may be unsupported. Reports use
fixed diagnostic categories and QDMI status codes. Do not enable HTTP debugging
or retain raw responses, account details, topology, or calibration snapshots.
Reproduce compatibility failures with synthetic fixtures before fixing them.

## Gated quantum execution

Hardware checks require an explicit, authorized dispatch on merged `main`:

```console
gh workflow run live-tests.yml --ref main -f suite=quantum
```

The `ibm-quantum` environment allows `main`, `refs/pull/*/merge`, and
`gh-readonly-queue/main/*`. Keep its protection rules enabled. Each request runs
native CTest, then builds and installs a candidate wheel. Its offline package
and ABI tests must pass before hardware validation uses that same installation.
Secrets are available only during the final test step.

Workflow and individual-job reruns reject hardware execution. Request a fresh
dispatch after authorizing another budget.

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

Install Doxygen 1.15 or newer on `PATH`, then run:

```console
uvx nox -s docs
uvx nox -s docs -- -b linkcheck
```

The session generates the native reference with Doxygen and builds Sphinx pages
in `docs/_build/html/`. The native reference lives under `cpp/`; Python API
pages come from AutoAPI. Warnings fail the build. Edit public header comments
and Python docstrings for API references.

## Automation

CI runs C++ and Python tests, minimum-dependency tests, installation checks,
lint, coverage, and package builds offline. Authenticated metadata checks run
separately; hardware execution requires an explicit request.

Read the Docs publishes documentation previews and the documentation from
`main`. Release workflows attest and publish distributions to PyPI through
trusted publishing after a GitHub release. Manual CD runs only build artifacts.
