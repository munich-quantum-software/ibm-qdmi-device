/*
 * Copyright (c) 2026 IQM Finland Oy
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

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cpr/body.h>
#include <cpr/connection_pool.h>
#include <cpr/cprtypes.h>
#include <cpr/error.h>
#include <cpr/payload.h>
#include <cpr/response.h>
#include <cpr/session.h>
#include <cstdint>
#include <cstdlib>
#include <ctime>
#include <curl/curl.h>
#include <curl/urlapi.h>
#include <fstream>
#include <ibm-qdmi-device/diagnostics.h>
#include <ibm_qdmi/constants.h>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <system_error>
#include <thread>
#include <utility>

#ifdef _MSC_VER
#include <cerrno>
#include <cstddef>
#include <stdlib.h> // NOLINT(modernize-deprecated-headers) -- MSVC environment extensions
#endif

#ifdef __linux__
#include <array>
#endif

// libcurl exposes a macro in curl.h on some platforms and a function otherwise.
#ifndef curl_easy_setopt
#include <curl/easy.h>
#endif

namespace ibm {
std::string internal::findCaBundle(std::span<const char* const> candidates) {
  for (const auto* candidate : candidates) {
    if (const std::ifstream file{candidate}; file.good()) {
      return candidate;
    }
  }
  return {};
}

std::string internal::resolveCaBundle() {
  for (const auto* variable : {"CURL_CA_BUNDLE", "SSL_CERT_FILE"}) {
#ifdef _MSC_VER
    char* value = nullptr;
    std::size_t size = 0;
    const auto error = _dupenv_s(&value, &size, variable);
    const std::unique_ptr<char, decltype(&std::free)> owned(value, std::free);
    if (error != 0) {
      throw Failure{error == ENOMEM ? QDMI_ERROR_OUTOFMEM : QDMI_ERROR_FATAL};
    }
    if (value != nullptr && *value != '\0') {
#else
    if (const auto* value = std::getenv(variable);
        value != nullptr && *value != '\0') {
#endif
      return value;
    }
  }
#ifdef __linux__
  constexpr std::array bundles{
      "/etc/ssl/certs/ca-certificates.crt",
      "/etc/pki/tls/certs/ca-bundle.crt",
      "/etc/ssl/ca-bundle.pem",
      "/etc/ssl/cert.pem",
  };
  return findCaBundle(bundles);
#else
  return {};
#endif
}

std::optional<std::chrono::milliseconds>
internal::parseRetryAfter(const std::string& value) {
  using Milliseconds = std::chrono::milliseconds;
  std::uint64_t seconds = 0;
  const auto [end, error] =
      std::from_chars(value.data(), value.data() + value.size(), seconds);
  if (end == value.data() + value.size() &&
      (error == std::errc{} || error == std::errc::result_out_of_range)) {
    if (error == std::errc::result_out_of_range ||
        seconds >
            static_cast<std::uint64_t>((Milliseconds::max)().count() / 1000)) {
      return (Milliseconds::max)();
    }
    return Milliseconds{static_cast<Milliseconds::rep>(seconds * 1000)};
  }
  const auto date = curl_getdate(value.c_str(), nullptr);
  if (date < 0) {
    return std::nullopt;
  }
  const auto secondsUntil =
      (std::max)(0.0, std::difftime(date, std::time(nullptr)));
  const auto maximumSeconds =
      std::chrono::duration_cast<std::chrono::seconds>((Milliseconds::max)())
          .count();
  if (secondsUntil >= static_cast<double>(maximumSeconds)) {
    return (Milliseconds::max)();
  }
  return std::chrono::duration_cast<Milliseconds>(
      std::chrono::duration<double>{secondsUntil});
}

internal::Hooks& internal::hooks() {
  static Hooks value{.sleepUntil = [](auto deadline) {
    std::this_thread::sleep_until(deadline);
  }};
  return value;
}

bool validEndpoint(const std::string& url) {
  const std::unique_ptr<CURLU, decltype(&curl_url_cleanup)> parsed(
      curl_url(), curl_url_cleanup);
  if (!parsed || curl_url_set(parsed.get(), CURLUPART_URL, url.c_str(),
                              CURLU_DISALLOW_USER) != CURLUE_OK) {
    return false;
  }
  const auto part = [&](CURLUPart field) {
    char* raw = nullptr;
    const auto result = curl_url_get(parsed.get(), field, &raw, 0);
    const std::unique_ptr<char, decltype(&curl_free)> owned(raw, curl_free);
    return result == CURLUE_OK ? std::string(owned.get()) : std::string{};
  };
  const auto scheme = part(CURLUPART_SCHEME);
  const auto host = part(CURLUPART_HOST);
  return !host.empty() && part(CURLUPART_QUERY).empty() &&
         part(CURLUPART_FRAGMENT).empty() &&
         (scheme == "https" ||
          (scheme == "http" &&
           (host == "127.0.0.1" || host == "[::1]" || host == "localhost")));
}

Response send(const Request& request) {
  if (!validEndpoint(request.url)) {
    throw Failure{QDMI_ERROR_INVALIDARGUMENT};
  }
  cpr::Session client;
  if (request.form.empty() && !request.post) {
    // Connection sharing across concurrent threads is unsupported by libcurl.
    // Fresh sessions share only this thread's read connections, never cookies.
    thread_local const cpr::ConnectionPool CONNECTIONS;
    client.SetConnectionPool(CONNECTIONS);
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-vararg)
    if (curl_easy_setopt(client.GetCurlHolder()->handle, CURLOPT_MAXCONNECTS,
                         4L) != CURLE_OK) {
      throw Failure{QDMI_ERROR_FATAL};
    }
  }
  // Avoid process-wide signal handler races between concurrent requests.
  // libcurl exposes this option through its variadic C API and requires a long.
  // NOLINTNEXTLINE(cppcoreguidelines-pro-type-vararg)
  if (curl_easy_setopt(client.GetCurlHolder()->handle, CURLOPT_NOSIGNAL, 1L) !=
      CURLE_OK) {
    throw Failure{QDMI_ERROR_FATAL};
  }
  client.SetUrl(cpr::Url{request.url});
  client.SetTimeout(cpr::Timeout{request.timeout});
  client.SetConnectTimeout(cpr::ConnectTimeout{request.timeout});
  client.SetRedirect(cpr::Redirect{false});
  client.SetVerifySsl(cpr::VerifySsl{true});
  if (const auto bundle = internal::resolveCaBundle(); !bundle.empty()) {
    // Set only CAINFO: CPR's SSL options also enable native-root fallback.
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-vararg)
    if (curl_easy_setopt(client.GetCurlHolder()->handle, CURLOPT_CAINFO,
                         bundle.c_str()) != CURLE_OK) {
      throw Failure{QDMI_ERROR_FATAL};
    }
  }
  cpr::Header headers;
  headers.insert(request.headers.begin(), request.headers.end());
  client.SetHeader(headers);
  cpr::Response response;
  if (request.form.empty() && !request.post) {
    response = client.Get();
  } else if (request.form.empty()) {
    client.SetBody(cpr::Body{request.body});
    response = client.Post();
  } else {
    cpr::Payload payload{};
    for (const auto& [name, value] : request.form) {
      payload.Add(cpr::Pair{name, value});
    }
    client.SetPayload(payload);
    response = client.Post();
  }
  return {.status = static_cast<std::int32_t>(response.status_code),
          .body = std::move(response.text),
          .timedOut = response.error.code == cpr::ErrorCode::OPERATION_TIMEDOUT,
          .failed = response.error.code != cpr::ErrorCode::OK,
          .transient =
              response.error.code == cpr::ErrorCode::COULDNT_CONNECT ||
              response.error.code == cpr::ErrorCode::COULDNT_RESOLVE_HOST ||
              response.error.code == cpr::ErrorCode::SEND_ERROR ||
              response.error.code == cpr::ErrorCode::RECV_ERROR ||
              response.error.code == cpr::ErrorCode::GOT_NOTHING ||
              response.error.code == cpr::ErrorCode::PARTIAL_FILE,
          .retryAfter =
              internal::parseRetryAfter(response.header["Retry-After"])};
}

void checkResponse(const Response& response) {
  if (response.timedOut) {
    throw Failure{QDMI_ERROR_TIMEOUT, IBM_QDMI_DIAGNOSTIC_TIMEOUT};
  }
  if (response.failed) {
    throw Failure{QDMI_ERROR_FATAL, IBM_QDMI_DIAGNOSTIC_TRANSPORT};
  }
  if (response.status == 401 || response.status == 403) {
    throw Failure{QDMI_ERROR_PERMISSIONDENIED,
                  IBM_QDMI_DIAGNOSTIC_AUTHENTICATION};
  }
  if (response.status == 404) {
    throw Failure{QDMI_ERROR_NOTFOUND, IBM_QDMI_DIAGNOSTIC_NOT_FOUND};
  }
  if (response.status == 429) {
    throw Failure{QDMI_ERROR_FATAL, IBM_QDMI_DIAGNOSTIC_RATE_LIMIT};
  }
  if (response.status != 200) {
    throw Failure{QDMI_ERROR_FATAL, IBM_QDMI_DIAGNOSTIC_SERVICE};
  }
}
} // namespace ibm
