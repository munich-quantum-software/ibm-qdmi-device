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

#include "Auth.hpp"

#include <cstddef>
#include <cstdint>
#include <ibm_qdmi/constants.h>
// The stored JSON member requires the complete type, not just the json alias.
#include <nlohmann/json.hpp> // IWYU pragma: keep
#include <nlohmann/json_fwd.hpp>
#include <optional>
#include <string>
#include <vector>

namespace ibm {
struct Register {
  std::string name;
  std::size_t width;
};
/// Extract top-level classical declarations in source order.
std::vector<Register> outputRegisters(const std::string& program);
/// Read the output layout of one QPY 17 circuit without interpreting gates.
std::vector<Register> qpyRegisters(const std::string& program,
                                   std::size_t qubits);
/// Encode QPY using IBM's zlib-compressed, base64 transport.
std::string encodeQpy(const std::string& program);
/// Decode IBM's transport back to the original QPY bytes.
std::string decodeQpy(const std::string& encoded);
struct Results {
  std::string shots;
  std::string keys;
  std::vector<std::size_t> counts;
};
Results decodeResults(const nlohmann::json& data,
                      const std::vector<Register>& registers,
                      std::size_t shots);
/// Job state is protected by its owning C ABI handle's mutex.
class Job {
public:
  Job(Auth& auth, std::string backend, std::size_t qubits);
  void setPrograms(QDMI_Program_Format value, std::vector<std::string> sources);
  void checkProgramSupport(QDMI_Program_Format value, std::size_t count) const;
  void setShots(std::size_t value);
  /// Validate and replace DD options atomically, filling omitted defaults.
  void setDynamicalDecoupling(const std::string& options);
  void submit();
  void retrieve(const std::string& remoteId);
  QDMI_Job_Status check(Deadline deadline = Deadline::max());
  void cancel();
  const Results& results(std::size_t index);
  const std::string& executorResults();
  [[nodiscard]] bool configurable() const;

  std::string id;
  std::vector<std::string> programs;
  std::optional<QDMI_Program_Format> format;
  std::size_t shots = 1024;
  std::uint64_t maxExecutionTime = 60;
  QDMI_Job_Status status = QDMI_JOB_STATUS_CREATED;

private:
  Auth* auth;
  std::string backend;
  std::size_t qubits;
  nlohmann::json dynamicalDecoupling;
  bool attempted = false;
  bool samplerOptionsSet = false;
  std::vector<std::vector<Register>> registers;
  std::optional<std::vector<Results>> cached;
  std::optional<std::string> cachedExecutor;
};
bool terminal(QDMI_Job_Status status);
} // namespace ibm
