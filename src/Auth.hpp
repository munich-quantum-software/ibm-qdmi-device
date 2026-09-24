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

#include <atomic>
#include <chrono>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>

namespace ibm {
using Clock = std::function<std::chrono::steady_clock::time_point()>;
using Deadline = std::chrono::steady_clock::time_point;
struct Configuration {
  std::string apiKey;
  std::string backend;
  std::string crn;
  std::string baseUrl;
  std::string authUrl = "https://iam.cloud.ibm.com/identity/token";
  std::optional<std::string> authFile;
  std::chrono::milliseconds requestTimeout{30000};
  bool apiKeyConfigured = false;
  bool backendConfigured = false;
  bool crnConfigured = false;
};
/// Resolve and validate a copy; unsuccessful initialization does not mutate
/// inputs.
Configuration resolve(Configuration configuration);
/// Parse positive decimal milliseconds within the portable transport limit.
std::chrono::milliseconds parseRequestTimeout(std::string_view value);
class Auth {
public:
  explicit Auth(Configuration configuration,
                Transport transport = internal::hooks().transport,
                Clock clock = internal::hooks().now);
  std::string get(const std::string& resource,
                  Deadline deadline = Deadline::max());
  /// GET may refresh and retry once after 401. POST is sent at most once.
  Response request(const std::string& resource, bool post = false,
                   const std::string& body = {},
                   Deadline deadline = Deadline::max());

private:
  struct Token {
    std::string bearer;
    Deadline expires;
    std::atomic<bool> valid{true};
  };
  std::shared_ptr<Token> acquireToken(Deadline deadline);
  std::shared_ptr<Token> refresh(Deadline deadline);
  [[nodiscard]] std::chrono::milliseconds remaining(Deadline deadline) const;
  Configuration configuration;
  Transport transport;
  Clock clock;
  std::shared_ptr<Token> cachedToken;
  std::timed_mutex mutex;
};
} // namespace ibm
