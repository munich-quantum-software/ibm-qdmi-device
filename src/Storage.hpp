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

#include <string>

namespace ibm {
struct StorageConfiguration {
  std::string endpoint;
  std::string bucket;
  std::string region;
  std::string accessKey;
  std::string secretKey;
  std::string sessionToken;
  std::string serviceEndpoint;
};
/// Read a private configuration snapshot without implicit AWS discovery.
StorageConfiguration readStorageConfiguration(const std::string& path);
/// Sign the final endpoint and object path; all transfers use our HTTP layer.
std::string storageUrl(const StorageConfiguration& configuration,
                       const std::string& key, bool put, bool service = false);
std::string newJobId();
} // namespace ibm
