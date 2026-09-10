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

#include <cpr/cprtypes.h>
#include <cpr/error.h>
#include <cpr/payload.h>
#include <cpr/response.h>
#include <cpr/session.h>
#include <cstdint>
#include <curl/curl.h>
#include <curl/urlapi.h>
#include <ibm_qdmi/constants.h>
#include <memory>
#include <string>
#include <utility>

namespace ibm {
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
  client.SetUrl(cpr::Url{request.url});
  client.SetTimeout(cpr::Timeout{30000});
  client.SetConnectTimeout(cpr::ConnectTimeout{30000});
  client.SetRedirect(cpr::Redirect{false});
  client.SetVerifySsl(cpr::VerifySsl{true});
  cpr::Header headers;
  headers.insert(request.headers.begin(), request.headers.end());
  client.SetHeader(headers);
  cpr::Response response;
  if (request.form.empty()) {
    response = client.Get();
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
          .failed = response.error.code != cpr::ErrorCode::OK};
}

void checkResponse(const Response& response) {
  if (response.timedOut) {
    throw Failure{QDMI_ERROR_TIMEOUT};
  }
  if (response.failed) {
    throw Failure{QDMI_ERROR_FATAL};
  }
  if (response.status == 401 || response.status == 403) {
    throw Failure{QDMI_ERROR_PERMISSIONDENIED};
  }
  if (response.status == 404) {
    throw Failure{QDMI_ERROR_NOTFOUND};
  }
  if (response.status != 200) {
    throw Failure{QDMI_ERROR_FATAL};
  }
}
} // namespace ibm
