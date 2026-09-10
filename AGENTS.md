# IBM QDMI Device Agent Guide

Follow this guide and the nearest scoped `AGENTS.md`. Use
[`docs/development.md`](docs/development.md) for build, test, and documentation
commands. Keep this file focused on repository-specific guardrails.

## Repository Layout

- `src/` contains the native device, HTTP transport, IAM authentication, and
  metadata parsing. `include/` contains public IBM constants. Generated QDMI
  headers stay in the build tree.
- `python/ibm/qdmi/` contains the Python package and version metadata.
- `test/` contains native packaging checks and pytest tests.
- `cmake/`, `CMakeLists.txt`, and `pyproject.toml` define builds. Keep generated
  output in `build/` and `docs/_build/`, never in commits.
- The project uses Apache-2.0 WITH LLVM-exception. SPANK is out of scope.

## Working Principles

- Inspect the worktree before editing and preserve unrelated user changes.
- Prefer the smallest change that fully solves the problem. Reuse existing code
  and C++20 facilities before adding abstractions or settings.
- Follow documented policy. Neighboring code does not override instructions.
- Write comments, documentation, tests, diagnostics, and public text for the
  final design. Remove review chronology and abandoned approaches.
- Use short sentences, active voice, and one established term per concept.
  Preserve the capitalization of IBM, QDMI, OpenQASM, CMake, and Python.
- Add tests for changed behavior or concrete regressions. Keep tests in `test/`
  and start with focused checks. Do not add artificial passing device tests.
- Keep cleanup separate from behavior changes unless correctness requires both.
  Retain only narrow, justified suppressions.
- Keep documentation at its existing source of truth and link to it.
- Keep project documentation and configuration self-contained. Do not name or
  link other device implementations. Preserve required copyright and license
  notices in copied material.
- Group related changes in a concise changelog entry. Once a PR exists, include
  its reference and every contributing author as `([#123]) ([**@username**])`
  and define their links at the bottom of `CHANGELOG.md`. Do not invent PRs.
- Never hand-edit generated files. Change their source configuration instead.
  Change externally managed templates in their owning repository.
- Preserve copyright and license notices on copied material.

## C++ and QDMI Contracts

The project targets C++20. Use `///` for documentation comments and keep API
documentation at the declaration. Explain only details that names and signatures
do not convey. Use C++ casts, not C-style casts.

Preserve the QDMI C ABI and the `IBM_` symbol prefix. No C++ exception may cross
the C boundary. Honor size queries, handle validation, status codes, and null
checks. The current milestone supports backend queries only. Job execution and
discovery require their own implementation milestones.

## Build and Validation

Run offline tests by default. Separate native, wheel, documentation, and
installed-consumer build directories under `build/`. Do not run package builds
concurrently in the same build directory. For dependency-only setup, use
`uv sync --locked --only-group dev`.

- Run `uvx nox -s lint` after each completed batch of changes. Inspect formatter
  changes, keep only relevant changes, and rerun the check.
- For C++ changes, reproduce `.github/workflows/cpp-linter.yml` against every
  line of each changed file. Report existing diagnostics rather than hiding them
  with broad suppressions.
- Run focused Python tests with `uvx nox -s tests-3.14 -- <test path>`. Use
  `uvx nox -s tests minimums` for the supported Python matrix.
- Use Google-style Python docstrings. Preserve the `ibm.qdmi` namespace. Fix
  Ruff and ty findings where possible.
- Build Sphinx and Doxygen through the dedicated Nox documentation session.

### Live Access

Never print, store, or commit credentials, tokens, account identifiers, or
private backend details. Live IBM access requires explicit authorization for the
service, backend, and spending scope. The opt-in metadata checks submit no jobs.
Run the manual workflow only from merged `main`, using the `ibm-quantum`
environment restricted to that branch. Never dispatch from a PR or merge to
enable a live run without human approval. Keep credentials confined to the live
test step, after wheel installation. Follow `docs/development.md` for commands.

Keep live tests marked `live` and skipped before credential access unless
`--run-live` is explicit. Preserve sequential execution and fixed diagnostic
categories. Never retain raw responses, topology, or calibration snapshots in
logs or artifacts. Reproduce compatibility failures with synthetic fixtures
before fixing them. Quantum execution requires a separate milestone and budget.

## Git and GitHub

- Keep commits focused. Start subjects with a gitmoji and an imperative verb;
  target 50 characters and never exceed 72. Use the body for constraints and
  non-obvious decisions.
- Sign commits and annotated tags with the configured key. Verify commits with
  `git verify-commit HEAD` before pushing; never bypass a signing failure.
- Preserve human attribution. Use `Assisted-by` for AI assistance, never an AI
  `Co-authored-by` trailer.
- Push, open or merge PRs, and post public text only within explicit human
  authorization. Request new authority before expanding that scope.
- Start every agent-authored or agent-edited public text body with
  `🤖 *AI text below* 🤖`; titles are exempt. State how AI assisted the work and
  leave acceptance and responsibility with the human reviewer.
- Use the applicable PR template, labels, and requested assignee. Do not invent
  checklist items or attest to human review on the user's behalf.
- Do not work on `good first issue` tasks or post repetitive reviews.
- A push does not authorize CI monitoring. Verify the remote head, report the
  available status, and stop unless monitoring was requested.

## Handoff

Inspect the final diff and worktree. Report what changed and each check run,
including failures or checks that could not run. Distinguish local validation,
live validation, and hosted CI for the final head. Never describe queued checks
or checks from an older commit as passing validation of the new head.
