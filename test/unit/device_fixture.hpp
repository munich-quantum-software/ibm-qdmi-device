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

#pragma once

#include "http_stub.hpp"

#include <cstddef>
#include <fstream>
#include <gtest/gtest.h>
#include <ibm-qdmi-device/constants.h>
#include <ibm_qdmi/device.h>
#include <nlohmann/json.hpp>
#include <nlohmann/json_fwd.hpp>
#include <string>
#include <vector>

class DeviceTest : public testing::Test {
protected:
  ibm::test_support::HttpStub http;
  nlohmann::json data;
  IBM_QDMI_Device_Session session = nullptr;
  std::vector<IBM_QDMI_Device_Session> sessions;
  std::vector<IBM_QDMI_Device_Job> jobs;
  static void SetUpTestSuite() {
    ASSERT_EQ(IBM_QDMI_device_initialize(), QDMI_SUCCESS);
  }
  static void TearDownTestSuite() {
    EXPECT_EQ(IBM_QDMI_device_finalize(), QDMI_SUCCESS);
  }
  void SetUp() override {
    std::ifstream input(IBM_QDMI_FIXTURE_FILE);
    data = nlohmann::json::parse(input);
    session = allocate();
  }
  void TearDown() override {
    for (auto* job : jobs) {
      IBM_QDMI_device_job_free(job);
    }
    for (auto* owned : sessions) {
      IBM_QDMI_device_session_free(owned);
    }
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
