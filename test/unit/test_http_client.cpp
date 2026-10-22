/*
 * Copyright (c) 2026 Munich Quantum Software Company GmbH
 * All rights reserved.
 *
 * Licensed under the Apache License v2.0 with LLVM Exceptions (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * https://llvm.org/LICENSE.txt
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 *
 * SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
 */

#include "Http.hpp"

#include <array>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <gtest/gtest.h>
#include <ibm-qdmi-device/diagnostics.h>
#include <ibm_qdmi/constants.h>
#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#ifdef _MSC_VER
#include <cstddef>
#include <memory>
#endif

#ifdef _WIN32
#include <stdlib.h> // NOLINT(modernize-deprecated-headers) -- Windows environment extensions
#endif

namespace {
class ScopedEnvVar {
public:
  ScopedEnvVar(const char* key, const char* value) : name(key) {
#ifdef _MSC_VER
    char* raw = nullptr;
    std::size_t size = 0;
    EXPECT_EQ(_dupenv_s(&raw, &size, key), 0);
    const std::unique_ptr<char, decltype(&std::free)> owned(raw, std::free);
    if (raw != nullptr) {
      previous = raw;
    }
#else
    if (const auto* old = std::getenv(key)) {
      previous = old;
    }
#endif
    assign(value);
  }
  ~ScopedEnvVar() { assign(previous ? previous->c_str() : nullptr); }
  ScopedEnvVar(const ScopedEnvVar&) = delete;
  ScopedEnvVar& operator=(const ScopedEnvVar&) = delete;

private:
  void assign(const char* value) const {
#ifdef _WIN32
    _putenv_s(name, value == nullptr ? "" : value);
#else
    if (value == nullptr) {
      unsetenv(name);
    } else {
      setenv(name, value, 1);
    }
#endif
  }
  const char* name;
  std::optional<std::string> previous;
};

class CaBundleTest : public testing::Test {
protected:
  const std::filesystem::path path =
      std::filesystem::path(testing::TempDir()) /
      ("ibm-qdmi-ca-" +
       std::to_string(
           std::chrono::steady_clock::now().time_since_epoch().count()));
  const std::string first = path.string() + "-first.pem";
  const std::string second = path.string() + "-second.pem";
  void TearDown() override {
    std::filesystem::remove(first);
    std::filesystem::remove(second);
  }
  static void write(const std::string& filename) {
    std::ofstream output{filename};
    output << "synthetic bundle";
    ASSERT_TRUE(output.good());
  }
};

template <class Function> void expectFailure(Function&& function, int status) {
  try {
    std::forward<Function>(function)();
    FAIL() << "Expected a QDMI failure";
  } catch (const ibm::Failure& error) {
    EXPECT_EQ(error.status, status);
  }
}
} // namespace

TEST(Http, MapsFailuresWithoutServerText) {
  for (const auto& [status, expected, diagnostic] :
       std::vector<std::tuple<std::int32_t, int, IBM_QDMI_Diagnostic>>{
           {401, QDMI_ERROR_PERMISSIONDENIED,
            IBM_QDMI_DIAGNOSTIC_AUTHENTICATION},
           {403, QDMI_ERROR_PERMISSIONDENIED,
            IBM_QDMI_DIAGNOSTIC_AUTHENTICATION},
           {404, QDMI_ERROR_NOTFOUND, IBM_QDMI_DIAGNOSTIC_NOT_FOUND},
           {429, QDMI_ERROR_FATAL, IBM_QDMI_DIAGNOSTIC_RATE_LIMIT},
           {500, QDMI_ERROR_FATAL, IBM_QDMI_DIAGNOSTIC_SERVICE},
           {302, QDMI_ERROR_FATAL, IBM_QDMI_DIAGNOSTIC_SERVICE}}) {
    try {
      ibm::checkResponse({.status = status, .body = "private response"});
      FAIL() << "Expected a QDMI failure";
    } catch (const ibm::Failure& error) {
      EXPECT_EQ(error.status, expected);
      EXPECT_EQ(error.diagnostic, diagnostic);
    }
  }
  expectFailure(
      [] {
        ibm::checkResponse(
            {.status = 0, .body = {}, .timedOut = true, .failed = true});
      },
      QDMI_ERROR_TIMEOUT);
  expectFailure(
      [] {
        ibm::checkResponse(
            {.status = 0, .body = {}, .timedOut = false, .failed = true});
      },
      QDMI_ERROR_FATAL);
}

TEST(Http, DefaultClockAndSleeperAcceptExpiredDeadline) {
  const auto before = std::chrono::steady_clock::now();
  const auto now = ibm::internal::hooks().now();
  EXPECT_GE(now, before);
  EXPECT_LE(now, std::chrono::steady_clock::now());
  EXPECT_NO_THROW(
      ibm::internal::hooks().sleepUntil(now - std::chrono::milliseconds{1}));
}

TEST(Http, ResolvesExplicitCaBundleBeforePlatformDefaults) {
  const ScopedEnvVar ssl{"SSL_CERT_FILE", "missing-ssl.pem"};
  const ScopedEnvVar curl{"CURL_CA_BUNDLE", "missing-curl.pem"};
  EXPECT_EQ(ibm::internal::resolveCaBundle(), "missing-curl.pem");
}

TEST(Http, EmptyCaBundleUsesFallback) {
  const ScopedEnvVar ssl{"SSL_CERT_FILE", "missing-ssl.pem"};
  for (const auto* value : {static_cast<const char*>(nullptr), ""}) {
    const ScopedEnvVar curl{"CURL_CA_BUNDLE", value};
    EXPECT_EQ(ibm::internal::resolveCaBundle(), "missing-ssl.pem");
  }
}

TEST(Http, ResolvesPlatformTrustWithoutOverrides) {
  const ScopedEnvVar curl{"CURL_CA_BUNDLE", ""};
  const ScopedEnvVar ssl{"SSL_CERT_FILE", ""};
  const auto bundle = ibm::internal::resolveCaBundle();
#ifdef __linux__
  if (std::ifstream{"/etc/ssl/certs/ca-certificates.crt"}.good()) {
    EXPECT_EQ(bundle, "/etc/ssl/certs/ca-certificates.crt");
  }
  // Minimal installations can have no system bundle; leave curl's default then.
  if (!bundle.empty()) {
    EXPECT_TRUE(std::ifstream{bundle}.good());
  }
#else
  EXPECT_TRUE(bundle.empty());
#endif
}

TEST(Http, ParsesRetryAfterWithoutOverflow) {
  using ibm::internal::parseRetryAfter;
  EXPECT_EQ(parseRetryAfter("0"), std::chrono::milliseconds{0});
  EXPECT_EQ(parseRetryAfter("2"), std::chrono::milliseconds{2000});
  EXPECT_EQ(parseRetryAfter("999999999999999999999999999999"),
            std::chrono::milliseconds::max());
  EXPECT_EQ(parseRetryAfter("18446744073709551615"),
            std::chrono::milliseconds::max());
  EXPECT_EQ(parseRetryAfter("Wed, 01 Jan 2020 00:00:00 GMT"),
            std::chrono::milliseconds{0});
  EXPECT_GT(parseRetryAfter("Fri, 31 Dec 9999 23:59:59 GMT"),
            std::chrono::hours{24});
  for (const auto* value : {"", "-1", "1.5", "invalid", "2garbage"}) {
    EXPECT_FALSE(parseRetryAfter(value).has_value()) << value;
  }
}

TEST_F(CaBundleTest, SearchesReadableCandidatesInOrder) {
  const std::array candidates{first.c_str(), second.c_str()};
  EXPECT_TRUE(ibm::internal::findCaBundle({}).empty());
  EXPECT_TRUE(ibm::internal::findCaBundle(candidates).empty());
  write(second);
  EXPECT_EQ(ibm::internal::findCaBundle(candidates), second);
  write(first);
  EXPECT_EQ(ibm::internal::findCaBundle(candidates), first);
}
