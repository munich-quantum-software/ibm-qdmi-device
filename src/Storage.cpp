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

#include "Storage.hpp"

#include "Http.hpp"

#include <algorithm>
#include <aws/core/Aws.h>
#include <aws/core/auth/AWSCredentials.h>
#include <aws/core/auth/signer/AWSAuthV4Signer.h>
#include <aws/core/client/ClientConfiguration.h>
#include <aws/core/http/HttpTypes.h>
#include <aws/core/utils/UUID.h>
#include <aws/s3/S3Client.h>
#include <cctype>
#include <cstddef>
#include <filesystem>
#include <fstream>
#include <ibm_qdmi/constants.h>
#include <ios>
#include <mutex>
#include <nlohmann/json.hpp>
#include <nlohmann/json_fwd.hpp>
#include <string>

namespace ibm {
namespace {
struct Runtime {
  Aws::SDKOptions options;
  Runtime() {
    options.httpOptions.initAndCleanupCurl = false;
    options.cryptoOptions.initAndCleanupOpenSSL = false;
    Aws::InitAPI(options);
  }
  ~Runtime() { Aws::ShutdownAPI(options); }
};
std::mutex& signingMutex() {
  static std::mutex mutex;
  return mutex;
}
void require(bool condition) {
  if (!condition) {
    throw Failure{QDMI_ERROR_INVALIDARGUMENT};
  }
}
std::string field(const nlohmann::json& data, const char* name,
                  bool optional = false) {
  if (optional && !data.contains(name)) {
    return {};
  }
  require(data.contains(name) && data.at(name).is_string());
  const auto result = data.at(name).get<std::string>();
  require(!result.empty() && result.size() <= 8192 &&
          std::ranges::none_of(
              result, [](unsigned char ch) { return ch < 32 || ch == 127; }));
  return result;
}
} // namespace

StorageConfiguration readStorageConfiguration(const std::string& path) {
  require(!path.empty());
  const auto filename =
      std::filesystem::path{std::u8string{path.begin(), path.end()}};
  std::ifstream input(filename, std::ios::binary);
  if (!input) {
    throw Failure{QDMI_ERROR_PERMISSIONDENIED};
  }
  std::string contents(65537, '\0');
  input.read(contents.data(), static_cast<std::streamsize>(contents.size()));
  require(!input.bad() && input.gcount() <= 65536);
  contents.resize(static_cast<std::size_t>(input.gcount()));
  const auto data = nlohmann::json::parse(contents, nullptr, false);
  require(data.is_object());
  StorageConfiguration config{
      .endpoint = field(data, "endpoint"),
      .bucket = field(data, "bucket"),
      .region = field(data, "region"),
      .accessKey = field(data, "access_key"),
      .secretKey = field(data, "secret_key"),
      .sessionToken = field(data, "session_token", true),
      .serviceEndpoint = field(data, "service_endpoint", true)};
  while (config.endpoint.ends_with('/')) {
    config.endpoint.pop_back();
  }
  while (config.serviceEndpoint.ends_with('/')) {
    config.serviceEndpoint.pop_back();
  }
  require(validEndpoint(config.endpoint) &&
          config.endpoint.find_first_of("?#") == std::string::npos &&
          (config.serviceEndpoint.empty() ||
           (validEndpoint(config.serviceEndpoint) &&
            config.serviceEndpoint.find_first_of("?#") == std::string::npos)));
  require(config.bucket.size() >= 3 && config.bucket.size() <= 63 &&
          std::isalnum(static_cast<unsigned char>(config.bucket.front())) !=
              0 &&
          std::isalnum(static_cast<unsigned char>(config.bucket.back())) != 0 &&
          config.bucket.find("..") == std::string::npos &&
          std::ranges::all_of(config.bucket, [](unsigned char ch) {
            return (ch >= 'a' && ch <= 'z') || std::isdigit(ch) != 0 ||
                   ch == '-' || ch == '.';
          }));
  require(std::ranges::all_of(config.region, [](unsigned char ch) {
    return std::isalnum(ch) != 0 || ch == '-';
  }));
  return config;
}
std::string storageUrl(const StorageConfiguration& configuration,
                       const std::string& key, bool put, bool service) {
  // SDK shutdown must run on its initializing thread, outside DLL teardown.
  const std::scoped_lock lock(signingMutex());
  const Runtime runtime;
  Aws::Client::ClientConfiguration config(
      Aws::Client::ClientConfigurationInitValues{.shouldDisableIMDS = true});
  config.region = configuration.region;
  config.endpointOverride = (service && !configuration.serviceEndpoint.empty()
                                 ? configuration.serviceEndpoint
                                 : configuration.endpoint);
  config.enableEndpointDiscovery = false;
  config.useDualStack = false;
  config.useFIPS = false;
  const Aws::Auth::AWSCredentials credentials(configuration.accessKey,
                                              configuration.secretKey,
                                              configuration.sessionToken);
  // Only presigning runs in the SDK; requests retain our TLS and timeout
  // policy.
  Aws::S3::S3Client client(
      credentials, config,
      Aws::Client::AWSAuthV4Signer::PayloadSigningPolicy::Never, false);
  const auto result = client.GeneratePresignedUrl(
      configuration.bucket, key,
      put ? Aws::Http::HttpMethod::HTTP_PUT : Aws::Http::HttpMethod::HTTP_GET,
      86400);
  if (result.empty()) {
    throw Failure{QDMI_ERROR_FATAL};
  }
  return {result.data(), result.size()};
}
std::string newJobId() {
  const std::scoped_lock lock(signingMutex());
  const Runtime runtime;
  const Aws::String id = Aws::Utils::UUID::RandomUUID();
  return {id.data(), id.size()};
}
} // namespace ibm
