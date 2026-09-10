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
#include "Metadata.hpp"

#include <atomic>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <gtest/gtest.h>
#include <ibm_qdmi/constants.h>
#include <limits>
#include <nlohmann/json.hpp>
#include <nlohmann/json_fwd.hpp>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {
nlohmann::json fixture() {
  std::ifstream input(IBM_QDMI_FIXTURE_FILE);
  return nlohmann::json::parse(input);
}
ibm::Configuration configuration() {
  return {.apiKey = "synthetic-key",
          .backend = "ibm_test",
          .crn =
              "crn:v1:bluemix:public:quantum-computing:us-east:a:instance::"};
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
TEST(Auth, RefreshesBeforeExpiryAndRetriesUnauthorizedGetOnce) {
  auto now = std::chrono::steady_clock::time_point{};
  int exchanges = 0;
  int requests = 0;
  bool unauthorized = false;
  ibm::Auth auth(
      ibm::resolve(configuration()),
      [&](const ibm::Request& request) {
        if (!request.form.empty()) {
          ++exchanges;
          EXPECT_EQ(request.form.at("apikey"), "synthetic-key");
          EXPECT_FALSE(request.headers.contains("Authorization"));
          return ibm::Response{.status = 200, .body = fixture()["auth"].dump()};
        }
        ++requests;
        EXPECT_EQ(request.headers.at("IBM-API-Version"), "2026-04-15");
        EXPECT_EQ(request.headers.at("Authorization"),
                  "Bearer synthetic-bearer");
        return ibm::Response{.status = unauthorized ? 401 : 200, .body = "{}"};
      },
      [&] { return now; });
  EXPECT_EQ(auth.get("/v1/backends/ibm_test/status"), "{}");
  (void)auth.get("/v1/backends/ibm_test/status");
  EXPECT_EQ(exchanges, 1);
  now += std::chrono::seconds{3540};
  (void)auth.get("/v1/backends/ibm_test/status");
  EXPECT_EQ(exchanges, 2);
  unauthorized = true;
  expectFailure([&] { (void)auth.get("/v1/backends/ibm_test/status"); },
                QDMI_ERROR_PERMISSIONDENIED);
  EXPECT_EQ(exchanges, 3);
  EXPECT_EQ(requests, 5);
}
TEST(Auth, SerializesConcurrentRefresh) {
  std::atomic<int> exchanges{0};
  ibm::Auth auth(
      ibm::resolve(configuration()), [&](const ibm::Request& request) {
        if (!request.form.empty()) {
          ++exchanges;
          return ibm::Response{.status = 200, .body = fixture()["auth"].dump()};
        }
        return ibm::Response{.status = 200, .body = "{}"};
      });
  std::vector<std::jthread> threads;
  threads.reserve(8);
  for (int i = 0; i < 8; ++i) {
    threads.emplace_back([&] { EXPECT_EQ(auth.get("/status"), "{}"); });
  }
  threads.clear();
  EXPECT_EQ(exchanges, 1);
}
TEST(Http, MapsFailuresWithoutServerText) {
  for (const auto& [status, expected] :
       std::vector<std::pair<std::int32_t, int>>{
           {401, QDMI_ERROR_PERMISSIONDENIED},
           {403, QDMI_ERROR_PERMISSIONDENIED},
           {404, QDMI_ERROR_NOTFOUND},
           {429, QDMI_ERROR_FATAL},
           {500, QDMI_ERROR_FATAL},
           {302, QDMI_ERROR_FATAL}}) {
    expectFailure(
        [&] {
          ibm::checkResponse({.status = status, .body = "private response"});
        },
        expected);
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
TEST(Metadata, ConvertsUnitsAndPreservesDirectedTuples) {
  const auto data = fixture();
  const auto metadata =
      ibm::parseMetadata(data["configuration"], data["properties"]);
  ASSERT_EQ(metadata.sites.size(), 2);
  EXPECT_EQ(metadata.sites[0].t1, 100500000);
  EXPECT_EQ(metadata.sites[0].t2, 200000000);
  EXPECT_FALSE(metadata.sites[1].t1);
  EXPECT_EQ(metadata.coupling, (std::vector<ibm::Sites>{{0, 1}}));
  const auto& operation = metadata.operations[2];
  EXPECT_EQ(operation.arity, 2);
  EXPECT_EQ(operation.parameters, 0);
  EXPECT_EQ(operation.sites, (std::vector<ibm::Sites>{{0, 1}}));
  EXPECT_EQ(operation.calibrations.front().second.duration, 35556);
  EXPECT_DOUBLE_EQ(*operation.calibrations.front().second.fidelity, 0.98);
}
TEST(Metadata, MissingAndInvalidCalibrationIsNotZero) {
  auto data = fixture();
  EXPECT_FALSE(
      ibm::parseMetadata(data["configuration"], nlohmann::json::object())
          .sites[0]
          .t1);
  for (const auto value :
       {-1.0, 1e30, std::numeric_limits<double>::infinity()}) {
    data["properties"]["qubits"][0][0]["value"] = value;
    EXPECT_FALSE(ibm::parseMetadata(data["configuration"], data["properties"])
                     .sites[0]
                     .t1);
  }
  data["properties"]["qubits"][0][0] = {
      {"name", "T1"}, {"value", 1}, {"unit", "unknown"}};
  EXPECT_FALSE(ibm::parseMetadata(data["configuration"], data["properties"])
                   .sites[0]
                   .t1);
}
TEST(Metadata, RejectsInconsistentTopologyAndStatus) {
  auto data = fixture();
  data["configuration"]["coupling_map"] = {{0, 2}};
  expectFailure(
      [&] {
        (void)ibm::parseMetadata(data["configuration"], data["properties"]);
      },
      QDMI_ERROR_FATAL);
  data = fixture();
  data["properties"]["gates"][0]["qubits"] = {1, 0};
  expectFailure(
      [&] {
        (void)ibm::parseMetadata(data["configuration"], data["properties"]);
      },
      QDMI_ERROR_FATAL);
  expectFailure([] { (void)ibm::parseStatus({{"length_queue", -1}}); },
                QDMI_ERROR_FATAL);
  EXPECT_FALSE(ibm::parseStatus({{"length_queue", 0}}).available);
}
