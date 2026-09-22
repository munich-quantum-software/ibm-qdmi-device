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
#include <cerrno>
#include <charconv>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <ibm_qdmi/constants.h>
#include <ios>
#include <iterator>
#include <mutex>
#include <nlohmann/json.hpp>
#include <nlohmann/json_fwd.hpp>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

#ifdef _MSC_VER
#include <memory>

// MSVC declares _dupenv_s in its C extension header.
#include <stdlib.h> // NOLINT(modernize-deprecated-headers)
#endif

namespace ibm {
namespace {
std::string environment(const char* name) {
#ifdef _MSC_VER
  char* raw = nullptr;
  std::size_t size = 0;
  const auto error = _dupenv_s(&raw, &size, name);
  const std::unique_ptr<char, decltype(&std::free)> owned(raw, std::free);
  if (error != 0) {
    throw Failure{error == ENOMEM ? QDMI_ERROR_OUTOFMEM : QDMI_ERROR_FATAL};
  }
  return raw == nullptr ? std::string{} : std::string{raw};
#else
  const auto* value = std::getenv(name);
  return value == nullptr ? std::string{} : std::string{value};
#endif
}

std::string readApiKey(const std::string& path) {
  if (path.empty()) {
    throw Failure{QDMI_ERROR_INVALIDARGUMENT};
  }
  std::ifstream input(
      std::filesystem::path{std::u8string{path.begin(), path.end()}},
      std::ios::binary);
  if (!input) {
    throw Failure{QDMI_ERROR_PERMISSIONDENIED};
  }
  std::string key{std::istreambuf_iterator<char>{input},
                  std::istreambuf_iterator<char>{}};
  if (input.bad()) {
    throw Failure{QDMI_ERROR_PERMISSIONDENIED};
  }
  if (key.ends_with('\n')) {
    key.pop_back();
    if (key.ends_with('\r')) {
      key.pop_back();
    }
  }
  if (key.empty() || key.find_first_of("\r\n") != std::string::npos ||
      key.find('\0') != std::string::npos) {
    throw Failure{QDMI_ERROR_INVALIDARGUMENT};
  }
  try {
    // The existing JSON library checks UTF-8 strictly when encoding strings.
    static_cast<void>(nlohmann::json(key).dump());
  } catch (const nlohmann::json::type_error&) {
    throw Failure{QDMI_ERROR_INVALIDARGUMENT};
  }
  return key;
}
} // namespace

std::chrono::milliseconds parseRequestTimeout(std::string_view value) {
  std::int32_t milliseconds = 0;
  const auto [end, error] =
      std::from_chars(value.data(), value.data() + value.size(), milliseconds);
  if (error != std::errc{} || end != value.data() + value.size() ||
      milliseconds <= 0) {
    throw Failure{QDMI_ERROR_INVALIDARGUMENT};
  }
  return std::chrono::milliseconds{milliseconds};
}

Configuration resolve(Configuration configuration) {
  if (!configuration.apiKeyConfigured && configuration.apiKey.empty()) {
    configuration.apiKey = configuration.authFile
                               ? readApiKey(*configuration.authFile)
                               : environment("IBM_QUANTUM_API_KEY");
  }
  if (!configuration.backendConfigured && configuration.backend.empty()) {
    configuration.backend = environment("IBM_QUANTUM_BACKEND");
  }
  if (!configuration.crnConfigured && configuration.crn.empty()) {
    configuration.crn = environment("IBM_QUANTUM_INSTANCE_CRN");
  }
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

std::chrono::milliseconds Auth::remaining(Deadline deadline) const {
  const auto now = clock();
  if (now >= deadline) {
    throw Failure{QDMI_ERROR_TIMEOUT};
  }
  return std::min(configuration.requestTimeout,
                  std::chrono::ceil<std::chrono::milliseconds>(deadline - now));
}

void Auth::refresh(Deadline deadline) {
  const auto started = clock();
  const auto response = transport(
      {.url = configuration.authUrl,
       .headers = {},
       .form = {{"grant_type", "urn:ibm:params:oauth:grant-type:apikey"},
                {"apikey", configuration.apiKey}},
       .body = {},
       .timeout = remaining(deadline)});
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

Response Auth::request(const std::string& resource, bool post,
                       const std::string& body, Deadline deadline) {
  std::unique_lock lock(mutex, std::defer_lock);
  if (!lock.try_lock_until(deadline)) {
    throw Failure{QDMI_ERROR_TIMEOUT};
  }
  if (bearer.empty() || clock() >= expires) {
    refresh(deadline);
  }
  const auto request = [&] {
    return transport({.url = configuration.baseUrl + resource,
                      .headers = {{"Accept", "application/json"},
                                  {"Authorization", "Bearer " + bearer},
                                  {"Service-CRN", configuration.crn},
                                  {"IBM-API-Version", "2026-04-15"},
                                  {"Content-Type", "application/json"}},
                      .form = {},
                      .post = post,
                      .body = body,
                      .timeout = remaining(deadline)});
  };
  auto response = request();
  if (!post && !response.failed && !response.timedOut &&
      response.status == 401) {
    bearer.clear();
    refresh(deadline);
    response = request();
  }
  if (post && response.status == 401) {
    bearer.clear();
  }
  return response;
}

std::string Auth::get(const std::string& resource, Deadline deadline) {
  const auto response = request(resource, false, {}, deadline);
  checkResponse(response);
  return response.body;
}
} // namespace ibm
