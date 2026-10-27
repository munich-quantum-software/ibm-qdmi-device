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

#include <array>
#include <cstddef>
#include <cstdint>
#include <ibm_qdmi/constants.h>
#include <nlohmann/json.hpp>
#include <set>
#include <string>
#include <string_view>
#include <vector>
#include <zconf.h>
#include <zlib.h>

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
  require(version >= 13 && version <= 17, QDMI_ERROR_NOTSUPPORTED);
  reader.take(3);
  require(reader.integer(8) == 1, QDMI_ERROR_NOTSUPPORTED);
  const auto symbolic = reader.take(1);
  require(symbolic == "p" || symbolic == "e");
  require(reader.take(1) == "q", QDMI_ERROR_NOTSUPPORTED);
  if (version >= 16) {
    // A single-circuit file has one table entry immediately before its payload.
    require(reader.integer(8) == 28);
  }
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
    // shortcut: Reject aliases until result decoding preserves overlapping
    // registers.
    require(type != "c" || inCircuit != 0, QDMI_ERROR_NOTSUPPORTED);
    const std::string name(reader.take(length));
    require(!name.empty() && name.find('\0') == std::string::npos);
    try {
      (void)nlohmann::json(name).dump();
    } catch (const nlohmann::json::type_error&) {
      throw Failure{QDMI_ERROR_INVALIDARGUMENT};
    }
    if (type == "c" && inCircuit != 0) {
      require(size > 0 && size <= bits - next && names.insert(name).second,
              QDMI_ERROR_NOTSUPPORTED);
      for (std::uint64_t bit = 0; bit < size; ++bit) {
        require(reader.integer(8) == next++, QDMI_ERROR_NOTSUPPORTED);
      }
      registers.push_back(
          {.name = name, .width = static_cast<std::size_t>(size)});
    } else {
      for (std::uint64_t bit = 0; bit < size; ++bit) {
        const auto position = reader.integer(8);
        require(position == UINT64_MAX ||
                position < (type == "q" ? width : bits));
      }
    }
  }
  require(next == bits && !registers.empty(), QDMI_ERROR_NOTSUPPORTED);
  // Every supported circuit has at least a custom-definition header after
  // registers.
  reader.take(8);
  return registers;
}

std::string encodeQpy(const std::string& program) {
  require(!program.empty() && program.size() <= MAX_QPY_SIZE);
  auto size = compressBound(static_cast<uLong>(program.size()));
  std::vector<unsigned char> compressed(size);
  require(compress(compressed.data(), &size,
                   reinterpret_cast<const Bytef*>(program.data()),
                   static_cast<uLong>(program.size())) == Z_OK,
          QDMI_ERROR_FATAL);
  std::string encoded;
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
  for (std::size_t index = 0; index < encoded.size(); index += 4) {
    std::uint32_t word = 0;
    std::size_t padding = 0;
    for (std::size_t digit = 0; digit < 4; ++digit) {
      const auto character = encoded[index + digit];
      if (character == '=') {
        require(index + 4 == encoded.size() && digit >= 2);
        ++padding;
        word <<= 6U;
      } else {
        const auto value = BASE64.find(character);
        require(value != std::string_view::npos && padding == 0);
        word = (word << 6U) | static_cast<std::uint32_t>(value);
      }
    }
    require(padding == 0 || (word & (padding == 1 ? 255U : 65535U)) == 0);
    compressed.push_back(static_cast<unsigned char>(word >> 16U));
    if (padding < 2) {
      compressed.push_back(static_cast<unsigned char>(word >> 8U));
    }
    if (padding == 0) {
      compressed.push_back(static_cast<unsigned char>(word));
    }
  }
  z_stream stream{};
  require(inflateInit(&stream) == Z_OK, QDMI_ERROR_FATAL);
  struct Cleanup {
    z_stream* stream;
    ~Cleanup() { inflateEnd(stream); }
  };
  const Cleanup cleanup{.stream = &stream};
  stream.next_in = compressed.data();
  stream.avail_in = static_cast<uInt>(compressed.size());
  std::array<char, 16384> buffer{};
  std::string result;
  int status = Z_OK;
  while (status == Z_OK) {
    stream.next_out = reinterpret_cast<Bytef*>(buffer.data());
    stream.avail_out = static_cast<uInt>(buffer.size());
    status = inflate(&stream, Z_NO_FLUSH);
    const auto size = buffer.size() - stream.avail_out;
    require(size <= MAX_QPY_SIZE - result.size());
    result.append(buffer.data(), size);
  }
  require(status == Z_STREAM_END && stream.avail_in == 0);
  return result;
}
} // namespace ibm
