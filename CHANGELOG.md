<!-- Entries in each category are sorted by merge time, with the latest PRs appearing first. -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on a mixture of [Keep a Changelog] and [Common Changelog].
This project adheres to [Semantic Versioning], with the exception that minor
releases may include breaking changes.

## [Unreleased]

### Added

- ✨ Add IBM cloud API-key authentication and native backend, site, and
  operation queries with offline integration tests. Exclude explicitly faulty
  operation tuples. Job execution remains unimplemented. ([#2])
  ([**@marcelwa**])

- 🎉 Initialize the IBM QDMI Device build, packaging, documentation, and
  automation scaffold. ([#1]) ([**@marcelwa**])

### Changed

- 👷 Route CI checks by changed files, aggregate results in `🚦 Check`, add
  Windows ClangCL testing, build caching, and Linux mold setup, and standardize
  workflow names, project badges, native build ignores, and changelog
  formatting. ([#5]) ([**@marcelwa**])

[Keep a Changelog]: https://keepachangelog.com/en/1.1.0/
[Common Changelog]: https://common-changelog.org/
[Semantic Versioning]: https://semver.org/spec/v2.0.0.html
[Unreleased]: https://github.com/munich-quantum-software/ibm-qdmi-device
[#1]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/1
[#2]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/2
[#5]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/5
[**@marcelwa**]: https://github.com/marcelwa
