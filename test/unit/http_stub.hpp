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

#include <chrono>
#include <deque>
#include <string>
#include <vector>

namespace ibm::test_support {
/// Script requests without sockets and advance time without sleeping.
class HttpStub {
public:
  HttpStub();
  ~HttpStub();
  HttpStub(const HttpStub&) = delete;
  HttpStub& operator=(const HttpStub&) = delete;
  void queue(std::string path, Response response, bool post = false);
  [[nodiscard]] const std::vector<Request>& requests() const;
  [[nodiscard]] std::chrono::steady_clock::time_point now() const;

private:
  struct Expected {
    std::string path;
    Response response;
    bool post;
  };
  internal::Hooks previous;
  std::deque<Expected> pending;
  std::vector<Request> recorded;
  std::chrono::steady_clock::time_point time = std::chrono::steady_clock::now();
};
} // namespace ibm::test_support
