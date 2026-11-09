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

#include "Http.hpp"
#include "device_fixture.hpp"

#include <gtest/gtest.h>
#include <nlohmann/json.hpp>

class QDMIQueryFixture : public DeviceTest {
protected:
  void SetUp() override {
    DeviceTest::SetUp();
    ASSERT_FALSE(HasFatalFailure());
    // Auth captures the transport when the session initializes.
    const auto transport = ibm::internal::hooks().transport;
    ibm::internal::hooks().transport = [status = data["status"].dump(),
                                        transport](
                                           const ibm::Request& request) {
      if (request.url.ends_with("/status")) {
        EXPECT_FALSE(request.post);
        EXPECT_TRUE(request.form.empty());
        return ibm::Response{.status = 200, .body = status, .retryAfter = {}};
      }
      return transport(request);
    };
    initialize();
  }
};
