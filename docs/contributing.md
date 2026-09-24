# Contributing

Contributions are welcome, from bug reports and documentation improvements to
features, tests, and tooling. We use GitHub to
[track issues](https://github.com/munich-quantum-software/ibm-qdmi-device/issues)
and review
[pull requests](https://github.com/munich-quantum-software/ibm-qdmi-device/pulls).

## Types of Contributions

- **Report bugs:** Search existing issues, then use the bug-report form. Include
  a minimal reproducer, expected and actual behavior, and environment details.
  Follow the [support guide](support.md).
- **Propose features:** Use the feature-request form to explain the problem,
  proposed solution, and alternatives. Discuss substantial changes before
  implementation.
- **Fix bugs or implement features:** Coordinate in the issue and open a draft
  pull request early for feedback.
- **Improve documentation:** Clarify guides, examples, or API documentation.
- **Improve testing, performance, or tooling:** Add meaningful tests, measure
  performance changes, and keep packaging and CI fixes focused.
- **Help other users:** Reproduce reported problems and answer questions in the
  issue tracker.

## Development Setup

Fork the repository if you do not have write access. Clone your fork or the
upstream repository, then create a branch for your change:

```console
git switch -c name-of-your-change
uv sync --locked --only-group dev
uv tool install prek
prek install
```

See [development and testing](development.md) for native builds, Python tests,
documentation builds, and lint commands. Run the focused checks for your change
and `uvx nox -s lint` before submitting it.

## Guidelines

Keep changes focused and update documentation at its existing source of truth.

Use C++20, LLVM-based formatting, and `///` documentation at API declarations.
Use Google-style Python docstrings, Ruff, and ty. Preserve copyright and license
notices on copied files.

Keep credentials and private backend details out of source, logs, and issue
reports. Live backend access requires separate authorization; automated tests
use synthetic responses and loopback HTTP.

### Commits and Changelog

Write focused, signed commits with a gitmoji and an imperative subject. Record
AI assistance in an `Assisted-by` trailer. Document user-visible changes in the
[changelog](CHANGELOG.md). Add actual PR and author references when available.

Group changelog entries under `Added`, `Changed`, `Fixed`, or `Removed` in
`Unreleased`, newest first. Start each entry with a gitmoji and include its PR
and every contributing author, with link definitions at the bottom. Fold related
unreleased changes into one entry.

## Pull Request Workflow

1. Open a draft pull request early for feedback. Use a clear title and the PR
   template, explain the resulting behavior, and reference related issues.
2. Keep each PR focused on one change. Add tests for changed behavior and report
   the checks you ran, including failures and limitations.
3. When ready, mark the PR ready for review and request a maintainer review.
   Required checks must pass before merging.
4. Address feedback on the same branch. Do not close and reopen a new PR to
   replace one with requested changes.
5. Reply to review comments and request another review after making changes.
   Leave comment resolution to the reviewer.
6. Keep commits separate; maintainers can squash on merge. Avoid rebasing or
   force-pushing during review.

For AI-assisted contributions, follow the {download}`agent guide <../AGENTS.md>`
and disclose the assistance in the PR template. Human reviewers retain
acceptance and responsibility for changes.

## Security and Questions

Follow the [security policy](security.md) for vulnerabilities. For other
questions, use the issue tracker and follow the [support guide](support.md).
