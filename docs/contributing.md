# Contributing

Keep changes focused and follow {download}`AGENTS.md <../AGENTS.md>` when using
an agent. Use [development and testing](development.md) for commands and report
the checks you ran. Add tests for changed behavior and update the documentation
at its existing source of truth.

Use C++20, LLVM-based formatting, and `///` documentation at API declarations.
Use Google-style Python docstrings, Ruff, and ty. Preserve copyright and license
notices on copied files.

Keep credentials and private backend details out of source, logs, and issue
reports. Live backend access requires separate authorization; automated tests
use synthetic responses and loopback HTTP.

Write focused, signed commits with a gitmoji and an imperative subject. Record
AI assistance in an `Assisted-by` trailer. Human reviewers retain acceptance and
responsibility for changes. Follow the pull request template and document
user-visible changes in the [changelog](CHANGELOG.md). Add actual PR and author
references when available.

Group changelog entries under `Added`, `Changed`, `Fixed`, or `Removed` in
`Unreleased`, newest first. Start each entry with a gitmoji and include its PR
and every contributing author, with link definitions at the bottom. Fold related
unreleased changes into one entry.
