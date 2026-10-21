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

#include <cpr/session.h>
#include <cstddef>
#include <curl/curl.h>
#include <curl/easy.h>
#include <exception>
#include <iostream>
#include <string>

namespace {
std::size_t discard(char* /*data*/, std::size_t size, std::size_t count,
                    void* /*user*/) {
  return size * count;
}
} // namespace

int main(int argc, char** argv) try {
  if (argc != 4 || curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
    return 1;
  }
  std::cout << curl_version() << '\n';
  int result = 1;
  {
    cpr::Session session;
    auto* handle = session.GetCurlHolder()->handle;
    if (handle == nullptr) {
      return 1;
    }
    // Seed an alternate trust directory without changing the host's CA store.
    // NOLINTBEGIN(cppcoreguidelines-pro-type-vararg)
    const auto capath = curl_easy_setopt(handle, CURLOPT_CAPATH, argv[3]);
    if (capath == CURLE_NOT_BUILT_IN) {
      std::cout << "TLS backend does not support CA directories\n";
      return 125;
    }
    const auto controlBundle = std::string{argv[3]} + "/control.pem";
    if (capath != CURLE_OK ||
        curl_easy_setopt(handle, CURLOPT_CAINFO, controlBundle.c_str()) !=
            CURLE_OK ||
        curl_easy_setopt(handle, CURLOPT_URL, argv[1]) != CURLE_OK ||
        curl_easy_setopt(handle, CURLOPT_NOPROXY, "*") != CURLE_OK ||
        curl_easy_setopt(handle, CURLOPT_TIMEOUT, 5L) != CURLE_OK ||
        curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, discard) != CURLE_OK) {
      return 1;
    }
    // NOLINTEND(cppcoreguidelines-pro-type-vararg)
    try {
      if (std::string{argv[2]} != "-") {
        ibm::internal::configureCaBundle(session, argv[2]);
      }
      result = static_cast<int>(curl_easy_perform(handle));
      if (result != 0) {
        std::cout << session.GetCurlHolder()->error.data() << '\n';
      }
    } catch (const ibm::Failure&) {
      return 1;
    }
  }
  curl_global_cleanup();
  return result;
} catch (const std::exception&) {
  return 1;
}
