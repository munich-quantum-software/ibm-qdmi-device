# Development and testing

Run the [examples](examples.md) and their offline checks with
`uvx nox -s examples`. This session installs the optional example dependencies
and checks both local simulation and the loopback IBM service. The example group
includes CMake and Ninja for its installed-package consumer.

The documentation session generates the Python API from `python/ibm/` and the
native API with Doxygen. Edit declarations and docstrings to update those
references; generated pages stay in the documentation build directory.

## Environment

Use uv for dependency management and Nox for automation. Install development
dependencies without building the project:

```console
uv sync --locked --only-group dev
```

Use separate directories under `build/` for native, wheel, documentation, and
installed-package builds. Do not run two Nox package builds concurrently in the
same checkout. Ordinary tests are offline with respect to quantum backends;
dependency installation may download packages. Live metadata and quantum checks
require separate opt-ins described below.

Test and documentation sessions let `uv run` sync their dependency groups and
build the package. Scikit-build-core manages isolated build dependencies.

## Native checks

```console
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native --config Release
ctest --test-dir build/native -C Release --output-on-failure
```

Use `Debug` in both configuration and build commands for a debug build.
`test/unit/` groups GoogleTest cases by native component. The shared `HttpStub`
scripts requests and advances time without sockets or delays. Device fixtures
exercise the public C API through the same internal object target as the shared
library. `test/integration/` checks exported C and C++ interfaces, installation,
and real HTTP transport against an ephemeral loopback server.

```console
ctest --test-dir build/native/test/unit -C Release --output-on-failure
uvx nox -s native_tests
```

Run native ABI integration and Python framework tests in separate processes.
Each ABI test owns initialization and finalization; MQT Core retains its driver
library across framework tests. The `native_tests` Nox session selects the
`integration` marker in a separate process. Ordinary tests exclude that marker;
wheel tests also exclude repository tooling marked `ci`. The native integration
suite retains transport, authentication, concurrency, job lifecycle, and
result-cache regressions.

Test installation, relocation, and an installed-package consumer:

```console
cmake -P test/install.cmake
```

Enable Linux sanitizer checks in a separate build with
`-DIBM_QDMI_SANITIZERS="address;undefined" -DCMAKE_BUILD_TYPE=Debug`. Enable
native coverage with `-DIBM_QDMI_ENABLE_COVERAGE=ON`.

Coverage uses synthetic data only. QPU time is expensive: never submit hardware
jobs to increase coverage. The coverage workflow receives no IBM credentials and
never enables live or quantum tests. Hardware validation remains separately
budgeted and explicitly authorized.

To include loopback transport in a Linux native coverage build:

```console
cmake -S . -B build/coverage -DCMAKE_BUILD_TYPE=Debug -DIBM_QDMI_ENABLE_COVERAGE=ON
cmake --build build/coverage --config Debug
ctest --test-dir build/coverage -C Debug --output-on-failure
uvx nox -s native_tests -- --native-library="$PWD/build/coverage/src/libibm-qdmi-device.so"
uvx nox -s tests-3.14 -- --cov=ibm.qdmi --cov-report=xml:build/python-coverage/coverage.xml
```

The explicit library path selects the instrumented build for ABI integration.
Ordinary integration tests load the installed wheel. Python coverage measures
Python code separately; it cannot measure native calls inside an uninstrumented
wheel. CLI tests run in process for coverage and retain subprocess smoke checks.

## Python checks

The Python package derives its version from the `project()` declaration in
`CMakeLists.txt`. Update that version for both native and Python releases.

```console
uvx nox -s tests-3.14 -- test/python/test_init.py
uvx nox -s tests minimums
```

Nox tests Python 3.11 through 3.14. The `tests` and `minimums` sessions use the
default selection in `[tool.pytest]`; CI also runs `native_tests`. Registered
markers, discovery paths, strict validation, and duration reporting live in
`pyproject.toml`. Select offline ABI tests with `pytest -m integration -n 0`,
repository tooling with `pytest -m ci`, or package tests with
`pytest -m "not integration and not ci"`. The `live` and `quantum` markers still
require their explicit opt-in flags; selecting a marker never grants access.
Python tests follow module boundaries: initialization, CLI, capabilities,
serializers, Qiskit backend, sampler, estimator, and PennyLane. The minimums
sessions resolve minimum direct dependencies and restore `uv.lock` afterward.
Tests inspect installed package metadata, headers, CMake exports, and
shared-library loading. Backend discovery checks open all three installed
catalogue entries through MQT Core after copying the native artifacts to a fresh
directory. Backend integration tests run the installed C ABI against an
ephemeral loopback HTTP server. They verify authentication headers, error
recovery, session isolation, and property queries without contacting IBM. The
synthetic fixture in `test/fixtures/` models IBM API version `2026-04-15`; no
recorded account data is used.

Qiskit tests use the released MQT Core driver and installed native library. A
separate local process hosts the synthetic server because native session
creation can hold Python's GIL. The fixture simulates submitted OpenQASM with
Qiskit's basic simulator. It checks layouts, registers, batches, cancellation,
retrieval, sampler broadcasting, and estimator precision without IBM access:

```console
uvx nox -s tests-3.14 -- test/python/test_qiskit_backend.py
```

Build an sdist and a wheel from that sdist:

```console
uv run --only-group build python -m build --outdir build/dist
```

Install the resulting wheel into a fresh environment with
`uv pip install --python <environment-python> <wheel-path>`, install the test
dependency group, and run `pytest -m integration -n 0`, then
`pytest -m "not integration and not ci"`, using that interpreter. CI also builds
and tests platform wheels with cibuildwheel.

The Linux wheel containers install OpenSSL development files before building.
macOS wheels use Apple's native TLS backend and disable optional curl libraries
from Homebrew so that their deployment requirements do not raise the wheel's
minimum supported macOS version.

## Live IBM metadata

Live validation is separate from ordinary CI and the required-check aggregate.
It checks the installed wheel's C ABI against `ibm_berlin` (120 qubits) and
`ibm_aachen` (156 qubits). It submits no quantum jobs. A successful offline run
does not establish live compatibility. Metadata validation succeeded on merged
`main` on 17 September 2026; quantum execution remains unverified on hardware.

After human merge, open **Actions → Live IBM metadata → Run workflow**. Select
the `main` branch and `both` (the default), `ibm_berlin`, or `ibm_aachen`. The
equivalent command is:

```console
gh workflow run live-metadata.yml --ref main -f backend=both
```

The workflow checks out the dispatch commit and permits only `refs/heads/main`.
The `ibm-quantum` environment permits `main` and opted-in PR runs described
below. Its `IBM_QUANTUM_API_KEY` and `IBM_QUANTUM_INSTANCE_CRN` secrets are
available only to the live step, after build and installation. The library
derives the region from the CRN; this workflow has no endpoint override. Runs
are serialized and have a 15-minute timeout, with no schedules or automatic
retries.

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
fix needs a synthetic regression test and a follow-up PR.

## Gated quantum execution

Pushes to `main` run all offline Actions checks before hardware validation.
Pre-commit.ci and Read the Docs guard pull-request merges; hardware execution
does not wait for their results on the merged commit. Manual
**Actions → CI → Run workflow** dispatches from `main` use the same gates:

```console
gh workflow run ci.yml --ref main
```

Maintainers can add `live-qpu-tests` to a same-repository PR to enable the same
hardware checks before merging. Adding this label reuses successful offline
checks and the retained candidate wheel for the exact PR merge commit. It does
not rebuild or rerun offline tests. Other label additions schedule no jobs and
do not replace `🚦 Check`; label removal starts no workflow. Label events do not
cancel an existing CI run.

If offline CI is still running, let it finish and rerun the label workflow. If
the artifact expired or the merge commit changed, run fresh offline CI first.
The candidate expires after seven days. Reuse requires successful offline and
candidate jobs from this PR's CI run; partial reruns use the candidate job's own
attempt. Hardware success from that source run is reused too. Pending or failed
source hardware must be handled in that run; the label workflow never
automatically retries it.

Reapplying `live-qpu-tests` or manually rerunning its workflow is a new paid
attempt when the original offline run skipped hardware. Do so only within an
authorized budget; results from separate label runs are not reused.

While the label remains, new commits and reopened PRs run fresh offline checks
before hardware execution. Each eligible run uses the budget below; remove the
label to stop future hardware runs. Removing it does not cancel jobs already
submitted to IBM. Fork PRs, unlabeled PRs, merge queues, and dispatches from
other branches run offline only. Do not use `pull_request_target` to expose
secrets to fork code.

Before enabling PR hardware checks, add `refs/pull/*/merge` as a deployment
branch rule for the `ibm-quantum` environment, retaining `main`. GitHub
documents this pattern in its
[deployment branch rules](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments#deployment-branches-and-tags).
Create the `live-qpu-tests` repository label. Apply it only after reviewing the
PR code and authorizing IBM access on Berlin and Aachen within the budget below.
The label opts subsequent PR updates into that budget too. Environment
protection rules still apply; a blocked hardware job cannot pass `🚦 Check`.

On `main`, change detection cannot skip a prerequisite. PRs retain their normal
change detection. The final `🚦 Check` requires the offline aggregate and, for
eligible main or labeled PR runs, successful hardware validation. A failed,
cancelled, or unexpectedly skipped prerequisite prevents hardware execution. The
independent metadata workflow remains available without quantum jobs.

The pipeline builds a Linux wheel from its sdist, tests that installed wheel
without secrets, and passes the exact wheel to the hardware job. Artifact names
include the merge commit and build attempt; label runs download only the
validated artifact ID from its source CI run. Dependencies come from `uv.lock`.
Only the final test step receives the existing `ibm-quantum` environment
secrets. The native library derives the API region from the instance CRN; the
workflow supplies no endpoint override.

Berlin and Aachen run sequentially through the public `IBMBackend`. Each backend
receives exactly one job with 128 shots and the native 60-second QPU execution
cap. The circuit contains a Bell pair and an independent X-prepared qubit. The
check requires 128 three-bit shots, matching counts and memory, at least 75%
combined `100`/`111`, and at least 10% for each outcome. A fresh session
retrieves the same job and compares its results without another submission.
Sampler and estimator checks run offline and do not add hardware jobs.

Each backend may wait up to one hour, including time in IBM's queue. This wait
does not increase the 60-second QPU execution cap. The original public job must
also report completion before result collection, so it cannot start an unlimited
second wait. Failures and timeouts trigger a cancellation attempt before handles
are released; cancellation can race with completion. Freeing a handle alone does
not cancel a remote job. The workflow job timeout is 130 minutes, allowing both
sequential waits plus installation and cleanup. Runs are serialized without
automatic cancellation or retries. Rerunning the workflow is another paid run;
do so only within an authorized budget. Do not make development-time hardware
submissions.

The `quantum` marker requires `--run-quantum`; `--run-live` enables metadata
only. Default pytest, Nox, wheel, and documentation builds cannot activate
hardware access, even when credentials exist. Live diagnostics contain backend
names, outcomes, and fixed failure categories. Job IDs exist only in process
memory for retrieval and cleanup. Hardware checks create no result artifacts and
retain no raw responses, topology, calibration snapshots, credentials, or CRNs.
A runner termination can prevent cleanup; the per-job execution cap still
applies.

Quantum execution remains **unverified on hardware** until the first eligible
run succeeds. Reproduce any live compatibility failure with a synthetic
regression before making a follow-up fix.

## Lint

```console
uvx nox -s lint
```

This runs the complete prek hook set, including pyproject.toml formatting,
spelling, license headers, metadata, lockfile, workflow security, Ruff, and ty.
Hooks can change files; inspect the changes and rerun until clean. To check new
untracked files before staging, use `uvx prek run --files <paths>`.

For C++ files, reproduce `.github/workflows/cpp-linter.yml` with its Clang
version and a Ninja compilation database. Check every line of each changed file
with clang-format and clang-tidy, including native tests. Do not restrict checks
to changed lines.

## Documentation

Install Doxygen 1.16.1 on `PATH`, then run:

```console
uvx nox --non-interactive -s docs
uvx nox --non-interactive -s docs -- -b linkcheck
```

The session builds the package in `build/docs/`, generates Doxygen XML and HTML,
and embeds declarations in Sphinx with Breathe. Warnings fail the build. HTML
output is in `docs/_build/html/`; existing `cpp/` links remain available. The
example notebook runs on the local simulator without IBM credentials. Successful
execution is cached; cell errors fail the build. To execute every cell again,
pass `-- -D nb_execution_mode=force` to the docs session.

## Automation

CI builds and tests without backend credentials, then permits the bounded
hardware checks described above on merged `main` and labeled internal PRs. Its
offline aggregate includes change detection, native tests on Linux, macOS, and
Windows (MSVC and ClangCL), installation tests, sanitizers, coverage,
clang-tidy, Python type and source-distribution checks, Python/Qiskit tests,
sdist and wheel builds, and the installed Linux candidate. PR checks may skip
jobs deselected by change detection; failures, cancellations, and unexpected
skips block the aggregate. Pushes to `main` run every Actions prerequisite.
Pre-commit.ci runs the hook checks on pull requests; its configuration skips
`ty`, which the Python Actions job runs together with `check-sdist`. The local
lint and documentation Nox sessions run the same checks during development.

The `main` ruleset requires `🚦 Check` from GitHub Actions,
`pre-commit.ci - pr`, and the Read the Docs preview check. These checks guard
pull-request merges. Hardware execution uses the Actions prerequisites on the
tested commit, including the PR merge commit for labeled internal PRs.

Read the Docs builds public pull-request previews and the `latest` documentation
from `main` using `.readthedocs.yaml`. It installs Doxygen 1.16.1 and OpenSSL
development headers and runs the strict documentation Nox session without
backend credentials. The published documentation includes the native API under
`cpp/`.

Release workflows attest and publish the `ibm-qdmi` distributions through PyPI
trusted publishing after a GitHub release is published. The `pypi` environment
permits only tags matching `v*`; publishing uses short-lived identity tokens.
Manual CD runs build artifacts. Coverage jobs upload native and Python reports
to Codecov using OpenID Connect.
