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

#include <cstddef>
#include <cstdint>
#include <nlohmann/json_fwd.hpp>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace ibm {
using Sites = std::vector<std::size_t>;
struct Calibration {
  std::optional<std::uint64_t> duration;
  std::optional<double> fidelity;
};
struct Site {
  std::size_t index = 0;
  std::optional<std::uint64_t> t1;
  std::optional<std::uint64_t> t2;
};
struct Operation {
  std::string name;
  std::optional<std::size_t> arity;
  std::optional<std::size_t> parameters;
  std::vector<Sites> sites;
  std::vector<std::pair<Sites, Calibration>> calibrations;
};
struct Metadata {
  std::string name;
  std::string version;
  std::vector<Site> sites;
  std::vector<Operation> operations;
  std::vector<Sites> coupling;
};
Metadata parseMetadata(const nlohmann::json& configuration,
                       const nlohmann::json& properties);
struct Status {
  std::optional<bool> available;
  std::size_t queue = 0;
};
Status parseStatus(const nlohmann::json& data);
} // namespace ibm
