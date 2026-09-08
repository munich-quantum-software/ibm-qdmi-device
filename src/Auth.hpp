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
#include <functional>
#include <mutex>
#include <string>

namespace ibm {
using Clock = std::function<std::chrono::steady_clock::time_point()>;
struct Configuration {
  std::string apiKey;
  std::string backend;
  std::string crn;
  std::string baseUrl;
  std::string authUrl = "https://iam.cloud.ibm.com/identity/token";
};
/// Resolve and validate a copy; unsuccessful initialization does not mutate
/// inputs.
Configuration resolve(Configuration configuration);
class Auth {
public:
  explicit Auth(Configuration configuration, Transport transport = send,
                Clock clock = std::chrono::steady_clock::now);
  std::string get(const std::string& resource);

private:
  void refresh();
  Configuration configuration;
  Transport transport;
  Clock clock;
  std::string bearer;
  std::chrono::steady_clock::time_point expires;
  std::mutex mutex;
};
} // namespace ibm
