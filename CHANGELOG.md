<!-- Entries in each category are sorted by merge time, with the latest PRs appearing first. -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on a mixture of [Keep a Changelog] and [Common Changelog].
This project adheres to [Semantic Versioning], with the exception that minor
releases may include breaking changes.

## [Unreleased]

### Added

- ✨ Add native Quantum System API access with S3 storage beside cloud access,
  with offline simulator execution and retrieval checks.
- ✨ Add binary QPY submission and retrieval, prefer QPY in Qiskit, and support
  measurement-based conditional gates with offline examples and regression
  tests. ([#71]) ([**@marcelwa**])

- ✨ Run official Runtime fake backends through native QDMI without IBM Cloud
  access using `IBMBackend(backend_name="fake_manila")` and `ibm-qdmi[mock]`.
  ([#72]) ([**@marcelwa**])

### Fixed

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

[#71]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/71
[#80]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/80
[#72]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/72
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
