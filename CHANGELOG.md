<!-- Entries in each category are sorted by merge time, with the latest PRs appearing first. -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on a mixture of [Keep a Changelog] and [Common Changelog].
This project adheres to [Semantic Versioning], with the exception that minor
releases may include breaking changes.

## [Unreleased]

### Fixed

- 🧪 Allow 60 seconds for native test discovery on slower runners. ([#13])
  ([**@marcelwa**])

- 🐛 Avoid hostname resolution when starting offline test servers and report
  slow wheel tests. ([#16]) ([**@marcelwa**])

### Added

- 🧪 Gate bounded Berlin and Aachen quantum execution behind all offline CI
  checks, using the tested wheel, fresh-session retrieval, and redacted
  diagnostics. Confirm terminal state before collecting public job results. Keep
  hardware access explicitly opt-in and unverified until the first merged-main
  run. ([#13]) ([**@marcelwa**])

- ✨ Add the public Qiskit backend, metadata-derived targets, physical-layout
  serialization, ordered results, and shared sampler and estimator primitives.
  Expose advertised measurement/reset metadata and readout calibration. Honor
  registered defaults and the shared backend factory, with separate circuit
  serialization. ([#12]) ([**@marcelwa**])

- ✨ Install a relocatable device catalogue, exported QDMI target properties,
  package path constants, and an information CLI with installed-driver checks.
  Preserve bundled wheel dependencies during relocation checks. ([#11])
  ([**@marcelwa**])

- ✨ Implement native OpenQASM 3 jobs, bounded execution, cancellation,
  retrieval, ordered shots, and histograms with synthetic lifecycle tests and
  QDMI error codes for invalid buffers and job states. ([#10]) ([**@marcelwa**])

- 🧪 Add opt-in, metadata-only live validation for IBM Berlin and Aachen through
  the installed library, with a manual main-only workflow and offline safety
  regressions. ([#3]) ([**@marcelwa**])

- ✨ Add IBM cloud API-key authentication and native backend, site, and
  operation queries with offline integration tests. Exclude explicitly faulty
  operation tuples. ([#2]) ([**@marcelwa**])

- 🎉 Initialize the IBM QDMI Device build, packaging, documentation, and
  automation scaffold. ([#1]) ([**@marcelwa**])

### Changed

- 📦 Use MQT Core 4 for Qiskit integration and duration conversion, standardize
  exported QDMI device metadata, and check every native ABI entry point during
  source builds.

- 🛠️ Format Python project metadata consistently, install the CMake executable
  used by development sessions, and classify release notes with label-based
  categories, exclusions, and version rules. ([#17]) ([**@marcelwa**])

- 👷 Route CI checks by changed files, aggregate results in `🚦 Check`, add
  Windows ClangCL testing, build caching, and Linux mold setup, and standardize
  workflow names, project badges, native build ignores, and changelog
  formatting. ([#5]) ([**@marcelwa**])

[Keep a Changelog]: https://keepachangelog.com/en/1.1.0/
[Common Changelog]: https://common-changelog.org/
[Semantic Versioning]: https://semver.org/spec/v2.0.0.html
[Unreleased]: https://github.com/munich-quantum-software/ibm-qdmi-device
[#10]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/10
[#11]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/11
[#12]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/12
[#13]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/13
[#16]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/16
[#17]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/17
[#1]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/1
[#2]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/2
[#3]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/3
[#5]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/5
[**@marcelwa**]: https://github.com/marcelwa
