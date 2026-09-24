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
#include "Job.hpp"

#include <chrono>
#include <cstddef>
#include <gtest/gtest.h>
#include <ibm_qdmi/constants.h>
#include <nlohmann/json.hpp>
#include <nlohmann/json_fwd.hpp>
#include <string>
#include <utility>
#include <vector>

namespace {
const std::string PROGRAM =
    "OPENQASM 3.0; include \"stdgates.inc\"; qubit[2] q; "
    "bit[2] z; bit a; x q[1]; z[0] = measure q[1]; a = measure q[0];";
template <class Function> void fails(Function&& function, int expected) {
  try {
    std::forward<Function>(function)();
    FAIL() << "Expected a QDMI error";
  } catch (const ibm::Failure& error) {
    EXPECT_EQ(error.status, expected);
  }
}
nlohmann::json results() {
  return {
      {"results",
       nlohmann::json::array(
           {{{"data",
              {{"a", {{"samples", {"0x1", "0x0", "0x1"}}, {"num_bits", 1}}},
               {"z",
                {{"samples", {"0x1", "0x0", "0x1"}}, {"num_bits", 2}}}}}}})}};
}
struct Service {
  std::vector<std::string> requests;
  std::string status = "Queued";
  int submissionStatus = 200;
  int cancellationStatus = 204;
  bool loseSubmission = false;
  nlohmann::json output = results();
  nlohmann::json submitted;
  ibm::Response operator()(const ibm::Request& request) {
    requests.push_back(request.url);
    if (!request.form.empty()) {
      return {.status = 200,
              .body = R"({"access_token":"synthetic","expires_in":3600})"};
    }
    if (request.url.ends_with("/cancel")) {
      return {.status = cancellationStatus, .body = ""};
    }
    if (request.post) {
      submitted = nlohmann::json::parse(request.body);
      return {.status = submissionStatus,
              .body = R"({"id":"synthetic-job","backend":"ibm_test"})",
              .timedOut = loseSubmission};
    }
    if (request.url.ends_with("/results")) {
      return {.status = 200, .body = output.dump()};
    }
    return {.status = 200,
            .body = nlohmann::json{{"id", "synthetic-job"},
                                   {"backend", "ibm_test"},
                                   {"state", {{"status", status}}},
                                   {"program", {{"id", "sampler"}}},
                                   {"params", submitted.at("params")}}
                        .dump()};
  }
};
ibm::Configuration configuration() {
  return {.apiKey = "synthetic-key",
          .backend = "ibm_test",
          .crn = "crn:v1:bluemix:public:quantum-computing:us-east:a:instance::",
          .baseUrl = "http://127.0.0.1:1"};
}
void configure(ibm::Job& job) {
  job.setProgram(PROGRAM);
  job.format = QDMI_PROGRAM_FORMAT_QASM3;
  job.shots = 3;
}
} // namespace

TEST(Results, PreservesShotsAndClassicalBitOrder) {
  const auto decoded =
      ibm::decodeResults(results(), ibm::outputRegisters(PROGRAM, 2), 3);
  EXPECT_EQ(decoded.shots, "101,000,101");
  EXPECT_EQ(decoded.keys, "000,101");
  EXPECT_EQ(decoded.counts, (std::vector<std::size_t>{1, 2}));
}
TEST(Results, RejectsWrongWidthsCountsAndSamples) {
  for (const auto* sample : {"0x4", "0xg", "0x", "10", "-1"}) {
    auto data = results();
    data["results"][0]["data"]["z"]["samples"][0] = sample;
    fails(
        [&] {
          (void)ibm::decodeResults(data, ibm::outputRegisters(PROGRAM, 2), 3);
        },
        QDMI_ERROR_FATAL);
  }
  auto data = results();
  data["results"][0]["data"]["z"]["num_bits"] = 1;
  fails(
      [&] {
        (void)ibm::decodeResults(data, ibm::outputRegisters(PROGRAM, 2), 3);
      },
      QDMI_ERROR_FATAL);
  fails(
      [&] {
        (void)ibm::decodeResults(results(), ibm::outputRegisters(PROGRAM, 2),
                                 4);
      },
      QDMI_ERROR_FATAL);
}
TEST(Job, SubmitsOnceCachesResultsAndRetrieves) {
  Service service;
  ibm::Auth auth(configuration(),
                 [&](const auto& request) { return service(request); });
  ibm::Job job(auth, "ibm_test", 2);
  fails([&] { job.submit(); }, QDMI_ERROR_BADSTATE);
  configure(job);
  job.maxExecutionTime = 42;
  job.submit();
  EXPECT_EQ(service.submitted["cost"], 42);
  EXPECT_EQ(service.submitted["params"]["pubs"][0][2], 3);
  EXPECT_EQ(service.submitted["params"]["support_qiskit"], false);
  EXPECT_EQ(
      service.submitted["params"]["options"]["twirling"]["enable_measure"],
      false);
  EXPECT_EQ(service.submitted["params"]["options"]["dynamical_decoupling"],
            (nlohmann::json{{"enable", false},
                            {"sequence_type", "XX"},
                            {"extra_slack_distribution", "middle"},
                            {"scheduling_method", "alap"},
                            {"skip_reset_qubits", false}}));
  fails([&] { job.submit(); }, QDMI_ERROR_BADSTATE);
  EXPECT_EQ(job.check(), QDMI_JOB_STATUS_QUEUED);
  fails([&] { (void)job.results(); }, QDMI_ERROR_INVALIDARGUMENT);
  service.status = "Running";
  EXPECT_EQ(job.check(), QDMI_JOB_STATUS_RUNNING);
  service.status = "Completed";
  EXPECT_EQ(job.results().shots, "101,000,101");
  const auto requestCount = service.requests.size();
  EXPECT_EQ(job.results().counts, (std::vector<std::size_t>{1, 2}));
  EXPECT_EQ(service.requests.size(), requestCount);
  ibm::Job retrieved(auth, "ibm_test", 2);
  retrieved.retrieve(job.id);
  EXPECT_EQ(retrieved.program, job.program);
  EXPECT_EQ(retrieved.shots, job.shots);
  EXPECT_FALSE(retrieved.configurable());
  EXPECT_EQ(retrieved.results().shots, job.results().shots);
  fails([&] { retrieved.submit(); }, QDMI_ERROR_BADSTATE);
}
TEST(Job, ConfiguresDynamicalDecouplingWithoutChangingExecutionLimits) {
  for (const auto* sequence : {"XX", "XpXm", "XY4"}) {
    Service service;
    ibm::Auth auth(configuration(),
                   [&](const auto& request) { return service(request); });
    ibm::Job job(auth, "ibm_test", 2);
    configure(job);
    job.maxExecutionTime = 42;
    const nlohmann::json options{{"enable", true},
                                 {"sequence_type", sequence},
                                 {"extra_slack_distribution", "edges"},
                                 {"scheduling_method", "asap"},
                                 {"skip_reset_qubits", true}};
    job.setDynamicalDecoupling(options.dump());
    EXPECT_TRUE(service.requests.empty());
    job.submit();
    const auto& submitted = service.submitted["params"]["options"];
    EXPECT_EQ(submitted["dynamical_decoupling"], options);
    EXPECT_EQ(
        submitted["twirling"],
        (nlohmann::json{{"enable_gates", false}, {"enable_measure", false}}));
    EXPECT_EQ(service.submitted["cost"], 42);
    EXPECT_EQ(service.submitted["params"]["pubs"][0][2], 3);
    fails([&] { job.setDynamicalDecoupling("{}"); }, QDMI_ERROR_BADSTATE);
  }
}
TEST(Job, ValidatesAndReplacesDynamicalDecouplingAtomically) {
  Service service;
  ibm::Auth auth(configuration(),
                 [&](const auto& request) { return service(request); });
  ibm::Job job(auth, "ibm_test", 2);
  configure(job);
  job.setDynamicalDecoupling(
      R"({"enable":true,"sequence_type":"XY4","skip_reset_qubits":true})");
  job.setDynamicalDecoupling(R"({"enable":true})");
  for (const auto* invalid :
       {"", "{", "[]", "null", "true", "42", R"("XX")", R"({"unknown":true})",
        R"({"enable":1})", R"({"enable":"true"})",
        R"({"skip_reset_qubits":null})", R"({"sequence_type":"xx"})",
        R"({"sequence_type":true})", R"({"extra_slack_distribution":"center"})",
        R"({"extra_slack_distribution":[]})", R"({"scheduling_method":"ALAP"})",
        R"({"scheduling_method":0})", R"({"enable":false,"invalid":true})"}) {
    fails([&] { job.setDynamicalDecoupling(invalid); },
          QDMI_ERROR_INVALIDARGUMENT);
  }
  EXPECT_TRUE(service.requests.empty());
  job.submit();
  EXPECT_EQ(service.submitted["params"]["options"]["dynamical_decoupling"],
            (nlohmann::json{{"enable", true},
                            {"sequence_type", "XX"},
                            {"extra_slack_distribution", "middle"},
                            {"scheduling_method", "alap"},
                            {"skip_reset_qubits", false}}));
}
TEST(Job, NeverRetriesUnauthorizedOrAmbiguousSubmission) {
  for (const bool ambiguous : {false, true}) {
    Service service;
    service.submissionStatus = ambiguous ? 200 : 401;
    service.loseSubmission = ambiguous;
    ibm::Auth auth(configuration(),
                   [&](const auto& request) { return service(request); });
    ibm::Job job(auth, "ibm_test", 2);
    configure(job);
    job.setDynamicalDecoupling(R"({"enable":true})");
    fails([&] { job.submit(); },
          ambiguous ? QDMI_ERROR_TIMEOUT : QDMI_ERROR_PERMISSIONDENIED);
    const auto count = service.requests.size();
    fails([&] { job.submit(); }, QDMI_ERROR_BADSTATE);
    EXPECT_EQ(service.requests.size(), count);
    EXPECT_EQ(count, 2);
    EXPECT_EQ(job.check(), QDMI_JOB_STATUS_FAILED);
  }
}
TEST(Job, CancelsAndHandlesCompletionRace) {
  for (const bool race : {false, true}) {
    Service service;
    ibm::Auth auth(configuration(),
                   [&](const auto& request) { return service(request); });
    ibm::Job job(auth, "ibm_test", 2);
    configure(job);
    job.submit();
    if (race) {
      service.cancellationStatus = 409;
      service.status = "Completed";
      fails([&] { job.cancel(); }, QDMI_ERROR_INVALIDARGUMENT);
      EXPECT_EQ(job.check(), QDMI_JOB_STATUS_DONE);
      const auto requests = service.requests.size();
      fails([&] { job.cancel(); }, QDMI_ERROR_INVALIDARGUMENT);
      EXPECT_EQ(service.requests.size(), requests);
    } else {
      job.cancel();
      EXPECT_EQ(job.check(), QDMI_JOB_STATUS_CANCELED);
      job.cancel();
      fails([&] { (void)job.results(); }, QDMI_ERROR_INVALIDARGUMENT);
    }
  }
}
TEST(Auth, DeadlineIncludesRefreshAndBackendRequest) {
  auto now = std::chrono::steady_clock::now();
  const auto deadline = now + std::chrono::seconds{5};
  std::vector<std::chrono::milliseconds> timeouts;
  ibm::Auth auth(
      configuration(),
      [&](const ibm::Request& request) {
        timeouts.push_back(request.timeout);
        now += std::chrono::seconds{2};
        return ibm::Response{
            .status = 200,
            .body = request.form.empty()
                        ? "{}"
                        : R"({"access_token":"synthetic","expires_in":3600})"};
      },
      [&] { return now; });
  (void)auth.get("/v1/jobs/synthetic", deadline);
  ASSERT_EQ(timeouts.size(), 2);
  EXPECT_EQ(timeouts[0], std::chrono::seconds{5});
  EXPECT_EQ(timeouts[1], std::chrono::seconds{3});
  now = deadline;
  fails([&] { (void)auth.get("/v1/jobs/synthetic", deadline); },
        QDMI_ERROR_TIMEOUT);
  EXPECT_EQ(timeouts.size(), 2);
}
