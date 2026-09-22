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

#include "Job.hpp"

#include "Auth.hpp"
#include "Http.hpp"

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <ibm_qdmi/constants.h>
#include <limits>
#include <map>
#include <nlohmann/json.hpp>
#include <nlohmann/json_fwd.hpp>
#include <string>
#include <utility>
#include <vector>

namespace ibm {
namespace {
void require(bool condition, int code = QDMI_ERROR_FATAL) {
  if (!condition) {
    throw Failure{code};
  }
}
nlohmann::json defaultDynamicalDecoupling() {
  return {{"enable", false},
          {"sequence_type", "XX"},
          {"extra_slack_distribution", "middle"},
          {"scheduling_method", "alap"},
          {"skip_reset_qubits", false}};
}
bool identifier(const std::string& text) {
  return !text.empty() && text.size() <= 255 &&
         std::ranges::all_of(text, [](unsigned char character) {
           return std::isalnum(character) != 0 || character == '_' ||
                  character == '-';
         });
}
std::size_t positiveInteger(const nlohmann::json& value) {
  require(value.is_number_integer());
  if (value.is_number_integer() && !value.is_number_unsigned()) {
    require(value.get<std::int64_t>() > 0);
  }
  const auto result = value.get<std::uint64_t>();
  require(result > 0 && result <= std::numeric_limits<std::size_t>::max());
  return static_cast<std::size_t>(result);
}
QDMI_Job_Status parseJobStatus(const nlohmann::json& data) {
  const auto value = data.at("state").at("status").get<std::string>();
  if (value == "Completed") {
    return QDMI_JOB_STATUS_DONE;
  }
  if (value == "Cancelled" || value == "Canceled") {
    return QDMI_JOB_STATUS_CANCELED;
  }
  if (value == "Failed") {
    return QDMI_JOB_STATUS_FAILED;
  }
  if (value == "Running") {
    return QDMI_JOB_STATUS_RUNNING;
  }
  if (value == "Queued") {
    return QDMI_JOB_STATUS_QUEUED;
  }
  if (value == "Creating" || value == "Created" || value == "Validating") {
    return QDMI_JOB_STATUS_SUBMITTED;
  }
  throw Failure{QDMI_ERROR_FATAL};
}
std::string bitstring(const std::string& sample, std::size_t width) {
  require(sample.starts_with("0x") && sample.size() > 2);
  std::string bits;
  for (const auto character : sample.substr(2)) {
    const auto value = std::string("0123456789abcdef")
                           .find(static_cast<char>(std::tolower(
                               static_cast<unsigned char>(character))));
    require(value != std::string::npos);
    for (int shift = 3; shift >= 0; --shift) {
      bits += ((value >> shift) & 1U) != 0 ? '1' : '0';
    }
  }
  if (bits.size() > width) {
    require(bits.find('1') >= bits.size() - width);
    bits.erase(0, bits.size() - width);
  }
  bits.insert(0, width - bits.size(), '0');
  return bits;
}
void append(std::string& destination, const std::string& value) {
  if (!destination.empty()) {
    destination += ',';
  }
  destination += value;
}
} // namespace

Results decodeResults(const nlohmann::json& data,
                      const std::vector<Register>& registers,
                      std::size_t shots) {
  const auto& pubs = data.at("results");
  require(pubs.is_array() && pubs.size() == 1);
  const auto& output = pubs.at(0).at("data");
  require(output.is_object() && output.size() == registers.size());
  std::vector<std::string> samples(shots);
  // QDMI strings put the highest classical-bit index on the left. Preserve
  // declaration order even when JSON objects sort their keys differently.
  for (const auto& reg : registers) {
    const auto& result = output.at(reg.name);
    if (result.contains("num_bits")) {
      require(positiveInteger(result.at("num_bits")) == reg.width);
    }
    const auto& values = result.at("samples");
    require(values.is_array() && values.size() == shots);
    for (std::size_t index = 0; index < shots; ++index) {
      samples[index] =
          bitstring(values.at(index).get<std::string>(), reg.width) +
          samples[index];
    }
  }
  Results result;
  std::map<std::string, std::size_t> histogram;
  for (const auto& sample : samples) {
    append(result.shots, sample);
    ++histogram[sample];
  }
  for (const auto& [key, count] : histogram) {
    append(result.keys, key);
    result.counts.push_back(count);
  }
  return result;
}

Job::Job(Auth& authValue, std::string backendValue, std::size_t qubitsValue)
    : auth(&authValue), backend(std::move(backendValue)), qubits(qubitsValue),
      dynamicalDecoupling(defaultDynamicalDecoupling()) {}
bool Job::configurable() const {
  return !attempted && status == QDMI_JOB_STATUS_CREATED;
}
bool terminal(QDMI_Job_Status status) {
  return status == QDMI_JOB_STATUS_DONE || status == QDMI_JOB_STATUS_CANCELED ||
         status == QDMI_JOB_STATUS_FAILED;
}
void Job::setProgram(std::string source) {
  auto layout = outputRegisters(source, qubits);
  program = std::move(source);
  registers = std::move(layout);
}
void Job::setDynamicalDecoupling(const std::string& options) {
  require(configurable(), QDMI_ERROR_BADSTATE);
  const auto parsed = nlohmann::json::parse(options, nullptr, false);
  require(parsed.is_object(), QDMI_ERROR_INVALIDARGUMENT);
  for (const auto& [key, value] : parsed.items()) {
    bool valid = false;
    if (key == "enable" || key == "skip_reset_qubits") {
      valid = value.is_boolean();
    } else if (key == "sequence_type") {
      valid = value == "XX" || value == "XpXm" || value == "XY4";
    } else if (key == "extra_slack_distribution") {
      valid = value == "middle" || value == "edges";
    } else if (key == "scheduling_method") {
      valid = value == "alap" || value == "asap";
    }
    require(valid, QDMI_ERROR_INVALIDARGUMENT);
  }
  auto configured = defaultDynamicalDecoupling();
  configured.update(parsed);
  dynamicalDecoupling = std::move(configured);
}
void Job::submit() {
  require(configurable() && format.has_value() && !program.empty(),
          QDMI_ERROR_BADSTATE);
  const nlohmann::json payload{
      {"program_id", "sampler"},
      {"backend", backend},
      {"cost", maxExecutionTime},
      {"params",
       {{"version", 2},
        {"support_qiskit", false},
        {"pubs", nlohmann::json::array(
                     {nlohmann::json::array({program, nullptr, shots})})},
        {"options",
         {{"execution", {{"meas_type", "classified"}}},
          {"dynamical_decoupling", dynamicalDecoupling},
          {"twirling",
           {{"enable_gates", false}, {"enable_measure", false}}}}}}}};
  const auto body = payload.dump();
  // Once submission starts, even a lost response must never permit a duplicate.
  attempted = true;
  status = QDMI_JOB_STATUS_FAILED;
  const auto response = auth->request("/v1/jobs", true, body);
  checkResponse(response);
  const auto data = nlohmann::json::parse(response.body);
  const auto remoteId = data.at("id").get<std::string>();
  require(identifier(remoteId));
  id = remoteId;
  require(data.at("backend") == backend);
  status = QDMI_JOB_STATUS_SUBMITTED;
}
void Job::retrieve(const std::string& remoteId) {
  require(identifier(remoteId), QDMI_ERROR_INVALIDARGUMENT);
  const auto data = nlohmann::json::parse(auth->get("/v1/jobs/" + remoteId));
  require(data.at("id") == remoteId && data.at("backend") == backend,
          QDMI_ERROR_INVALIDARGUMENT);
  require(data.at("program").at("id") == "sampler" &&
              !data.value("private", false),
          QDMI_ERROR_NOTSUPPORTED);
  auto parameters = data.at("params");
  if (parameters.is_string()) {
    parameters = nlohmann::json::parse(parameters.get<std::string>());
  }
  require(parameters.at("version") == 2 &&
              !parameters.value("support_qiskit", true),
          QDMI_ERROR_NOTSUPPORTED);
  const auto& pubs = parameters.at("pubs");
  require(pubs.is_array() && pubs.size() == 1, QDMI_ERROR_NOTSUPPORTED);
  const auto& pub = pubs.at(0);
  require(pub.is_array() && pub.size() == 3 && pub.at(0).is_string() &&
              (pub.at(1).is_null() || pub.at(1).empty()),
          QDMI_ERROR_NOTSUPPORTED);
  setProgram(pub.at(0).get<std::string>());
  shots = positiveInteger(pub.at(2));
  format = QDMI_PROGRAM_FORMAT_QASM3;
  id = remoteId;
  attempted = true;
  status = parseJobStatus(data);
}
QDMI_Job_Status Job::check(Deadline deadline) {
  if (!id.empty() && !terminal(status)) {
    const auto data =
        nlohmann::json::parse(auth->get("/v1/jobs/" + id, deadline));
    require(data.at("id") == id && data.at("backend") == backend);
    status = parseJobStatus(data);
  }
  return status;
}
void Job::cancel() {
  require(!id.empty(), QDMI_ERROR_BADSTATE);
  require(status != QDMI_JOB_STATUS_DONE, QDMI_ERROR_INVALIDARGUMENT);
  if (status == QDMI_JOB_STATUS_CANCELED) {
    return;
  }
  require(!terminal(status), QDMI_ERROR_BADSTATE);
  const auto response = auth->request("/v1/jobs/" + id + "/cancel", true);
  if (!response.failed && !response.timedOut && response.status == 204) {
    status = QDMI_JOB_STATUS_CANCELED;
    return;
  }
  if (!response.failed && !response.timedOut && response.status == 409) {
    check();
    require(status != QDMI_JOB_STATUS_DONE, QDMI_ERROR_INVALIDARGUMENT);
    require(status == QDMI_JOB_STATUS_CANCELED, QDMI_ERROR_BADSTATE);
    return;
  }
  checkResponse(response);
  throw Failure{QDMI_ERROR_FATAL};
}
const Results& Job::results() {
  const auto current = check();
  require(current != QDMI_JOB_STATUS_FAILED, QDMI_ERROR_FATAL);
  require(current == QDMI_JOB_STATUS_DONE, QDMI_ERROR_INVALIDARGUMENT);
  if (!cached) {
    const auto response = auth->request("/v1/jobs/" + id + "/results");
    require(response.failed || response.timedOut || response.status != 204,
            QDMI_ERROR_BADSTATE);
    checkResponse(response);
    auto data = nlohmann::json::parse(response.body);
    if (data.is_string()) {
      data = nlohmann::json::parse(data.get<std::string>());
    }
    cached = decodeResults(data, registers, shots);
  }
  return *cached;
}
} // namespace ibm
