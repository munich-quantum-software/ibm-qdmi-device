# Contributing

Keep changes focused and follow {download}`AGENTS.md <../AGENTS.md>` when using
an agent. Use [development and testing](development.md) for commands and report
the checks you ran. Add tests for changed behavior and update the documentation
at its existing source of truth.

Use C++20, LLVM-based formatting, and `///` documentation at API declarations.
Use Google-style Python docstrings, Ruff, and ty. Preserve copyright and license
notices on copied files.

Keep credentials and private backend details out of source, logs, and issue
reports. Backend access requires separate authorization; the scaffold needs
none.

Write focused, signed commits with a gitmoji and an imperative subject. Record
AI assistance in an `Assisted-by` trailer. Human reviewers retain acceptance and
responsibility for changes. Follow the pull request template and document
user-visible changes in the [changelog](CHANGELOG.md). Add actual PR and author
references when available.
