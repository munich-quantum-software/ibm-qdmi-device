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

#include <atomic>
#include <chrono>
#include <fstream>
#include <future>
#include <gtest/gtest.h>
#include <ibm_qdmi/constants.h>
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
