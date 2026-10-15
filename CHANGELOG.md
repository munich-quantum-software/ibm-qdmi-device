<!-- Entries in each category are sorted by merge time, with the latest PRs appearing first. -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on a mixture of [Keep a Changelog] and [Common Changelog].
This project adheres to [Semantic Versioning], with the exception that minor
releases may include breaking changes.

## [Unreleased]

### Added

- ✨ Run official Runtime fake backends through native QDMI without IBM Cloud
  access using `IBMBackend(backend_name="fake_manila")` and `ibm-qdmi[mock]`.
- ✨ Support binary QPY 17 submission and retrieval. ([#71]) ([**@marcelwa**],
  [**@burgholzer**])
- ✨ Support measurement-based `if_else` conditions through QPY and OpenQASM 3.
  ([#71]) ([**@marcelwa**], [**@burgholzer**])

### Changed

- ♻️ Prefer Core's QPY serializer for Qiskit circuits. ([#71]) ([**@marcelwa**],
  [**@burgholzer**])
- ♻️ Limit native OpenQASM parsing to classical result layout extraction.
  ([#71]) ([**@burgholzer**])
- 🧪 Use MQT Core's decision-diagram simulator for offline execution tests.
  ([#71]) ([**@burgholzer**])
- ♻️ Simplify native dependency setup with CPR 1.15.1 and GoogleTest 1.18.0.
  ([#92]) ([**@burgholzer**])
- 📝 Consolidate usage and development guidance and publish the native API
  directly with Doxygen. ([#92]) ([**@burgholzer**])
- 🔧 Simplify package license metadata and configuration. ([#92])
  ([**@burgholzer**])
- 👷 Run hardware checks independently on explicit requests after fresh offline
  validation. ([#92]) ([**@burgholzer**])
- 👷 Run selected Python sessions for draft PRs and the full range when ready
  for review. ([#92]) ([**@burgholzer**])
- 👷 Separate native coverage from Python test coverage uploads. ([#92])
  ([**@burgholzer**])
- 👷 Use Clang 23 to lint whole changed files on PRs and all files on `main`.
  ([#92]) ([**@burgholzer**])
- 👷 Use shared native CI workflows with MSVC on Windows and one check
  aggregate. ([#92]) ([**@burgholzer**])
- 👷 Check IBM metadata automatically in trusted CI. ([#92])
  ([**@burgholzer**])
- ♻️ Remove the offloader, worker commands, and application examples; refer to
  MQT Core for shared QDMI and Slurm workflows. ([#92]) ([**@burgholzer**])
- ⬆️ Update the Python certificate bundle to 2026.10.19. ([#82])
  ([**@marcelwa**])

### Fixed

- 🐛 Build Windows Debug binaries with embedded debug information. ([#92])
  ([**@burgholzer**])
- 🐛 Use the PennyLane adapter without requiring Qiskit. ([#92])
  ([**@burgholzer**])
- 🐛 Select OpenSSL 3 when building Linux wheels. ([#92])
  ([**@burgholzer**])
- 🐛 Create the documentation output directory before running Doxygen. ([#92])
  ([**@burgholzer**])
- 🐛 Reserve static TLS space for PySCF in chemistry tests. ([#80])
  ([**@marcelwa**])

## [1.0.0] - 2026-10-14

### Added

- ✨ Add a QDMI Slurm guide and an offline cluster smoke test. ([#62])
  ([**@flowerthrower**], [**@burgholzer**])

### Changed

- ⬆️ Update MQT Core to 4.1.1 with installed manifest discovery. ([#66])
  ([**@marcelwa**], [**@denialhaag**])
- ⬆️ Update QDMI to 1.4.0 with native multi-program jobs, indexed results, and
  export control. ([#66]) ([**@marcelwa**], [**@denialhaag**])
- 👷 Enable testing on Python 3.15 ([#63]) ([**@denialhaag**])

### Fixed

- 🐛 Select calibrated layouts for live quantum checks. ([#66])
  ([**@marcelwa**])
- 🐛 Enforce Sampler execution limits and consistent QDMI credential precedence.
  ([#66]) ([**@burgholzer**])

## [0.1.1] - 2026-10-06

### Changed

- 📝 Document installation from PyPI, keep source builds as an alternative, and
  list the supported wheel platforms. ([#60]) ([**@marcelwa**])

### Fixed

- 🐛 Ship license texts for libcurl, cpr, nlohmann/json, and OpenSSL bundled in
  binary wheels, and declare them in the package license metadata. ([#59])
  ([**@marcelwa**])

- 🐛 Use absolute links in the README so its logo and links render on PyPI.
  ([#59]) ([**@marcelwa**])

## [0.1.0] - 2026-10-05

_This is the initial release of the IBM QDMI Device._

### Added

- 🎉 Initial release. See the [documentation] for features and usage.
  ([**@marcelwa**])

<!-- PR links -->

[#92]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/92
[#82]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/82
[#80]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/80
[#71]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/71
[#66]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/66
[#63]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/63
[#62]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/62
[#60]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/60
[#59]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/59

<!-- Version links -->

[unreleased]: https://github.com/munich-quantum-software/ibm-qdmi-device/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/munich-quantum-software/ibm-qdmi-device/releases/tag/v1.0.0
[0.1.1]: https://github.com/munich-quantum-software/ibm-qdmi-device/releases/tag/v0.1.1
[0.1.0]: https://github.com/munich-quantum-software/ibm-qdmi-device/releases/tag/v0.1.0

<!-- Contributor -->

[**@burgholzer**]: https://github.com/burgholzer
[**@denialhaag**]: https://github.com/denialhaag
[**@flowerthrower**]: https://github.com/flowerthrower
[**@marcelwa**]: https://github.com/marcelwa

<!-- General links -->

[Keep a Changelog]: https://keepachangelog.com/en/1.1.0/
[Common Changelog]: https://common-changelog.org/
[Semantic Versioning]: https://semver.org/spec/v2.0.0.html
[documentation]: https://ibm-qdmi-device.readthedocs.io/en/latest/
