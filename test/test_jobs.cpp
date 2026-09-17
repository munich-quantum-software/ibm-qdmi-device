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

TEST(Program, PreservesDeclarationOrderAndPhysicalIndices) {
  const auto named = ibm::outputRegisters(
      "OPENQASM 3; bit[1] q; qubit[5] physical; q[0] = measure physical[4];",
      5);
  ASSERT_EQ(named.size(), 1);
  EXPECT_EQ(named[0].name, "q");
  const auto layout = ibm::outputRegisters(PROGRAM, 2);
  ASSERT_EQ(layout.size(), 2);
  EXPECT_EQ(layout[0].name, "z");
  EXPECT_EQ(layout[0].width, 2);
  EXPECT_EQ(layout[1].name, "a");
  EXPECT_EQ(ibm::outputRegisters("OPENQASM 3; // bit[9] ignored;\n bit[1] c; "
                                 "/* ignored */ x $119; c[0] = measure $119;",
                                 120)
                .size(),
            1);
  EXPECT_EQ(ibm::outputRegisters("OPENQASM 3; qreg q[2]; creg c[2]; rz(-pi/2) "
                                 "q[0]; measure q[0] -> c[1];",
                                 2)
                .at(0)
                .width,
            2);
}
TEST(Program, RejectsAmbiguousOrUnsupportedPrograms) {
  for (const auto* source :
       {"OPENQASM 2;", "OPENQASM 3; bit[0] c;", "OPENQASM 3; bit[2] c; bit c;",
        "OPENQASM 3; bit c; c = measure $2;", "OPENQASM 3; /* unterminated",
        "OPENQASM 3; bit c; c = measure $0",
        "OPENQASM 3; qubit[2] physical; bit physical;",
        "OPENQASM 3; bit physical; qubit[2] physical;"}) {
    fails([&] { (void)ibm::outputRegisters(source, 2); },
          QDMI_ERROR_INVALIDARGUMENT);
  }
  for (const auto* source :
       {"OPENQASM 3; qubit[1] q;", "OPENQASM 3; input float theta;",
        "OPENQASM 3; bit c; if (true) { c = measure $0; }",
        "OPENQASM 3; bit c; rz(theta) $0; c = measure $0;",
        "OPENQASM 3; bit c; c = true; c = measure $0;"}) {
    fails([&] { (void)ibm::outputRegisters(source, 2); },
          QDMI_ERROR_NOTSUPPORTED);
  }
}
TEST(Program, PreservesResultsAcrossStaticGateDefinitions) {
  const auto registers = ibm::outputRegisters(
      "OPENQASM 3; include \"stdgates.inc\"; "
      "gate rzz(theta) a,b { cx a,b; rz(theta) b; cx a,b; } "
      "qubit[5] q; bit[2] c; rzz(pi/4) q[3],q[4]; c[1] = measure q[4];",
      5);
  ASSERT_EQ(registers.size(), 1);
  EXPECT_EQ(registers[0].name, "c");
  EXPECT_EQ(registers[0].width, 2);
  for (const auto* program :
       {"OPENQASM 3; gate g a { bit c; c = measure a; } bit c; c = measure $0;",
        "OPENQASM 3; gate g a { rz(unbound) a; } bit c; c = measure $0;",
        "OPENQASM 3; gate g a { x outside; } bit c; c = measure $0;",
        "OPENQASM 3; gate g a { reset a; } bit c; c = measure $0;",
        "OPENQASM 3; gate g a { if (true) { x a; } } bit c; c = measure $0;"}) {
    fails([&] { (void)ibm::outputRegisters(program, 5); },
          QDMI_ERROR_NOTSUPPORTED);
  }
  for (const auto* program :
       {"OPENQASM 3; gate g a { x a;",
        "OPENQASM 3; gate g(p,p) a { rz(p) a; } bit c; c = measure $0;",
        "OPENQASM 3; gate g a { x a; } gate g a { x a; } bit c; c = measure "
        "$0;"}) {
    fails([&] { (void)ibm::outputRegisters(program, 5); },
          QDMI_ERROR_INVALIDARGUMENT);
  }
}
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
  fails([&] { job.submit(); }, QDMI_ERROR_BADSTATE);
  EXPECT_EQ(job.check(), QDMI_JOB_STATUS_QUEUED);
  fails([&] { (void)job.results(); }, QDMI_ERROR_BADSTATE);
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
TEST(Job, NeverRetriesUnauthorizedOrAmbiguousSubmission) {
  for (const bool ambiguous : {false, true}) {
    Service service;
    service.submissionStatus = ambiguous ? 200 : 401;
    service.loseSubmission = ambiguous;
    ibm::Auth auth(configuration(),
                   [&](const auto& request) { return service(request); });
    ibm::Job job(auth, "ibm_test", 2);
    configure(job);
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
      fails([&] { job.cancel(); }, QDMI_ERROR_BADSTATE);
      EXPECT_EQ(job.check(), QDMI_JOB_STATUS_DONE);
    } else {
      job.cancel();
      EXPECT_EQ(job.check(), QDMI_JOB_STATUS_CANCELED);
      job.cancel();
      fails([&] { (void)job.results(); }, QDMI_ERROR_BADSTATE);
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
