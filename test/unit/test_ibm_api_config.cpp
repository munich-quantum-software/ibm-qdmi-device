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

#include "Auth.hpp"
#include "Http.hpp"

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <gtest/gtest.h>
#include <ibm_qdmi/constants.h>
#include <ios>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace {
ibm::Configuration configuration() {
  return {.apiKey = "synthetic-key",
          .backend = "ibm_test",
          .crn = "crn:v1:bluemix:public:quantum-computing:us-east:a:instance::",
          .apiKeyConfigured = true,
          .backendConfigured = true,
          .crnConfigured = true};
}
template <class Function> void expectFailure(Function&& function, int status) {
  try {
    std::forward<Function>(function)();
    FAIL() << "Expected a QDMI failure";
  } catch (const ibm::Failure& error) {
    EXPECT_EQ(error.status, status);
  }
}
} // namespace

TEST(Configuration, RegionsAndOverrides) {
  EXPECT_EQ(ibm::resolve(configuration()).baseUrl,
            "https://quantum.cloud.ibm.com/api");
  auto config = configuration();
  config.crn = "crn:v1:bluemix:public:quantum-computing:eu-de:a:instance::";
  EXPECT_EQ(ibm::resolve(config).baseUrl,
            "https://eu-de.quantum.cloud.ibm.com/api");
  config.baseUrl = "http://127.0.0.1:12345/api/";
  EXPECT_EQ(ibm::resolve(config).baseUrl, "http://127.0.0.1:12345/api");
  config.apiKey.clear();
  expectFailure([&] { (void)ibm::resolve(config); },
                QDMI_ERROR_PERMISSIONDENIED);
}
TEST(Configuration, RejectsUnsafeEndpointsAndInvalidSelection) {
  for (const auto* url :
       {"http://example.com", "file:///tmp/test",
        "https://user:secret@example.com", "http://127.0.0.1.example.com",
        "https://example.com?token=secret"}) {
    EXPECT_FALSE(ibm::validEndpoint(url));
  }
  auto config = configuration();
  config.backend = "../jobs";
  expectFailure([&] { (void)ibm::resolve(config); },
                QDMI_ERROR_INVALIDARGUMENT);
  config = configuration();
  config.crn += "\r\nInjected: header";
  expectFailure([&] { (void)ibm::resolve(config); },
                QDMI_ERROR_INVALIDARGUMENT);
}
TEST(Configuration, RequestTimeoutHasPortableBounds) {
  EXPECT_EQ(ibm::parseRequestTimeout("1"), std::chrono::milliseconds{1});
  EXPECT_EQ(ibm::parseRequestTimeout("2147483647"),
            std::chrono::milliseconds{2147483647});
  for (const auto* value : {"", "0", "-1", "+1", " 1", "1 ", "1.5", "1ms",
                            "2147483648", "9999999999999999999999"}) {
    expectFailure([&] { static_cast<void>(ibm::parseRequestTimeout(value)); },
                  QDMI_ERROR_INVALIDARGUMENT);
  }
}

#ifdef _MSC_VER
#include <cstddef>
#include <memory>
#include <stdlib.h> // NOLINT(modernize-deprecated-headers) -- MSVC environment extensions
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
class ConfigurationFileTest : public testing::Test {
protected:
  ScopedEnvVar key{"IBM_QUANTUM_API_KEY", "environment-key"};
  std::filesystem::path path =
      std::filesystem::path(testing::TempDir()) /
      ("ibm-qdmi-key-" +
       std::to_string(
           std::chrono::steady_clock::now().time_since_epoch().count()));
  void TearDown() override { std::filesystem::remove(path); }
  void write(const std::string& text) {
    std::ofstream output(path, std::ios::binary);
    output << text;
    ASSERT_TRUE(output.good());
  }
  [[nodiscard]] ibm::Configuration config() const {
    auto value = configuration();
    value.apiKey.clear();
    value.apiKeyConfigured = false;
    value.authFile = path.string();
    return value;
  }
};
} // namespace

TEST(Configuration, EnvironmentDefaultsAndExplicitEmptyValues) {
  const ScopedEnvVar key{"IBM_QUANTUM_API_KEY", "environment-key"};
  const ScopedEnvVar backend{"IBM_QUANTUM_BACKEND", "ibm_test"};
  const ScopedEnvVar crn{
      "IBM_QUANTUM_INSTANCE_CRN",
      "crn:v1:bluemix:public:quantum-computing:us-east:a:instance::"};
  const auto resolved = ibm::resolve({});
  EXPECT_EQ(resolved.apiKey, "environment-key");
  EXPECT_EQ(resolved.backend, "ibm_test");
  EXPECT_EQ(resolved.crn, configuration().crn);
  auto explicitValues = configuration();
  EXPECT_EQ(ibm::resolve(explicitValues).apiKey, "synthetic-key");
  explicitValues.apiKey.clear();
  expectFailure([&] { (void)ibm::resolve(explicitValues); },
                QDMI_ERROR_PERMISSIONDENIED);
  explicitValues = configuration();
  explicitValues.backend.clear();
  expectFailure([&] { (void)ibm::resolve(explicitValues); },
                QDMI_ERROR_INVALIDARGUMENT);
  explicitValues = configuration();
  explicitValues.crn.clear();
  expectFailure([&] { (void)ibm::resolve(explicitValues); },
                QDMI_ERROR_INVALIDARGUMENT);
}

TEST_F(ConfigurationFileTest, FilePrecedesEnvironmentAndAcceptsLineEndings) {
  for (const auto* ending : {"", "\n", "\r\n"}) {
    const std::string keyText = "synthetic-\xc3\xa4-key";
    write(keyText + ending);
    EXPECT_EQ(ibm::resolve(config()).apiKey, keyText);
  }
}

TEST_F(ConfigurationFileTest, ExplicitTokenSkipsFileAccess) {
  auto value = configuration();
  value.authFile = path.string();
  EXPECT_FALSE(std::filesystem::exists(path));
  EXPECT_EQ(ibm::resolve(value).apiKey, "synthetic-key");
}

TEST_F(ConfigurationFileTest, RejectsMalformedFilesAndAllowsRecovery) {
  for (const auto& content :
       std::vector<std::string>{"", "\n", "key\n\n", "key\r", "ke\ny", "ke\ry",
                                std::string("ke\0y", 4), "key\xff"}) {
    write(content);
    expectFailure([&] { (void)ibm::resolve(config()); },
                  QDMI_ERROR_INVALIDARGUMENT);
    write("recovered-key");
    EXPECT_EQ(ibm::resolve(config()).apiKey, "recovered-key");
  }
}

TEST_F(ConfigurationFileTest, UnreadableFilesDoNotFallBackToEnvironment) {
  expectFailure([&] { (void)ibm::resolve(config()); },
                QDMI_ERROR_PERMISSIONDENIED);
  auto value = config();
  value.authFile = "";
  expectFailure([&] { (void)ibm::resolve(value); }, QDMI_ERROR_INVALIDARGUMENT);
}
