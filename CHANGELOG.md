<!-- Entries in each category are sorted by merge time, with the latest PRs appearing first. -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on a mixture of [Keep a Changelog] and [Common Changelog].
This project adheres to [Semantic Versioning], with the exception that minor
releases may include breaking changes.

## [Unreleased]

## [1.0.0] - 2026-10-14

### Added

- ✨ Add a QDMI Slurm guide and an offline cluster smoke test. ([#62])
  ([**@flowerthrower**], [**@burgholzer**])

### Fixed

- 🐛 Select calibrated layouts for live quantum checks. ([#66])
  ([**@marcelwa**])
- 🐛 Enforce Sampler execution limits and consistent QDMI credential precedence.
  ([#66]) ([**@burgholzer**])

### Changed

- ⬆️ Update MQT Core to 4.1.1 with installed manifest discovery. ([#66])
  ([**@marcelwa**], [**@denialhaag**])
- ⬆️ Update QDMI to 1.4.0 with native multi-program jobs, indexed results, and
  export control. ([#66]) ([**@marcelwa**], [**@denialhaag**])
- 👷 Enable testing on Python 3.15 ([#63]) ([**@denialhaag**])

## [0.1.1] - 2026-10-06

### Fixed

- 🐛 Ship license texts for libcurl, cpr, nlohmann/json, and OpenSSL bundled in
  binary wheels, and declare them in the package license metadata. ([#59])
  ([**@marcelwa**])

- 🐛 Use absolute links in the README so its logo and links render on PyPI.
  ([#59]) ([**@marcelwa**])

### Changed

- 📝 Document installation from PyPI, keep source builds as an alternative, and
  list the supported wheel platforms. ([#60]) ([**@marcelwa**])

## [0.1.0] - 2026-10-05

_This is the initial release of the IBM QDMI Device._

### Added

- 🎉 Initial release. See the [documentation] for features and usage.
  ([**@marcelwa**])

<!-- PR links -->

[#66]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/66
[#59]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/59
[#60]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/60
[#62]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/62
[#63]: https://github.com/munich-quantum-software/ibm-qdmi-device/pull/63

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
