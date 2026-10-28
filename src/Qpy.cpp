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
#include "Job.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <ibm_qdmi/constants.h>
#include <nlohmann/json.hpp>
#include <set>
#include <string>
#include <string_view>
#include <vector>
#include <zlib-ng.h>

namespace ibm {
namespace {
constexpr std::string_view BASE64 =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
void require(bool condition, int code = QDMI_ERROR_INVALIDARGUMENT) {
  if (!condition) {
    throw Failure{code};
  }
}
class Reader {
public:
  explicit Reader(std::string_view source) : remaining(source) {}
  std::string_view take(std::size_t size) {
    require(size <= remaining.size());
    const auto result = remaining.substr(0, size);
    remaining.remove_prefix(size);
    return result;
  }
  std::uint64_t integer(std::size_t size) {
    std::uint64_t value = 0;
    for (const auto byte : take(size)) {
      value = (value << 8U) | static_cast<unsigned char>(byte);
    }
    return value;
  }

private:
  std::string_view remaining;
};
} // namespace

std::vector<Register> qpyRegisters(const std::string& program,
                                   std::size_t qubits) {
  require(program.size() <= MAX_QPY_SIZE);
  Reader reader(program);
  require(reader.take(6) == "QISKIT");
  const auto version = reader.integer(1);
  require(version == 17, QDMI_ERROR_NOTSUPPORTED);
  reader.take(3);
  require(reader.integer(8) == 1, QDMI_ERROR_NOTSUPPORTED);
  const auto symbolic = reader.take(1);
  require(symbolic == "p" || symbolic == "e");
  require(reader.take(1) == "q", QDMI_ERROR_NOTSUPPORTED);
  // A single-circuit file has one table entry immediately before its payload.
  require(reader.integer(8) == 28);
  const auto nameSize = reader.integer(2);
  reader.take(1);
  const auto phaseSize = reader.integer(2);
  const auto width = reader.integer(4);
  const auto bits = reader.integer(4);
  const auto metadataSize = reader.integer(8);
  const auto count = reader.integer(4);
  reader.take(8);
  require(reader.integer(4) == 0, QDMI_ERROR_NOTSUPPORTED);
  require(width > 0 && width <= qubits && bits > 0);
  reader.take(nameSize);
  reader.take(phaseSize);
  reader.take(metadataSize);
  std::vector<Register> registers;
  std::set<std::string> names;
  std::uint64_t next = 0;
  for (std::uint64_t index = 0; index < count; ++index) {
    const auto type = reader.take(1);
    require(type == "q" || type == "c");
    require(reader.integer(1) <= 1);
    const auto size = reader.integer(4);
    const auto length = reader.integer(2);
    const auto inCircuit = reader.integer(1);
    require(inCircuit <= 1);
    if (type == "q") {
      reader.take(length);
      reader.take(size * 8);
      continue;
    }
    // Classified results require a partition of the circuit's classical bits.
    require(inCircuit != 0, QDMI_ERROR_NOTSUPPORTED);
    const std::string name(reader.take(length));
    require(!name.empty() && name.find('\0') == std::string::npos);
    try {
      (void)nlohmann::json(name).dump();
    } catch (const nlohmann::json::type_error&) {
      throw Failure{QDMI_ERROR_INVALIDARGUMENT};
    }
    require(size > 0 && size <= bits - next && names.insert(name).second,
            QDMI_ERROR_NOTSUPPORTED);
    for (std::uint64_t bit = 0; bit < size; ++bit) {
      require(reader.integer(8) == next++, QDMI_ERROR_NOTSUPPORTED);
    }
    registers.push_back(
        {.name = name, .width = static_cast<std::size_t>(size)});
  }
  require(next == bits && !registers.empty(), QDMI_ERROR_NOTSUPPORTED);
  return registers;
}

std::string encodeQpy(const std::string& program) {
  require(!program.empty() && program.size() <= MAX_QPY_SIZE);
  auto size = zng_compressBound(program.size());
  std::vector<unsigned char> compressed(size);
  const auto status = zng_compress(
      compressed.data(), &size,
      reinterpret_cast<const std::uint8_t*>(program.data()), program.size());
  require(status != Z_MEM_ERROR, QDMI_ERROR_OUTOFMEM);
  require(status == Z_OK, QDMI_ERROR_FATAL);
  std::string encoded;
  encoded.reserve((size + 2) / 3 * 4);
  for (std::size_t index = 0; index < size; index += 3) {
    const auto remaining = size - index;
    const std::uint32_t word =
        (static_cast<std::uint32_t>(compressed[index]) << 16U) |
        (remaining > 1 ? static_cast<std::uint32_t>(compressed[index + 1]) << 8U
                       : 0U) |
        (remaining > 2 ? compressed[index + 2] : 0U);
    encoded += BASE64[(word >> 18U) & 63U];
    encoded += BASE64[(word >> 12U) & 63U];
    encoded += remaining > 1 ? BASE64[(word >> 6U) & 63U] : '=';
    encoded += remaining > 2 ? BASE64[word & 63U] : '=';
  }
  return encoded;
}

std::string decodeQpy(const std::string& encoded) {
  require(!encoded.empty() && encoded.size() % 4 == 0 &&
          encoded.size() <= 2 * MAX_QPY_SIZE);
  std::vector<unsigned char> compressed;
  compressed.reserve(encoded.size() / 4 * 3);
  auto padding = encoded.ends_with('=') ? 1U : 0U;
  if (encoded.ends_with("==")) {
    ++padding;
  }
  std::uint32_t word = 0;
  unsigned bits = 0;
  for (const auto character :
       std::string_view(encoded).substr(0, encoded.size() - padding)) {
    const auto value = BASE64.find(character);
    require(value != std::string_view::npos);
    word = (word << 6U) | static_cast<std::uint32_t>(value);
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      compressed.push_back(static_cast<unsigned char>(word >> bits));
    }
  }
  require((word & ((1U << bits) - 1)) == 0);
  std::string result(std::min(compressed.size(), MAX_QPY_SIZE / 4) * 4, '\0');
  while (true) {
    auto size = result.size();
    auto inputSize = compressed.size();
    const auto status =
        zng_uncompress2(reinterpret_cast<std::uint8_t*>(result.data()), &size,
                        compressed.data(), &inputSize);
    if (status == Z_OK) {
      require(inputSize == compressed.size());
      result.resize(size);
      return result;
    }
    require(status != Z_MEM_ERROR, QDMI_ERROR_OUTOFMEM);
    require(status == Z_BUF_ERROR && result.size() < MAX_QPY_SIZE);
    result.resize(std::min(result.size() * 2, MAX_QPY_SIZE));
  }
}
} // namespace ibm
