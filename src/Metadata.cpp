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

#include "Metadata.hpp"

#include "Http.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <ibm_qdmi/constants.h>
#include <limits>
#include <nlohmann/json.hpp>
#include <nlohmann/json_fwd.hpp>
#include <optional>
#include <set>
#include <string>
#include <utility>

namespace ibm {
namespace {
std::size_t index(const nlohmann::json& value) {
  if (!value.is_number_integer() || value.get<double>() < 0 ||
      value.get<double>() >=
          static_cast<double>(std::numeric_limits<std::size_t>::max())) {
    throw Failure{QDMI_ERROR_FATAL};
  }
  return value.get<std::size_t>();
}
Sites tuple(const nlohmann::json& values, std::size_t count) {
  if (!values.is_array() || values.empty()) {
    throw Failure{QDMI_ERROR_FATAL};
  }
  Sites sites;
  for (const auto& value : values) {
    const auto site = index(value);
    if (site >= count || std::ranges::find(sites, site) != sites.end()) {
      throw Failure{QDMI_ERROR_FATAL};
    }
    sites.push_back(site);
  }
  return sites;
}
std::optional<std::uint64_t> duration(const nlohmann::json& parameter) {
  if (!parameter.contains("value") || !parameter["value"].is_number() ||
      !parameter.contains("unit") || !parameter["unit"].is_string()) {
    return std::nullopt;
  }
  const auto value = parameter["value"].get<double>();
  const auto unit = parameter["unit"].get<std::string>();
  double scale = 0;
  if (unit == "s") {
    scale = 1e12;
  } else if (unit == "ms") {
    scale = 1e9;
  } else if (unit == "us" || unit == "µs") {
    scale = 1e6;
  } else if (unit == "ns") {
    scale = 1e3;
  } else if (unit == "ps") {
    scale = 1;
  }
  const auto rounded = std::round(value * scale);
  // The upper bound is exclusive: UINT64_MAX rounds up in binary64.
  if (scale == 0 || !std::isfinite(value) || value < 0 ||
      !std::isfinite(rounded) ||
      rounded >=
          static_cast<double>(std::numeric_limits<std::uint64_t>::max())) {
    return std::nullopt;
  }
  return static_cast<std::uint64_t>(rounded);
}
void addSites(Operation& operation, const Sites& sites) {
  if (operation.arity && *operation.arity != sites.size()) {
    throw Failure{QDMI_ERROR_FATAL};
  }
  operation.arity = sites.size();
  if (std::ranges::find(operation.sites, sites) == operation.sites.end()) {
    operation.sites.push_back(sites);
  }
}
} // namespace

Metadata parseMetadata(const nlohmann::json& configuration,
                       const nlohmann::json& properties) {
  Metadata result;
  result.name = configuration.at("backend_name").get<std::string>();
  result.version = configuration.at("backend_version").get<std::string>();
  const auto count = index(configuration.at("n_qubits"));
  if (result.name.empty() || result.version.empty() || count == 0) {
    throw Failure{QDMI_ERROR_FATAL};
  }
  result.sites.resize(count);
  for (std::size_t i = 0; i < count; ++i) {
    result.sites[i].index = i;
  }
  const auto& coupling = configuration.at("coupling_map");
  if (!coupling.is_array()) {
    throw Failure{QDMI_ERROR_FATAL};
  }
  for (const auto& item : coupling) {
    auto sites = tuple(item, count);
    if (sites.size() != 2) {
      throw Failure{QDMI_ERROR_FATAL};
    }
    if (std::ranges::find(result.coupling, sites) == result.coupling.end()) {
      result.coupling.push_back(std::move(sites));
    }
  }
  const auto& basis = configuration.at("basis_gates");
  const auto& gates = configuration.at("gates");
  if (!basis.is_array() || basis.empty() || !gates.is_array() ||
      !properties.is_object()) {
    throw Failure{QDMI_ERROR_FATAL};
  }
  std::set<std::string> names;
  for (const auto& item : basis) {
    auto name = item.get<std::string>();
    if (name.empty() || !names.insert(name).second) {
      throw Failure{QDMI_ERROR_FATAL};
    }
    Operation operation;
    operation.name = std::move(name);
    bool defined = false;
    for (const auto& gate : gates) {
      if (gate.at("name") != operation.name) {
        continue;
      }
      if (defined || !gate.at("parameters").is_array()) {
        throw Failure{QDMI_ERROR_FATAL};
      }
      defined = true;
      for (const auto& parameter : gate.at("parameters")) {
        if (!parameter.is_string()) {
          throw Failure{QDMI_ERROR_FATAL};
        }
      }
      operation.parameters = gate.at("parameters").size();
      if (gate.contains("coupling_map") && !gate["coupling_map"].is_null()) {
        if (!gate["coupling_map"].is_array()) {
          throw Failure{QDMI_ERROR_FATAL};
        }
        for (const auto& entry : gate["coupling_map"]) {
          addSites(operation, tuple(entry, count));
        }
      }
    }
    result.operations.push_back(std::move(operation));
  }
  if (properties.contains("qubits") && !properties["qubits"].is_null()) {
    const auto& qubits = properties["qubits"];
    if (!qubits.is_array() || qubits.size() > count) {
      throw Failure{QDMI_ERROR_FATAL};
    }
    for (std::size_t i = 0; i < qubits.size(); ++i) {
      if (!qubits[i].is_array()) {
        throw Failure{QDMI_ERROR_FATAL};
      }
      for (const auto& parameter : qubits[i]) {
        const auto name = parameter.at("name").get<std::string>();
        if (name == "T1") {
          result.sites[i].t1 = duration(parameter);
        } else if (name == "T2") {
          result.sites[i].t2 = duration(parameter);
        }
      }
    }
  }
  if (properties.contains("gates") && !properties["gates"].is_null()) {
    if (!properties["gates"].is_array()) {
      throw Failure{QDMI_ERROR_FATAL};
    }
    // Configuration tuples are authoritative when supplied. Calibration tuples
    // provide explicit support information only when configuration omits them.
    std::set<std::string> configured;
    for (const auto& operation : result.operations) {
      if (!operation.sites.empty()) {
        configured.insert(operation.name);
      }
    }
    for (const auto& gate : properties["gates"]) {
      const auto name = gate.at("gate").get<std::string>();
      auto operation =
          std::ranges::find(result.operations, name, &Operation::name);
      if (operation == result.operations.end()) {
        continue;
      }
      const auto sites = tuple(gate.at("qubits"), count);
      if (configured.contains(name) &&
          std::ranges::find(operation->sites, sites) ==
              operation->sites.end()) {
        throw Failure{QDMI_ERROR_FATAL};
      }
      addSites(*operation, sites);
      Calibration calibration;
      if (!gate.at("parameters").is_array()) {
        throw Failure{QDMI_ERROR_FATAL};
      }
      for (const auto& parameter : gate.at("parameters")) {
        const auto parameterName = parameter.at("name").get<std::string>();
        if (parameterName == "gate_length") {
          calibration.duration = duration(parameter);
        } else if (parameterName == "gate_error" &&
                   parameter.contains("value") &&
                   parameter["value"].is_number()) {
          const auto error = parameter["value"].get<double>();
          if (std::isfinite(error) && error >= 0 && error <= 1) {
            calibration.fidelity = 1 - error;
          }
        }
      }
      if (std::ranges::any_of(operation->calibrations, [&](const auto& entry) {
            return entry.first == sites;
          })) {
        throw Failure{QDMI_ERROR_FATAL};
      }
      operation->calibrations.emplace_back(sites, calibration);
    }
  }
  return result;
}

Status parseStatus(const nlohmann::json& data) {
  Status result;
  result.queue = index(data.at("length_queue"));
  if (data.contains("state") && !data["state"].is_null()) {
    result.available = data["state"].get<bool>();
  }
  return result;
}
} // namespace ibm
