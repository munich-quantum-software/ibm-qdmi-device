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
#include <future>
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
TEST(Auth, RequestTimeoutBoundsRefreshAndRetry) {
  for (const auto timeout :
       {std::chrono::milliseconds{30000}, std::chrono::milliseconds{125}}) {
    auto config = ibm::resolve(configuration());
    config.requestTimeout = timeout;
    auto now = std::chrono::steady_clock::now();
    const auto deadline = now + std::chrono::milliseconds{40000};
    std::vector<std::chrono::milliseconds> timeouts;
    int backendRequests = 0;
    ibm::Auth auth(
        config,
        [&](const ibm::Request& request) {
          timeouts.push_back(request.timeout);
          if (!request.form.empty()) {
            return ibm::Response{.status = 200,
                                 .body = fixture()["auth"].dump()};
          }
          if (++backendRequests == 1) {
            now = deadline - std::chrono::milliseconds{50};
            return ibm::Response{.status = 401, .body = "{}"};
          }
          return ibm::Response{.status = 200, .body = "{}"};
        },
        [&] { return now; });
    EXPECT_EQ(auth.get("/status", deadline), "{}");
    EXPECT_EQ(timeouts, (std::vector<std::chrono::milliseconds>{
                            timeout, timeout, std::chrono::milliseconds{50},
                            std::chrono::milliseconds{50}}));
  }
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
TEST(Auth, IndependentRequestsRunConcurrently) {
  std::promise<void> entered;
  std::promise<void> release;
  const auto released = release.get_future().share();
  ibm::Auth auth(
      ibm::resolve(configuration()), [&](const ibm::Request& request) {
        if (!request.form.empty()) {
          return ibm::Response{.status = 200, .body = fixture()["auth"].dump()};
        }
        if (request.url.ends_with("/slow")) {
          entered.set_value();
          EXPECT_EQ(released.wait_for(std::chrono::seconds{5}),
                    std::future_status::ready);
        }
        return ibm::Response{.status = 200, .body = "{}"};
      });
  auto slow = std::async(std::launch::async, [&] { return auth.get("/slow"); });
  EXPECT_EQ(entered.get_future().wait_for(std::chrono::seconds{5}),
            std::future_status::ready);
  auto fast = std::async(std::launch::async, [&] { return auth.get("/fast"); });
  EXPECT_EQ(fast.wait_for(std::chrono::seconds{2}), std::future_status::ready);
  release.set_value();
  EXPECT_EQ(fast.get(), "{}");
  EXPECT_EQ(slow.get(), "{}");
}
TEST(Auth, ConcurrentExpiredRequestsShareRefresh) {
  std::atomic<int> exchanges{0};
  std::atomic<int> elapsed{0};
  std::promise<void> entered;
  std::promise<void> release;
  const auto released = release.get_future().share();
  const auto started = std::chrono::steady_clock::now();
  ibm::Auth auth(
      ibm::resolve(configuration()),
      [&](const ibm::Request& request) {
        if (!request.form.empty()) {
          if (++exchanges == 2) {
            entered.set_value();
            EXPECT_EQ(released.wait_for(std::chrono::seconds{5}),
                      std::future_status::ready);
          }
          return ibm::Response{.status = 200, .body = fixture()["auth"].dump()};
        }
        return ibm::Response{.status = 200, .body = "{}"};
      },
      [&] { return started + std::chrono::seconds{elapsed.load()}; });
  EXPECT_EQ(auth.get("/initial"), "{}");
  elapsed = 3600;
  std::vector<std::future<std::string>> requests;
  requests.reserve(8);
  for (int i = 0; i < 8; ++i) {
    requests.push_back(
        std::async(std::launch::async, [&] { return auth.get("/status"); }));
  }
  EXPECT_EQ(entered.get_future().wait_for(std::chrono::seconds{5}),
            std::future_status::ready);
  release.set_value();
  for (auto& request : requests) {
    EXPECT_EQ(request.get(), "{}");
  }
  EXPECT_EQ(exchanges, 2);
}
TEST(Auth, LateUnauthorizedResponsesPreserveRefreshedToken) {
  for (const auto post : {false, true}) {
    std::atomic<int> exchanges{0};
    std::atomic<int> slowRequests{0};
    std::atomic<int> fastRequests{0};
    std::promise<void> entered;
    std::promise<void> release;
    const auto released = release.get_future().share();
    ibm::Auth auth(
        ibm::resolve(configuration()), [&](const ibm::Request& request) {
          if (!request.form.empty()) {
            ++exchanges;
            // Equal bearer strings still represent separate IAM exchanges.
            return ibm::Response{.status = 200,
                                 .body = fixture()["auth"].dump()};
          }
          if (request.url.ends_with("/slow") && ++slowRequests == 1) {
            entered.set_value();
            EXPECT_EQ(released.wait_for(std::chrono::seconds{5}),
                      std::future_status::ready);
            return ibm::Response{.status = 401, .body = "{}"};
          }
          if (request.url.ends_with("/fast") && ++fastRequests == 1) {
            return ibm::Response{.status = 401, .body = "{}"};
          }
          return ibm::Response{.status = 200, .body = "{}"};
        });
    auto slow = std::async(std::launch::async,
                           [&] { return auth.request("/slow", post); });
    EXPECT_EQ(entered.get_future().wait_for(std::chrono::seconds{5}),
              std::future_status::ready);
    auto fast =
        std::async(std::launch::async, [&] { return auth.get("/fast"); });
    EXPECT_EQ(fast.wait_for(std::chrono::seconds{2}),
              std::future_status::ready);
    release.set_value();
    EXPECT_EQ(fast.get(), "{}");
    EXPECT_EQ(slow.get().status, post ? 401 : 200);
    EXPECT_EQ(auth.get("/after"), "{}");
    EXPECT_EQ(exchanges, 2);
    EXPECT_EQ(slowRequests, post ? 1 : 2);
    EXPECT_EQ(fastRequests, 2);
  }
}
TEST(Auth, DeadlineBoundsWaitingForRefresh) {
  std::atomic<int> exchanges{0};
  std::promise<void> entered;
  std::promise<void> release;
  const auto released = release.get_future().share();
  ibm::Auth auth(
      ibm::resolve(configuration()), [&](const ibm::Request& request) {
        if (!request.form.empty()) {
          ++exchanges;
          entered.set_value();
          EXPECT_EQ(released.wait_for(std::chrono::seconds{5}),
                    std::future_status::ready);
          return ibm::Response{.status = 200, .body = fixture()["auth"].dump()};
        }
        return ibm::Response{.status = 200, .body = "{}"};
      });
  auto first =
      std::async(std::launch::async, [&] { return auth.get("/first"); });
  EXPECT_EQ(entered.get_future().wait_for(std::chrono::seconds{5}),
            std::future_status::ready);
  const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::milliseconds{20};
  expectFailure([&] { static_cast<void>(auth.get("/second", deadline)); },
                QDMI_ERROR_TIMEOUT);
  release.set_value();
  EXPECT_EQ(first.get(), "{}");
  EXPECT_EQ(auth.get("/after"), "{}");
  EXPECT_EQ(exchanges, 1);
}
TEST(Auth, FailedRefreshReleasesWaitingRequests) {
  std::atomic<int> exchanges{0};
  std::promise<void> entered;
  std::promise<void> release;
  const auto released = release.get_future().share();
  ibm::Auth auth(
      ibm::resolve(configuration()), [&](const ibm::Request& request) {
        if (!request.form.empty()) {
          if (++exchanges == 1) {
            entered.set_value();
            EXPECT_EQ(released.wait_for(std::chrono::seconds{5}),
                      std::future_status::ready);
            throw ibm::Failure{QDMI_ERROR_FATAL};
          }
          return ibm::Response{.status = 200, .body = fixture()["auth"].dump()};
        }
        return ibm::Response{.status = 200, .body = "{}"};
      });
  auto first = std::async(std::launch::async, [&] {
    expectFailure([&] { static_cast<void>(auth.get("/first")); },
                  QDMI_ERROR_FATAL);
  });
  EXPECT_EQ(entered.get_future().wait_for(std::chrono::seconds{5}),
            std::future_status::ready);
  auto second =
      std::async(std::launch::async, [&] { return auth.get("/second"); });
  release.set_value();
  first.get();
  EXPECT_EQ(second.get(), "{}");
  EXPECT_EQ(exchanges, 2);
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
  EXPECT_EQ(operation.calibrations.at({0, 1}).duration, 35556);
  EXPECT_DOUBLE_EQ(*operation.calibrations.at({0, 1}).fidelity, 0.98);
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

TEST(Metadata, ExposesAdvertisedMeasurementAndReset) {
  auto data = fixture();
  data["configuration"]["supported_instructions"] = {"measure", "reset",
                                                     "delay"};
  data["properties"]["qubits"][0].push_back(
      {{"name", "readout_length"}, {"value", 1.5}, {"unit", "us"}});
  data["properties"]["qubits"][0].push_back(
      {{"name", "readout_error"}, {"value", 0.03}});
  data["properties"]["qubits"][1].push_back(
      {{"name", "operational"}, {"value", false}});
  auto metadata = ibm::parseMetadata(data["configuration"], data["properties"]);
  ASSERT_EQ(metadata.operations.size(), 5);
  const auto& measurement = metadata.operations[3];
  EXPECT_EQ(measurement.name, "measure");
  EXPECT_EQ(measurement.arity, 1);
  EXPECT_EQ(measurement.parameters, 0);
  EXPECT_EQ(measurement.sites, (std::vector<ibm::Sites>{{0}}));
  ASSERT_EQ(measurement.calibrations.size(), 1);
  EXPECT_EQ(measurement.calibrations.at({0}).duration, 1500000);
  EXPECT_DOUBLE_EQ(*measurement.calibrations.at({0}).fidelity, 0.97);
  EXPECT_EQ(metadata.operations[4].name, "reset");
  EXPECT_EQ(metadata.operations[4].sites, measurement.sites);
  metadata =
      ibm::parseMetadata(data["configuration"], nlohmann::json::object());
  EXPECT_EQ(metadata.operations[3].sites.size(), 2);
  EXPECT_TRUE(metadata.operations[3].calibrations.empty());
  data["configuration"].erase("supported_instructions");
  EXPECT_EQ(ibm::parseMetadata(data["configuration"], data["properties"])
                .operations.size(),
            3);
}
TEST(Metadata, MergesRepeatedMeasurementCalibration) {
  auto data = fixture();
  data["configuration"]["supported_instructions"] = {"measure"};
  data["properties"]["qubits"][0].push_back(
      {{"name", "readout_length"}, {"value", 1.5}, {"unit", "us"}});
  data["properties"]["gates"].push_back(
      {{"gate", "measure"},
       {"qubits", {0}},
       {"parameters",
        {{{"name", "gate_length"}, {"value", 2}, {"unit", "us"}},
         {{"name", "gate_error"}, {"value", 0.03}}}}});
  const auto metadata =
      ibm::parseMetadata(data["configuration"], data["properties"]);
  const auto& measurement = metadata.operations[3];
  ASSERT_EQ(measurement.calibrations.size(), 1);
  EXPECT_EQ(measurement.calibrations.at({0}).duration, 1500000);
  EXPECT_DOUBLE_EQ(*measurement.calibrations.at({0}).fidelity, 0.97);
}

TEST(Metadata, PreservesTupleOrderAndFiltersFaultyCalibrations) {
  auto data = fixture();
  data["configuration"]["gates"][2]["coupling_map"] = {{1, 0}, {0, 1}};
  auto reverse = data["properties"]["gates"][0];
  reverse["qubits"] = {1, 0};
  data["properties"]["gates"].push_back(reverse);
  auto metadata = ibm::parseMetadata(data["configuration"], data["properties"]);
  EXPECT_EQ(metadata.operations[2].sites,
            (std::vector<ibm::Sites>{{1, 0}, {0, 1}}));
  EXPECT_EQ(metadata.operations[2].calibrations.size(), 2);
  data["properties"]["gates"][0]["parameters"].push_back(
      {{"name", "operational"}, {"value", false}});
  metadata = ibm::parseMetadata(data["configuration"], data["properties"]);
  EXPECT_EQ(metadata.operations[2].sites, (std::vector<ibm::Sites>{{1, 0}}));
  ASSERT_EQ(metadata.operations[2].calibrations.size(), 1);
  EXPECT_TRUE(metadata.operations[2].calibrations.contains({1, 0}));
}
TEST(Metadata, RejectsRepeatedGateCalibration) {
  for (const auto measurement : {false, true}) {
    auto data = fixture();
    if (measurement) {
      data["configuration"]["supported_instructions"] = {"measure"};
      data["properties"]["qubits"][0].push_back(
          {{"name", "readout_error"}, {"value", 0.03}});
      data["properties"]["gates"][0]["gate"] = "measure";
      data["properties"]["gates"][0]["qubits"] = {0};
    }
    const auto duplicate = data["properties"]["gates"][0];
    data["properties"]["gates"].push_back(duplicate);
    expectFailure(
        [&] {
          static_cast<void>(
              ibm::parseMetadata(data["configuration"], data["properties"]));
        },
        QDMI_ERROR_FATAL);
  }
}
TEST(Metadata, InvalidErrorsPreserveEarlierCalibration) {
  for (const auto& invalid :
       {nlohmann::json{}, nlohmann::json("invalid"), nlohmann::json(-0.1),
        nlohmann::json(1.1),
        nlohmann::json(std::numeric_limits<double>::infinity())}) {
    auto data = fixture();
    data["configuration"]["supported_instructions"] = {"measure"};
    data["properties"]["qubits"][0].push_back(
        {{"name", "readout_error"}, {"value", 0.03}});
    data["properties"]["qubits"][0].push_back(
        {{"name", "readout_error"}, {"value", invalid}});
    data["properties"]["gates"][0]["parameters"].push_back(
        {{"name", "gate_error"}, {"value", invalid}});
    const auto metadata =
        ibm::parseMetadata(data["configuration"], data["properties"]);
    EXPECT_DOUBLE_EQ(*metadata.operations[2].calibrations.at({0, 1}).fidelity,
                     0.98);
    EXPECT_DOUBLE_EQ(*metadata.operations[3].calibrations.at({0}).fidelity,
                     0.97);
  }
}
