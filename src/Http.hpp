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

#include <chrono>
#include <cstdint>
#include <functional>
#include <ibm-qdmi-device/diagnostics.h>
#include <map>
#include <optional>
#include <span>
#include <string>

namespace ibm {
struct Request {
  std::string url;
  std::map<std::string, std::string> headers;
  std::map<std::string, std::string> form;
  bool post = false;
  std::string body;
  std::chrono::milliseconds timeout{30000};
};
struct Response {
  std::int32_t status = 0;
  std::string body;
  bool timedOut = false;
  bool failed = false;
  bool transient = false;
  std::optional<std::chrono::milliseconds> retryAfter;
};
using Transport = std::function<Response(const Request&)>;
/// Validate an HTTPS endpoint, or an HTTP loopback endpoint for offline tests.
bool validEndpoint(const std::string& url);
Response send(const Request& request);
namespace internal {
/// Return the first readable CA bundle, or empty to keep platform defaults.
std::string findCaBundle(std::span<const char* const> candidates);
/// Prefer CURL_CA_BUNDLE, then SSL_CERT_FILE, then a readable Linux CA bundle.
/// Preserve invalid explicit paths so TLS fails; empty keeps platform defaults.
std::string resolveCaBundle();
std::optional<std::chrono::milliseconds>
parseRetryAfter(const std::string& value);
/// Internal dependencies shared by the device and hermetic native tests.
struct Hooks {
  Transport transport = send;
  std::function<std::chrono::steady_clock::time_point()> now =
      std::chrono::steady_clock::now;
  std::function<void(std::chrono::steady_clock::time_point)> sleepUntil;
};
/// Replace hooks only while no device calls are running; restore after testing.
Hooks& hooks();
} // namespace internal
/// An internal status-only exception; never carries server text or credentials.
struct Failure {
  explicit Failure(int result,
                   IBM_QDMI_Diagnostic reason = IBM_QDMI_DIAGNOSTIC_NONE)
      : status(result), diagnostic(reason) {}
  int status;
  IBM_QDMI_Diagnostic diagnostic;
};
void checkResponse(const Response& response);
} // namespace ibm
