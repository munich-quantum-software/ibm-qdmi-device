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

#include <cstdint>
#include <functional>
#include <map>
#include <string>

namespace ibm {
struct Request {
  std::string url;
  std::map<std::string, std::string> headers;
  // A nonempty form selects POST; backend requests always use GET.
  std::map<std::string, std::string> form;
};
struct Response {
  std::int32_t status = 0;
  std::string body;
  bool timedOut = false;
  bool failed = false;
};
using Transport = std::function<Response(const Request&)>;
/// Validate an HTTPS endpoint, or an HTTP loopback endpoint for offline tests.
bool validEndpoint(const std::string& url);
Response send(const Request& request);
/// An internal status-only exception; never carries server text or credentials.
struct Failure {
  int status;
};
void checkResponse(const Response& response);
} // namespace ibm
