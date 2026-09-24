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

#include <cstdint>
#include <gtest/gtest.h>
#include <ibm_qdmi/constants.h>
#include <utility>
#include <vector>

namespace {
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
