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
#include "http_stub.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <gtest/gtest.h>
#include <ibm-qdmi-device/constants.h>
#include <ibm_qdmi/device.h>
#include <limits>
#include <new>
#include <nlohmann/json.hpp>
#include <nlohmann/json_fwd.hpp>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
const std::string PROGRAM = "OPENQASM 3; qubit[2] q; bit[2] z; bit a; "
                            "z[0] = measure q[1]; a = measure q[0];";
class DeviceTest : public testing::Test {
protected:
  ibm::test_support::HttpStub http;
  nlohmann::json data;
  IBM_QDMI_Device_Session session = nullptr;
  std::vector<IBM_QDMI_Device_Session> sessions;
  std::vector<IBM_QDMI_Device_Job> jobs;
  void SetUp() override {
    std::ifstream input(IBM_QDMI_FIXTURE_FILE);
    data = nlohmann::json::parse(input);
    ASSERT_EQ(IBM_QDMI_device_initialize(), QDMI_SUCCESS);
    session = allocate();
  }
  void TearDown() override {
    for (auto* job : jobs) {
      IBM_QDMI_device_job_free(job);
    }
    for (auto* owned : sessions) {
      IBM_QDMI_device_session_free(owned);
    }
    EXPECT_EQ(IBM_QDMI_device_finalize(), QDMI_SUCCESS);
  }
  IBM_QDMI_Device_Session allocate() {
    IBM_QDMI_Device_Session value = nullptr;
    EXPECT_EQ(IBM_QDMI_device_session_alloc(&value), QDMI_SUCCESS);
    sessions.push_back(value);
    set(value, QDMI_DEVICE_SESSION_PARAMETER_TOKEN, "synthetic-key");
    set(value, IBM_QDMI_DEVICE_SESSION_PARAMETER_BACKEND, "ibm_test");
    set(value, IBM_QDMI_DEVICE_SESSION_PARAMETER_INSTANCE_CRN,
        "crn:v1:bluemix:public:quantum-computing:us-east:a:instance::");
    set(value, QDMI_DEVICE_SESSION_PARAMETER_BASEURL, "http://127.0.0.1:1");
    set(value, QDMI_DEVICE_SESSION_PARAMETER_AUTHURL,
        "http://127.0.0.1:1/auth");
    return value;
  }
  static void set(IBM_QDMI_Device_Session value,
                  QDMI_Device_Session_Parameter parameter,
                  const std::string& text) {
    ASSERT_EQ(IBM_QDMI_device_session_set_parameter(
                  value, parameter, text.size() + 1, text.c_str()),
              QDMI_SUCCESS);
  }
  void queueInit(int propertiesStatus = 200) {
    http.queue("/auth", {.status = 200, .body = data["auth"].dump()}, true);
    http.queue("/configuration",
               {.status = 200, .body = data["configuration"].dump()});
    http.queue("/properties",
               {.status = propertiesStatus, .body = data["properties"].dump()});
  }
  void initialize() {
    queueInit();
    ASSERT_EQ(IBM_QDMI_device_session_init(session), QDMI_SUCCESS);
  }
  template <class T> std::vector<T> handles(QDMI_Device_Property property) {
    std::size_t size = 0;
    EXPECT_EQ(IBM_QDMI_device_session_query_device_property(session, property,
                                                            0, nullptr, &size),
              QDMI_SUCCESS);
    std::vector<T> values(size / sizeof(T));
    EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                  session, property, size, static_cast<void*>(values.data()),
                  nullptr),
              QDMI_SUCCESS);
    return values;
  }
};

TEST_F(DeviceTest, QueryContractAndDirectedCalibration) {
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_NAME, 0, nullptr, nullptr),
            QDMI_ERROR_BADSTATE);
  initialize();
  EXPECT_EQ(IBM_QDMI_device_session_init(session), QDMI_ERROR_BADSTATE);
  EXPECT_EQ(IBM_QDMI_device_session_set_parameter(
                session, QDMI_DEVICE_SESSION_PARAMETER_TOKEN, 0, nullptr),
            QDMI_ERROR_BADSTATE);
  std::size_t required = 0;
  ASSERT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_NAME, 999, nullptr, &required),
            QDMI_SUCCESS);
  EXPECT_EQ(required, std::string("ibm_test").size() + 1);
  std::vector<char> name(required);
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_NAME, required - 1, name.data(),
                nullptr),
            QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(name.front(), '\0');
  EXPECT_EQ(
      IBM_QDMI_device_session_query_device_property(
          session, QDMI_DEVICE_PROPERTY_NAME, required, name.data(), nullptr),
      QDMI_SUCCESS);
  EXPECT_STREQ(name.data(), "ibm_test");
  const auto sites = handles<IBM_QDMI_Site>(QDMI_DEVICE_PROPERTY_SITES);
  const auto operations =
      handles<IBM_QDMI_Operation>(QDMI_DEVICE_PROPERTY_OPERATIONS);
  ASSERT_EQ(sites.size(), 2);
  ASSERT_EQ(operations.size(), 3);
  EXPECT_EQ(handles<IBM_QDMI_Site>(QDMI_DEVICE_PROPERTY_COUPLINGMAP), sites);
  std::uint64_t value = 0;
  EXPECT_EQ(IBM_QDMI_device_session_query_site_property(
                session, sites[0], QDMI_SITE_PROPERTY_T1, sizeof(value), &value,
                nullptr),
            QDMI_SUCCESS);
  EXPECT_EQ(value, 100500000);
  EXPECT_EQ(IBM_QDMI_device_session_query_site_property(
                session, sites[1], QDMI_SITE_PROPERTY_T1, 0, nullptr, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
  EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                session, operations[2], 2, sites.data(), 0, nullptr,
                QDMI_OPERATION_PROPERTY_DURATION, sizeof(value), &value,
                nullptr),
            QDMI_SUCCESS);
  EXPECT_EQ(value, 35556);
  const std::array reverse{sites[1], sites[0]};
  EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                session, operations[2], 2, reverse.data(), 0, nullptr,
                QDMI_OPERATION_PROPERTY_DURATION, 0, nullptr, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
  EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                session, operations[2], 0, nullptr, 0, nullptr,
                QDMI_OPERATION_PROPERTY_DURATION, 0, nullptr, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
  const auto& requests = http.requests();
  ASSERT_EQ(requests.size(), 3);
  EXPECT_FALSE(requests[0].headers.contains("Authorization"));
  EXPECT_EQ(requests[0].form.at("apikey"), "synthetic-key");
  for (std::size_t i = 1; i < requests.size(); ++i) {
    EXPECT_EQ(requests[i].headers.at("Authorization"),
              "Bearer synthetic-bearer");
    EXPECT_EQ(requests[i].headers.at("IBM-API-Version"), "2026-04-15");
    EXPECT_EQ(requests[i].headers.at("Service-CRN"),
              "crn:v1:bluemix:public:quantum-computing:us-east:a:instance::");
    EXPECT_TRUE(requests[i].body.empty());
  }
}

TEST_F(DeviceTest, StaticPropertiesUseCorrectTypesWithoutRequests) {
  initialize();
  const auto before = http.requests().size();
  for (const auto property :
       {QDMI_DEVICE_PROPERTY_VERSION, QDMI_DEVICE_PROPERTY_LIBRARYVERSION,
        QDMI_DEVICE_PROPERTY_DURATIONUNIT}) {
    std::array<char, 32> value{};
    EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                  session, property, value.size(), value.data(), nullptr),
              QDMI_SUCCESS);
    EXPECT_NE(value.front(), '\0');
  }
  double scale = 0;
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_DURATIONSCALEFACTOR,
                sizeof(scale), &scale, nullptr),
            QDMI_SUCCESS);
  EXPECT_DOUBLE_EQ(scale, 1.0);
  std::size_t qubits = 0;
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_QUBITSNUM, sizeof(qubits),
                &qubits, nullptr),
            QDMI_SUCCESS);
  EXPECT_EQ(qubits, 2);
  QDMI_Program_Format format{};
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_SUPPORTEDPROGRAMFORMATS,
                sizeof(format), &format, nullptr),
            QDMI_SUCCESS);
  EXPECT_EQ(format, QDMI_PROGRAM_FORMAT_QASM3);
  std::size_t calibration = 123;
  std::size_t required = 0;
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_NEEDSCALIBRATION, 0, nullptr,
                &required),
            QDMI_SUCCESS);
  EXPECT_EQ(required, sizeof(calibration));
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_NEEDSCALIBRATION, required - 1,
                &calibration, nullptr),
            QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(calibration, 123);
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_NEEDSCALIBRATION, required,
                &calibration, nullptr),
            QDMI_SUCCESS);
  EXPECT_EQ(calibration, 0);
  QDMI_Device_Pulse_Support_Level pulse = QDMI_DEVICE_PULSE_SUPPORT_LEVEL_SITE;
  EXPECT_EQ(
      IBM_QDMI_device_session_query_device_property(
          session, QDMI_DEVICE_PROPERTY_PULSESUPPORT, 0, nullptr, &required),
      QDMI_SUCCESS);
  EXPECT_EQ(required, sizeof(pulse));
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_PULSESUPPORT, required - 1,
                &pulse, nullptr),
            QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(pulse, QDMI_DEVICE_PULSE_SUPPORT_LEVEL_SITE);
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_PULSESUPPORT, sizeof(pulse),
                &pulse, nullptr),
            QDMI_SUCCESS);
  EXPECT_EQ(pulse, QDMI_DEVICE_PULSE_SUPPORT_LEVEL_NONE);
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_CUSTOM1, 0, nullptr, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
  EXPECT_EQ(http.requests().size(), before);
}

TEST_F(DeviceTest, StatusAndQueueLengthRefreshFromBackend) {
  initialize();
  for (const auto& [body, expected] :
       std::vector<std::pair<nlohmann::json, QDMI_Device_Status>>{
           {{{"state", true}, {"length_queue", 2}}, QDMI_DEVICE_STATUS_BUSY},
           {{{"state", true}, {"length_queue", 0}}, QDMI_DEVICE_STATUS_IDLE},
           {{{"state", false}, {"length_queue", 0}},
            QDMI_DEVICE_STATUS_OFFLINE}}) {
    http.queue("/status", {.status = 200, .body = body.dump()});
    QDMI_Device_Status status{};
    EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                  session, QDMI_DEVICE_PROPERTY_STATUS, sizeof(status), &status,
                  nullptr),
              QDMI_SUCCESS);
    EXPECT_EQ(status, expected);
  }
  http.queue("/status", {.status = 200, .body = R"({"length_queue":4})"});
  std::size_t count = 0;
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_QUEUELENGTH, sizeof(count),
                &count, nullptr),
            QDMI_SUCCESS);
  EXPECT_EQ(count, 4);
  http.queue("/status", {.status = 200, .body = R"({"length_queue":4})"});
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_STATUS, 0, nullptr, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
}

TEST_F(DeviceTest, ForeignHandlesAndCalibrationSnapshots) {
  initialize();
  auto* second = allocate();
  queueInit();
  ASSERT_EQ(IBM_QDMI_device_session_init(second), QDMI_SUCCESS);
  const auto sites = handles<IBM_QDMI_Site>(QDMI_DEVICE_PROPERTY_SITES);
  const auto operations =
      handles<IBM_QDMI_Operation>(QDMI_DEVICE_PROPERTY_OPERATIONS);
  EXPECT_EQ(
      IBM_QDMI_device_session_query_site_property(
          second, sites[0], QDMI_SITE_PROPERTY_INDEX, 0, nullptr, nullptr),
      QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                second, operations[0], 0, nullptr, 0, nullptr,
                QDMI_OPERATION_PROPERTY_NAME, 0, nullptr, nullptr),
            QDMI_ERROR_INVALIDARGUMENT);
  data["properties"] = nlohmann::json::object();
  EXPECT_EQ(IBM_QDMI_device_session_query_site_property(
                session, sites[0], QDMI_SITE_PROPERTY_T1, 0, nullptr, nullptr),
            QDMI_SUCCESS);
  auto* third = allocate();
  queueInit();
  ASSERT_EQ(IBM_QDMI_device_session_init(third), QDMI_SUCCESS);
  session = third;
  const auto thirdSites = handles<IBM_QDMI_Site>(QDMI_DEVICE_PROPERTY_SITES);
  EXPECT_EQ(IBM_QDMI_device_session_query_site_property(third, thirdSites[0],
                                                        QDMI_SITE_PROPERTY_T1,
                                                        0, nullptr, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
}

TEST_F(DeviceTest, InvalidArgumentsDoNotMakeRequests) {
  EXPECT_EQ(IBM_QDMI_device_session_alloc(nullptr), QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(IBM_QDMI_device_session_init(nullptr), QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                nullptr, QDMI_DEVICE_PROPERTY_NAME, 0, nullptr, nullptr),
            QDMI_ERROR_INVALIDARGUMENT);
  for (const auto size : {0U, 1U}) {
    EXPECT_EQ(IBM_QDMI_device_session_set_parameter(
                  session, QDMI_DEVICE_SESSION_PARAMETER_TOKEN, size, "x"),
              QDMI_ERROR_INVALIDARGUMENT);
  }
  EXPECT_EQ(IBM_QDMI_device_session_set_parameter(
                session, QDMI_DEVICE_SESSION_PARAMETER_TOKEN, 4, "a\0b"),
            QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(IBM_QDMI_device_session_set_parameter(
                session, QDMI_DEVICE_SESSION_PARAMETER_MAX, 0, nullptr),
            QDMI_ERROR_INVALIDARGUMENT);
  set(session, QDMI_DEVICE_SESSION_PARAMETER_TOKEN, "");
  EXPECT_EQ(IBM_QDMI_device_session_init(session), QDMI_ERROR_PERMISSIONDENIED);
  EXPECT_TRUE(http.requests().empty());
}

TEST_F(DeviceTest, MissingCalibrationStillInitializes) {
  queueInit(404);
  ASSERT_EQ(IBM_QDMI_device_session_init(session), QDMI_SUCCESS);
  const auto sites = handles<IBM_QDMI_Site>(QDMI_DEVICE_PROPERTY_SITES);
  EXPECT_EQ(IBM_QDMI_device_session_query_site_property(
                session, sites[0], QDMI_SITE_PROPERTY_T1, 0, nullptr, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
}

TEST_F(DeviceTest, InitializationContainsExceptionsAndAllowsRecovery) {
  for (const auto& body : {std::string("not json"),
                           std::string(R"({"backend_name":"ibm_test"})")}) {
    http.queue("/auth", {.status = 200, .body = data["auth"].dump()}, true);
    http.queue("/configuration", {.status = 200, .body = body});
    if (body.front() == '{') {
      http.queue("/properties",
                 {.status = 200, .body = data["properties"].dump()});
    }
    EXPECT_EQ(IBM_QDMI_device_session_init(session), QDMI_ERROR_FATAL);
  }
  const auto transport = ibm::internal::hooks().transport;
  ibm::internal::hooks().transport = [](const auto&) -> ibm::Response {
    throw std::bad_alloc{};
  };
  EXPECT_EQ(IBM_QDMI_device_session_init(session), QDMI_ERROR_OUTOFMEM);
  ibm::internal::hooks().transport = [](const auto&) -> ibm::Response {
    throw std::runtime_error("synthetic");
  };
  EXPECT_EQ(IBM_QDMI_device_session_init(session), QDMI_ERROR_FATAL);
  ibm::internal::hooks().transport = transport;
  initialize();
}

TEST_F(DeviceTest, AuthenticationAndBackendErrorsRemainConfigurable) {
  for (const auto& [status, expected] :
       std::vector<std::pair<int, int>>{{401, QDMI_ERROR_PERMISSIONDENIED},
                                        {403, QDMI_ERROR_PERMISSIONDENIED},
                                        {404, QDMI_ERROR_NOTFOUND},
                                        {429, QDMI_ERROR_FATAL},
                                        {500, QDMI_ERROR_FATAL},
                                        {302, QDMI_ERROR_FATAL}}) {
    http.queue("/auth", {.status = 200, .body = data["auth"].dump()}, true);
    http.queue("/configuration", {.status = status, .body = "{}"});
    if (status == 401) {
      http.queue("/auth", {.status = 200, .body = data["auth"].dump()}, true);
      http.queue("/configuration", {.status = status, .body = "{}"});
    }
    EXPECT_EQ(IBM_QDMI_device_session_init(session), expected);
    EXPECT_EQ(IBM_QDMI_device_session_set_parameter(
                  session, QDMI_DEVICE_SESSION_PARAMETER_TOKEN, 0, nullptr),
              QDMI_SUCCESS);
  }
  for (const auto status : {400, 403}) {
    http.queue("/auth", {.status = status, .body = "{}"}, true);
    EXPECT_EQ(IBM_QDMI_device_session_init(session),
              QDMI_ERROR_PERMISSIONDENIED);
  }
  initialize();
}

TEST_F(DeviceTest, MalformedAuthenticationStopsBeforeBackendRequests) {
  for (const auto& body :
       {std::string("not json"), std::string("{}"),
        std::string(R"({"access_token":"x","expires_in":"bad"})")}) {
    const auto before = http.requests().size();
    http.queue("/auth", {.status = 200, .body = body}, true);
    EXPECT_EQ(IBM_QDMI_device_session_init(session), QDMI_ERROR_FATAL);
    EXPECT_EQ(http.requests().size(), before + 1);
  }
}

TEST_F(DeviceTest, OperationAndSitePropertiesValidateBuffersAndParameters) {
  initialize();
  const auto sites = handles<IBM_QDMI_Site>(QDMI_DEVICE_PROPERTY_SITES);
  const auto operations =
      handles<IBM_QDMI_Operation>(QDMI_DEVICE_PROPERTY_OPERATIONS);
  std::size_t index = 99;
  EXPECT_EQ(IBM_QDMI_device_session_query_site_property(
                session, sites[1], QDMI_SITE_PROPERTY_INDEX, sizeof(index),
                &index, nullptr),
            QDMI_SUCCESS);
  EXPECT_EQ(index, 1);
  std::uint64_t t2 = 0;
  EXPECT_EQ(
      IBM_QDMI_device_session_query_site_property(
          session, sites[0], QDMI_SITE_PROPERTY_T2, sizeof(t2), &t2, nullptr),
      QDMI_SUCCESS);
  EXPECT_EQ(t2, 200000000);
  EXPECT_EQ(
      IBM_QDMI_device_session_query_site_property(
          session, sites[0], QDMI_SITE_PROPERTY_CUSTOM1, 0, nullptr, nullptr),
      QDMI_ERROR_NOTSUPPORTED);
  for (const auto property : {QDMI_OPERATION_PROPERTY_QUBITSNUM,
                              QDMI_OPERATION_PROPERTY_PARAMETERSNUM}) {
    std::size_t value = 0;
    EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                  session, operations[1], 0, nullptr, 0, nullptr, property,
                  sizeof(value), &value, nullptr),
              QDMI_SUCCESS);
    EXPECT_EQ(value, 1);
  }
  std::array<char, 8> name{};
  EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                session, operations[1], 0, nullptr, 0, nullptr,
                QDMI_OPERATION_PROPERTY_NAME, name.size(), name.data(),
                nullptr),
            QDMI_SUCCESS);
  EXPECT_STREQ(name.data(), "rz");
  std::array<IBM_QDMI_Site, 2> supported{};
  EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                session, operations[1], 0, nullptr, 0, nullptr,
                QDMI_OPERATION_PROPERTY_SITES, sizeof(supported),
                static_cast<void*>(supported.data()), nullptr),
            QDMI_SUCCESS);
  EXPECT_EQ((std::vector<IBM_QDMI_Site>{supported.begin(), supported.end()}),
            sites);
  double fidelity = 0;
  EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                session, operations[2], 2, sites.data(), 0, nullptr,
                QDMI_OPERATION_PROPERTY_FIDELITY, sizeof(fidelity), &fidelity,
                nullptr),
            QDMI_SUCCESS);
  EXPECT_DOUBLE_EQ(fidelity, 0.98);
  double parameter = 0.5;
  EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                session, operations[1], 1, sites.data(), 1, &parameter,
                QDMI_OPERATION_PROPERTY_NAME, 0, nullptr, nullptr),
            QDMI_SUCCESS);
  parameter = std::numeric_limits<double>::infinity();
  EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                session, operations[1], 1, sites.data(), 1, &parameter,
                QDMI_OPERATION_PROPERTY_NAME, 0, nullptr, nullptr),
            QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                session, operations[0], 1, sites.data(), 1, &parameter,
                QDMI_OPERATION_PROPERTY_NAME, 0, nullptr, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
  EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                session, operations[0], 0, nullptr, 0, nullptr,
                QDMI_OPERATION_PROPERTY_CUSTOM1, 0, nullptr, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
}

class DeviceJobMockTest : public DeviceTest {
protected:
  IBM_QDMI_Device_Job job = nullptr;
  void SetUp() override {
    DeviceTest::SetUp();
    initialize();
    ASSERT_EQ(IBM_QDMI_device_session_create_device_job(session, &job),
              QDMI_SUCCESS);
    jobs.push_back(job);
  }
  void configure() {
    const auto format = QDMI_PROGRAM_FORMAT_QASM3;
    const std::size_t shots = 3;
    ASSERT_EQ(IBM_QDMI_device_job_set_parameter(
                  job, QDMI_DEVICE_JOB_PARAMETER_PROGRAMFORMAT, sizeof(format),
                  &format),
              QDMI_SUCCESS);
    ASSERT_EQ(IBM_QDMI_device_job_set_parameter(
                  job, QDMI_DEVICE_JOB_PARAMETER_PROGRAM, PROGRAM.size() + 1,
                  PROGRAM.c_str()),
              QDMI_SUCCESS);
    ASSERT_EQ(
        IBM_QDMI_device_job_set_parameter(
            job, QDMI_DEVICE_JOB_PARAMETER_SHOTSNUM, sizeof(shots), &shots),
        QDMI_SUCCESS);
  }
  void submit() {
    http.queue("/jobs",
               {.status = 200,
                .body = R"({"id":"synthetic-job","backend":"ibm_test"})"},
               true);
    ASSERT_EQ(IBM_QDMI_device_job_submit(job), QDMI_SUCCESS);
  }
  void queueStatus(const std::string& status) {
    http.queue("/synthetic-job",
               {.status = 200,
                .body =
                    nlohmann::json{
                        {"id", "synthetic-job"},
                        {"backend", "ibm_test"},
                        {"program", {{"id", "sampler"}}},
                        {"state", {{"status", status}}},
                        {"params",
                         {{"version", 2},
                          {"support_qiskit", false},
                          {"pubs", nlohmann::json::array({nlohmann::json::array(
                                       {PROGRAM, nullptr, 3})})}}}}
                        .dump()});
  }
};

TEST_F(DeviceJobMockTest, LifecycleResultsAndRetrievalPreserveRegisterOrder) {
  configure();
  submit();
  EXPECT_EQ(IBM_QDMI_device_job_submit(job), QDMI_ERROR_BADSTATE);
  queueStatus("Completed");
  EXPECT_EQ(IBM_QDMI_device_job_wait(job, 1), QDMI_SUCCESS);
  http.queue("/results", {.status = 200, .body = R"({"results":[{"data":{
      "z":{"num_bits":2,"samples":["0x1","0x0","0x1"]},
      "a":{"num_bits":1,"samples":["0x1","0x0","0x1"]}}}]})"});
  std::size_t required = 0;
  EXPECT_EQ(IBM_QDMI_device_job_get_results(job, QDMI_JOB_RESULT_SHOTS, 0,
                                            nullptr, &required),
            QDMI_SUCCESS);
  EXPECT_EQ(required, 12);
  std::array<char, 32> text{};
  EXPECT_EQ(IBM_QDMI_device_job_get_results(job, QDMI_JOB_RESULT_SHOTS, 1,
                                            text.data(), nullptr),
            QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(IBM_QDMI_device_job_get_results(job, QDMI_JOB_RESULT_SHOTS,
                                            text.size(), text.data(), nullptr),
            QDMI_SUCCESS);
  EXPECT_STREQ(text.data(), "101,000,101");
  EXPECT_EQ(IBM_QDMI_device_job_get_results(job, QDMI_JOB_RESULT_HIST_KEYS,
                                            text.size(), text.data(), nullptr),
            QDMI_SUCCESS);
  EXPECT_STREQ(text.data(), "000,101");
  std::array<std::size_t, 2> counts{};
  EXPECT_EQ(IBM_QDMI_device_job_get_results(job, QDMI_JOB_RESULT_HIST_VALUES,
                                            sizeof(counts), counts.data(),
                                            nullptr),
            QDMI_SUCCESS);
  EXPECT_EQ(counts, (std::array<std::size_t, 2>{1, 2}));
  EXPECT_EQ(IBM_QDMI_device_job_get_results(
                job, QDMI_JOB_RESULT_STATEVECTOR_DENSE, 0, nullptr, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
  EXPECT_EQ(std::ranges::count_if(http.requests(),
                                  [](const auto& request) {
                                    return request.url.ends_with("/results");
                                  }),
            1);
  const auto submitted = nlohmann::json::parse(http.requests()[3].body);
  EXPECT_EQ(submitted["cost"], 60);
  EXPECT_EQ(submitted["params"]["pubs"][0],
            nlohmann::json::array({PROGRAM, nullptr, 3}));
  queueStatus("Completed");
  IBM_QDMI_Device_Job retrieved = nullptr;
  ASSERT_EQ(IBM_QDMI_device_session_retrieve_device_job_by_id(
                session, "synthetic-job", &retrieved),
            QDMI_SUCCESS);
  jobs.push_back(retrieved);
  EXPECT_EQ(IBM_QDMI_device_job_submit(retrieved), QDMI_ERROR_BADSTATE);
}

TEST_F(DeviceJobMockTest, JobRetainsSessionAndFreeNeverCancels) {
  configure();
  IBM_QDMI_device_session_free(session);
  EXPECT_EQ(IBM_QDMI_device_session_init(session), QDMI_ERROR_INVALIDARGUMENT);
  submit();
  queueStatus("Completed");
  EXPECT_EQ(IBM_QDMI_device_job_wait(job, 1), QDMI_SUCCESS);
  EXPECT_EQ(IBM_QDMI_device_finalize(), QDMI_ERROR_FATAL);
  EXPECT_EQ(IBM_QDMI_device_job_check(job, nullptr),
            QDMI_ERROR_INVALIDARGUMENT);
  IBM_QDMI_device_job_free(job);
  EXPECT_EQ(IBM_QDMI_device_job_submit(job), QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_FALSE(std::ranges::any_of(http.requests(), [](const auto& request) {
    return request.url.ends_with("/cancel");
  }));
}

TEST_F(DeviceJobMockTest, ParameterAndPropertyContracts) {
  EXPECT_EQ(IBM_QDMI_device_job_query_property(job, QDMI_DEVICE_JOB_PROPERTY_ID,
                                               0, nullptr, nullptr),
            QDMI_ERROR_BADSTATE);
  EXPECT_EQ(IBM_QDMI_device_job_query_property(
                job, QDMI_DEVICE_JOB_PROPERTY_PROGRAM, 0, nullptr, nullptr),
            QDMI_ERROR_BADSTATE);
  EXPECT_EQ(
      IBM_QDMI_device_job_query_property(
          job, QDMI_DEVICE_JOB_PROPERTY_PROGRAMFORMAT, 0, nullptr, nullptr),
      QDMI_ERROR_BADSTATE);
  const std::size_t one = 1;
  for (const auto parameter :
       {QDMI_DEVICE_JOB_PARAMETER_PROGRAMFORMAT,
        QDMI_DEVICE_JOB_PARAMETER_PROGRAM, QDMI_DEVICE_JOB_PARAMETER_SHOTSNUM,
        IBM_QDMI_DEVICE_JOB_PARAMETER_MAX_EXECUTION_TIME,
        IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING}) {
    EXPECT_EQ(IBM_QDMI_device_job_set_parameter(job, parameter, 0, &one),
              QDMI_ERROR_INVALIDARGUMENT);
    EXPECT_EQ(IBM_QDMI_device_job_set_parameter(job, parameter, 0, nullptr),
              QDMI_SUCCESS);
  }
  EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                job, QDMI_DEVICE_JOB_PARAMETER_CUSTOM3, 0, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
  for (const std::uint64_t seconds : {0U, 10801U}) {
    EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                  job, IBM_QDMI_DEVICE_JOB_PARAMETER_MAX_EXECUTION_TIME,
                  sizeof(seconds), &seconds),
              QDMI_ERROR_INVALIDARGUMENT);
  }
  const std::uint64_t seconds = 42;
  EXPECT_EQ(
      IBM_QDMI_device_job_set_parameter(
          job, IBM_QDMI_DEVICE_JOB_PARAMETER_MAX_EXECUTION_TIME, 1, &seconds),
      QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                job, IBM_QDMI_DEVICE_JOB_PARAMETER_MAX_EXECUTION_TIME,
                sizeof(seconds), &seconds),
            QDMI_SUCCESS);
  const std::size_t zero = 0;
  EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                job, QDMI_DEVICE_JOB_PARAMETER_SHOTSNUM, sizeof(zero), &zero),
            QDMI_ERROR_INVALIDARGUMENT);
  const auto unsupported = QDMI_PROGRAM_FORMAT_QASM2;
  EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                job, QDMI_DEVICE_JOB_PARAMETER_PROGRAMFORMAT,
                sizeof(unsupported), &unsupported),
            QDMI_ERROR_NOTSUPPORTED);
  configure();
  EXPECT_EQ(IBM_QDMI_device_job_set_parameter(job,
                                              QDMI_DEVICE_JOB_PARAMETER_PROGRAM,
                                              PROGRAM.size(), PROGRAM.c_str()),
            QDMI_ERROR_INVALIDARGUMENT);
  for (const auto property :
       {QDMI_DEVICE_JOB_PROPERTY_PROGRAMFORMAT,
        QDMI_DEVICE_JOB_PROPERTY_PROGRAM, QDMI_DEVICE_JOB_PROPERTY_SHOTSNUM}) {
    std::size_t size = 0;
    EXPECT_EQ(
        IBM_QDMI_device_job_query_property(job, property, 0, nullptr, &size),
        QDMI_SUCCESS);
    EXPECT_GT(size, 0);
  }
  submit();
  EXPECT_EQ(nlohmann::json::parse(http.requests().back().body)["cost"], 42);
  std::array<char, 32> id{};
  EXPECT_EQ(IBM_QDMI_device_job_query_property(job, QDMI_DEVICE_JOB_PROPERTY_ID,
                                               id.size(), id.data(), nullptr),
            QDMI_SUCCESS);
  EXPECT_STREQ(id.data(), "synthetic-job");
  EXPECT_EQ(IBM_QDMI_device_job_query_property(
                job, QDMI_DEVICE_JOB_PROPERTY_CUSTOM1, 0, nullptr, nullptr),
            QDMI_ERROR_NOTSUPPORTED);
}

TEST_F(DeviceJobMockTest, WaitAdvancesClockWithoutImplicitCancellation) {
  configure();
  EXPECT_EQ(IBM_QDMI_device_job_wait(job, 1), QDMI_ERROR_BADSTATE);
  submit();
  queueStatus("Queued");
  const auto started = http.now();
  EXPECT_EQ(IBM_QDMI_device_job_wait(job, 1), QDMI_ERROR_TIMEOUT);
  EXPECT_EQ(http.now() - started, std::chrono::seconds{1});
  EXPECT_FALSE(std::ranges::any_of(http.requests(), [](const auto& request) {
    return request.url.ends_with("/cancel");
  }));
  http.queue("/cancel", {.status = 204, .body = ""}, true);
  EXPECT_EQ(IBM_QDMI_device_job_cancel(job), QDMI_SUCCESS);
  EXPECT_EQ(IBM_QDMI_device_job_wait(job, 1), QDMI_SUCCESS);
  EXPECT_EQ(IBM_QDMI_device_job_get_results(job, QDMI_JOB_RESULT_SHOTS, 0,
                                            nullptr, nullptr),
            QDMI_ERROR_INVALIDARGUMENT);
}

TEST_F(DeviceJobMockTest, SubmissionFailureAndTimeoutNeverRetry) {
  configure();
  http.queue("/jobs", {.status = 0, .body = "", .timedOut = true}, true);
  const auto before = http.requests().size();
  EXPECT_EQ(IBM_QDMI_device_job_submit(job), QDMI_ERROR_TIMEOUT);
  EXPECT_EQ(IBM_QDMI_device_job_submit(job), QDMI_ERROR_BADSTATE);
  EXPECT_EQ(IBM_QDMI_device_job_wait(job, 1), QDMI_ERROR_FATAL);
  EXPECT_EQ(http.requests().size(), before + 1);
}

TEST_F(DeviceTest, FaultyOperationSitesRespectBooleanAndIntegerFlags) {
  const auto original = data;
  for (const auto* kind : {"qubit", "gate"}) {
    for (const auto& flag : {nlohmann::json(0), nlohmann::json(false),
                             nlohmann::json(1), nlohmann::json(true)}) {
      data = original;
      session = allocate();
      const nlohmann::json parameter = {
          {"name", "operational"}, {"value", flag}, {"unit", ""}};
      const bool qubit = std::string(kind) == "qubit";
      if (qubit) {
        data["properties"]["qubits"][0].push_back(parameter);
      } else {
        data["properties"]["gates"][0]["parameters"].push_back(parameter);
      }
      initialize();
      const auto sites = handles<IBM_QDMI_Site>(QDMI_DEVICE_PROPERTY_SITES);
      const auto operations =
          handles<IBM_QDMI_Operation>(QDMI_DEVICE_PROPERTY_OPERATIONS);
      const bool enabled = flag == true || flag == 1;
      for (const auto property : {QDMI_OPERATION_PROPERTY_DURATION,
                                  QDMI_OPERATION_PROPERTY_FIDELITY}) {
        EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                      session, operations[2], 2, sites.data(), 0, nullptr,
                      property, 0, nullptr, nullptr),
                  enabled ? QDMI_SUCCESS : QDMI_ERROR_NOTSUPPORTED);
      }
      EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                    session, operations[2], 0, nullptr, 0, nullptr,
                    QDMI_OPERATION_PROPERTY_SITES, 0, nullptr, nullptr),
                enabled ? QDMI_SUCCESS : QDMI_ERROR_NOTSUPPORTED);
      std::array<IBM_QDMI_Site, 2> supported{};
      std::size_t required = 0;
      EXPECT_EQ(IBM_QDMI_device_session_query_operation_property(
                    session, operations[0], 0, nullptr, 0, nullptr,
                    QDMI_OPERATION_PROPERTY_SITES, sizeof(supported),
                    static_cast<void*>(supported.data()), &required),
                QDMI_SUCCESS);
      EXPECT_EQ(required, (qubit && !enabled ? 1 : 2) * sizeof(IBM_QDMI_Site));
      EXPECT_EQ(supported[0], sites[qubit && !enabled ? 1 : 0]);
    }
  }
}

TEST_F(DeviceTest, RequestTimeoutRejectsInvalidUpdates) {
  set(session, IBM_QDMI_DEVICE_SESSION_PARAMETER_REQUEST_TIMEOUT, "2147483647");
  for (const std::string text :
       {"", "0", "-1", "+1", " 1", "1ms", "2147483648"}) {
    EXPECT_EQ(IBM_QDMI_device_session_set_parameter(
                  session, IBM_QDMI_DEVICE_SESSION_PARAMETER_REQUEST_TIMEOUT,
                  text.size() + 1, text.c_str()),
              QDMI_ERROR_INVALIDARGUMENT);
  }
  EXPECT_EQ(IBM_QDMI_device_session_set_parameter(
                session, IBM_QDMI_DEVICE_SESSION_PARAMETER_REQUEST_TIMEOUT, 0,
                nullptr),
            QDMI_SUCCESS);
  initialize();
  EXPECT_EQ(http.requests().front().timeout,
            std::chrono::milliseconds{2147483647});
  EXPECT_EQ(IBM_QDMI_device_session_set_parameter(
                session, IBM_QDMI_DEVICE_SESSION_PARAMETER_REQUEST_TIMEOUT, 0,
                nullptr),
            QDMI_ERROR_BADSTATE);
}

TEST_F(DeviceJobMockTest, DynamicalDecouplingReplacesOptionsWithoutSubmission) {
  configure();
  const std::string initial =
      R"({"enable":true,"sequence_type":"XpXm","skip_reset_qubits":true})";
  const auto before = http.requests().size();
  for (const auto& options :
       {nlohmann::json::object(), nlohmann::json{{"enable", true}},
        nlohmann::json{{"enable", false}, {"sequence_type", "XY4"}}}) {
    IBM_QDMI_Device_Job next = nullptr;
    ASSERT_EQ(IBM_QDMI_device_session_create_device_job(session, &next),
              QDMI_SUCCESS);
    jobs.push_back(next);
    job = next;
    configure();
    EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                  job, IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING,
                  initial.size() + 1, initial.c_str()),
              QDMI_SUCCESS);
    const auto encoded = options.dump();
    EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                  job, IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING,
                  encoded.size() + 1, encoded.c_str()),
              QDMI_SUCCESS);
    EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                  job, IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING, 0,
                  nullptr),
              QDMI_SUCCESS);
    submit();
    EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                  job, IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING,
                  encoded.size() + 1, encoded.c_str()),
              QDMI_ERROR_BADSTATE);
    EXPECT_EQ(IBM_QDMI_device_job_submit(job), QDMI_ERROR_BADSTATE);
    nlohmann::json expected = {{"enable", false},
                               {"sequence_type", "XX"},
                               {"extra_slack_distribution", "middle"},
                               {"scheduling_method", "alap"},
                               {"skip_reset_qubits", false}};
    expected.update(options);
    const auto payload = nlohmann::json::parse(http.requests().back().body);
    EXPECT_EQ(payload["params"]["options"]["dynamical_decoupling"], expected);
    EXPECT_EQ(
        payload["params"]["options"]["twirling"],
        (nlohmann::json{{"enable_gates", false}, {"enable_measure", false}}));
    EXPECT_EQ(payload["cost"], 60);
  }
  EXPECT_EQ(http.requests().size(), before + 3);
}

TEST_F(DeviceJobMockTest, InvalidDynamicalDecouplingPreservesLastValidOptions) {
  configure();
  const std::string options = R"({"enable":true,"sequence_type":"XY4"})";
  EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                job, IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING,
                options.size() + 1, options.c_str()),
            QDMI_SUCCESS);
  const auto before = http.requests().size();
  for (const std::string invalid :
       {"{", "[]", "null", R"({"unknown":true})", R"({"enable":1})",
        R"({"sequence_type":"ZZ"})"}) {
    EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                  job, IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING,
                  invalid.size() + 1, invalid.c_str()),
              QDMI_ERROR_INVALIDARGUMENT);
  }
  for (const auto size : {std::size_t{0}, options.size()}) {
    EXPECT_EQ(IBM_QDMI_device_job_set_parameter(
                  job, IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING, size,
                  options.c_str()),
              QDMI_ERROR_INVALIDARGUMENT);
  }
  EXPECT_EQ(
      IBM_QDMI_device_job_set_parameter(
          job, IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING, 6, "{}\0{}"),
      QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(http.requests().size(), before);
  submit();
  const auto sent = nlohmann::json::parse(
      http.requests().back().body)["params"]["options"]["dynamical_decoupling"];
  EXPECT_EQ(sent["enable"], true);
  EXPECT_EQ(sent["sequence_type"], "XY4");
}
} // namespace
