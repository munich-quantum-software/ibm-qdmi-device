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

#include "http_stub.hpp"

#include "Http.hpp"

#include <chrono>
#include <gtest/gtest.h>
#include <utility>
#include <vector>

namespace ibm::test_support {
HttpStub::HttpStub() : previous(internal::hooks()) {
  internal::hooks() = {
      .transport =
          [this](const Request& request) {
            recorded.push_back(request);
            if (pending.empty()) {
              ADD_FAILURE() << "Unexpected request: " << request.url;
              return Response{.status = 500, .body = {}};
            }
            auto expected = std::move(pending.front());
            pending.pop_front();
            EXPECT_TRUE(request.url.ends_with(expected.path)) << request.url;
            EXPECT_EQ(request.post || !request.form.empty(), expected.post);
            return expected.response;
          },
      .now = [this] { return time; },
      .sleepUntil = [this](auto deadline) { time = deadline; }};
}
HttpStub::~HttpStub() {
  internal::hooks() = std::move(previous);
  EXPECT_TRUE(pending.empty()) << "Scripted requests were not made";
}
void HttpStub::queue(std::string path, Response response, bool post) {
  pending.push_back(
      {.path = std::move(path), .response = std::move(response), .post = post});
}
const std::vector<Request>& HttpStub::requests() const { return recorded; }
std::chrono::steady_clock::time_point HttpStub::now() const { return time; }
} // namespace ibm::test_support
