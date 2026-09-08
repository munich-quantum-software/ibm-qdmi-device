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

#include "Auth.hpp"

#include "Http.hpp"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <ibm_qdmi/constants.h>
#include <mutex>
#include <nlohmann/json.hpp>
#include <nlohmann/json_fwd.hpp>
#include <string>
#include <utility>
#include <vector>

namespace ibm {
Configuration resolve(Configuration configuration) {
  if (configuration.apiKey.empty()) {
    throw Failure{QDMI_ERROR_PERMISSIONDENIED};
  }
  if (configuration.backend.empty() || configuration.crn.empty() ||
      !std::ranges::all_of(configuration.backend,
                           [](unsigned char value) {
                             return std::isalnum(value) != 0 || value == '_';
                           }) ||
      configuration.crn.find_first_of("\r\n") != std::string::npos) {
    throw Failure{QDMI_ERROR_INVALIDARGUMENT};
  }
  std::vector<std::string> parts;
  std::size_t start = 0;
  for (auto end = configuration.crn.find(':'); end != std::string::npos;
       end = configuration.crn.find(':', start)) {
    parts.push_back(configuration.crn.substr(start, end - start));
    start = end + 1;
  }
  parts.push_back(configuration.crn.substr(start));
  if (parts.size() != 10 || parts[0] != "crn" || parts[1] != "v1" ||
      parts[4] != "quantum-computing" || parts[6].empty() || parts[7].empty()) {
    throw Failure{QDMI_ERROR_INVALIDARGUMENT};
  }
  if (configuration.baseUrl.empty()) {
    if (parts[5] == "us-east") {
      configuration.baseUrl = "https://quantum.cloud.ibm.com/api";
    } else if (parts[5] == "eu-de") {
      configuration.baseUrl = "https://eu-de.quantum.cloud.ibm.com/api";
    } else {
      throw Failure{QDMI_ERROR_NOTSUPPORTED};
    }
  }
  while (configuration.baseUrl.ends_with('/')) {
    configuration.baseUrl.pop_back();
  }
  if (!validEndpoint(configuration.baseUrl) ||
      !validEndpoint(configuration.authUrl)) {
    throw Failure{QDMI_ERROR_INVALIDARGUMENT};
  }
  return configuration;
}

Auth::Auth(Configuration configurationValue, Transport transportValue,
           Clock clockValue)
    : configuration(std::move(configurationValue)),
      transport(std::move(transportValue)), clock(std::move(clockValue)) {}

void Auth::refresh() {
  const auto started = clock();
  const auto response = transport(
      {.url = configuration.authUrl,
       .headers = {},
       .form = {{"grant_type", "urn:ibm:params:oauth:grant-type:apikey"},
                {"apikey", configuration.apiKey}}});
  // IAM reports invalid API keys as 400 as well as 401/403.
  if (!response.failed && !response.timedOut && response.status == 400) {
    throw Failure{QDMI_ERROR_PERMISSIONDENIED};
  }
  checkResponse(response);
  const auto data = nlohmann::json::parse(response.body);
  const auto token = data.at("access_token").get<std::string>();
  const auto& lifetime = data.at("expires_in");
  if (!lifetime.is_number_integer() || token.empty() ||
      token.find_first_of("\r\n") != std::string::npos) {
    throw Failure{QDMI_ERROR_FATAL};
  }
  const auto seconds = lifetime.get<std::int64_t>();
  if (seconds <= 0 || seconds > 86400) {
    throw Failure{QDMI_ERROR_FATAL};
  }
  // Keep a safety margin while still allowing short-lived test/service tokens.
  expires = started + std::chrono::seconds{
                          seconds - std::min<std::int64_t>(60, seconds / 10)};
  bearer = token;
}

std::string Auth::get(const std::string& resource) {
  const std::scoped_lock lock(mutex);
  if (bearer.empty() || clock() >= expires) {
    refresh();
  }
  const auto request = [&] {
    return transport({.url = configuration.baseUrl + resource,
                      .headers = {{"Accept", "application/json"},
                                  {"Authorization", "Bearer " + bearer},
                                  {"Service-CRN", configuration.crn},
                                  {"IBM-API-Version", "2026-04-15"}},
                      .form = {}});
  };
  auto response = request();
  if (!response.failed && !response.timedOut && response.status == 401) {
    bearer.clear();
    refresh();
    response = request();
  }
  checkResponse(response);
  return response.body;
}
} // namespace ibm
