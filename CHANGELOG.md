<!-- Entries in each category are sorted by merge time, with the latest PRs appearing first. -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on a mixture of [Keep a Changelog] and [Common Changelog].
This project adheres to [Semantic Versioning], with the exception that minor
releases may include breaking changes.

## [Unreleased]

### Fixed

- 🐛 Allow one hour per backend for hardware validation, including queue time,
  without increasing the QPU execution budget. ([#32]) ([**@marcelwa**])

- 🐛 Find generated native coverage reports when uploading to Codecov. ([#27])
  ([**@marcelwa**])

- 🐛 Accept IBM measurement calibration repeated in per-qubit readout and gate
  metadata so public backends can initialize for quantum execution. ([#25])
  ([**@marcelwa**])

- 🧪 Allow 60 seconds for native test discovery on slower runners. ([#13])
  ([**@marcelwa**])

- 🐛 Avoid hostname resolution when starting offline test servers and report
  slow wheel tests. ([#16]) ([**@marcelwa**])

### Added

- 👷 Allow maintainers to opt same-repository PRs into bounded IBM hardware
  checks with the `live-qpu-tests` label. ([#31]) ([**@marcelwa**])

- 📚 Add task-based navigation, Python package and dependency guides, API links,
  and MQSC branding. Align community support, security reporting, and
  contribution guidance. ([#26]) ([**@marcelwa**])

- 📚 Add generated Python API references and runnable native QDMI, Qiskit, MQT
  Bench, H₂, and PennyLane QAOA examples with offline validation. ([#24])
  ([**@marcelwa**])

- ✨ Add PennyLane devices for the IBM catalogue with finite-shot measurements,
  gradients, shot vectors, and validated native OpenQASM execution. Synthesize
  CNOT for CZ/ECR bases and fold native RZZ angles into the hardware range. Use
  MQT Core 4 for the shared Python adapters and Qiskit duration conversion.
  ([#22]) ([**@marcelwa**])

- ✨ Add native environment defaults, explicit API-key files, per-session HTTP
  timeouts, and explicit calibration and pulse capability reporting. ([#20])
  ([**@marcelwa**])

- ✨ Configure per-job IBM Runtime dynamical decoupling through a validated JSON
  parameter, with disabled defaults and unchanged execution limits. ([#19])
  ([**@marcelwa**])

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

- 🔧 Let uv manage Nox test and documentation environments. Declare the native
  example's build tools in its dependency group. ([#30]) ([**@marcelwa**])

- ♻️ Index native calibrations by directed site tuple and share gate and readout
  fidelity validation. Preserve tuple order and measurement precedence. ([#29])
  ([**@marcelwa**])

- ♻️ Share connection defaults between the Qiskit and PennyLane adapters while
  preserving explicit overrides and catalogue backend selection. ([#28])
  ([**@marcelwa**])

- ⚡ Allow independent session and job requests to progress concurrently while
  preserving shared IAM refresh, per-job result caches, and wait deadlines.
  ([#23]) ([**@marcelwa**])

- 👷 Use GitHub's self-repository references for reusable CI workflows. ([#8])
  ([**@marcelwa**])

- 👷 Delegate hook checks to pre-commit.ci and documentation builds to Read the
  Docs before merging. Retain Actions type checks, source-distribution checks,
  and offline hardware prerequisites. Use the same Doxygen version for hosted
  native API builds. Configure release-tag publishing. ([#18]) ([**@marcelwa**])

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
[#18]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/18
[#19]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/19
[#1]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/1
[#2]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/2
[#20]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/20
[#22]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/22
[#23]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/23
[#24]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/24
[#25]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/25
[#26]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/26
[#27]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/27
[#29]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/29
[#30]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/30
[#31]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/31
[#32]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/32
[#3]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/3
[#5]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/5
[#8]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/8
[#28]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/28
[**@marcelwa**]: https://github.com/marcelwa
