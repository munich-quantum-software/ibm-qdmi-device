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
#include <nlohmann/json_fwd.hpp>
#include <optional>
#include <string>
#include <vector>

namespace ibm {
struct Register {
  std::string name;
  std::size_t width;
};
/// Extract the output layout of a static, bound OpenQASM 3 program.
std::vector<Register> outputRegisters(const std::string& program,
                                      std::size_t qubits);
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
  void setProgram(std::string source);
  void submit();
  void retrieve(const std::string& remoteId);
  QDMI_Job_Status check(Deadline deadline = Deadline::max());
  void cancel();
  const Results& results();
  [[nodiscard]] bool configurable() const;

  std::string id;
  std::string program;
  std::optional<QDMI_Program_Format> format;
  std::size_t shots = 1024;
  std::uint64_t maxExecutionTime = 60;
  QDMI_Job_Status status = QDMI_JOB_STATUS_CREATED;

private:
  Auth* auth;
  std::string backend;
  std::size_t qubits;
  bool attempted = false;
  std::vector<Register> registers;
  std::optional<Results> cached;
};
bool terminal(QDMI_Job_Status status);
} // namespace ibm
