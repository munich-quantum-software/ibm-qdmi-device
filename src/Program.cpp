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
#include <cctype>
#include <charconv>
#include <cstddef>
#include <ibm_qdmi/constants.h>
#include <limits>
#include <set>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

namespace ibm {
namespace {
void require(bool condition, int code = QDMI_ERROR_INVALIDARGUMENT) {
  if (!condition) {
    throw Failure{code};
  }
}
std::vector<std::string_view> tokenize(std::string_view source) {
  std::vector<std::string_view> tokens;
  for (std::size_t index = 0; index < source.size();) {
    const auto character = static_cast<unsigned char>(source[index]);
    if (std::isspace(character) != 0) {
      ++index;
    } else if (source.compare(index, 2, "//") == 0) {
      const auto end = source.find('\n', index + 2);
      index = end == std::string_view::npos ? source.size() : end;
    } else if (source.compare(index, 2, "/*") == 0) {
      const auto end = source.find("*/", index + 2);
      require(end != std::string_view::npos);
      index = end + 2;
    } else if (character == '"') {
      const auto start = index++;
      while (index < source.size() && source[index] != '"') {
        if (source[index] == '\\') {
          ++index;
        }
        ++index;
      }
      require(index < source.size());
      tokens.push_back(source.substr(start, ++index - start));
    } else if (std::isalnum(character) != 0 || character == '_') {
      const auto start = index++;
      while (index < source.size() &&
             (std::isalnum(static_cast<unsigned char>(source[index])) != 0 ||
              source[index] == '_' || source[index] == '.')) {
        ++index;
      }
      tokens.push_back(source.substr(start, index - start));
    } else {
      require(character != '@', QDMI_ERROR_NOTSUPPORTED);
      tokens.push_back(source.substr(index++, 1));
    }
  }
  return tokens;
}
std::size_t number(std::string_view token) {
  std::size_t result = 0;
  const auto parsed =
      std::from_chars(token.data(), token.data() + token.size(), result);
  require(parsed.ec == std::errc{} &&
          parsed.ptr == token.data() + token.size());
  return result;
}
bool name(std::string_view token) {
  return !token.empty() &&
         (std::isalpha(static_cast<unsigned char>(token.front())) != 0 ||
          token.front() == '_') &&
         std::ranges::all_of(token, [](unsigned char ch) {
           return std::isalnum(ch) != 0 || ch == '_';
         });
}
} // namespace

std::string declareNativeGates(std::string program) {
  const auto tokens = tokenize(program);
  require(tokens.size() >= 3);
  auto insertion =
      static_cast<std::size_t>(tokens[2].data() - program.data()) + 1;
  bool standardGates = false;
  std::set<std::string_view> definitions;
  std::set<std::string_view> calls;
  for (std::size_t index = 3; index < tokens.size(); ++index) {
    if (tokens[index] == "include" && index + 2 < tokens.size()) {
      standardGates |= tokens[index + 1] == "\"stdgates.inc\"";
      insertion =
          static_cast<std::size_t>(tokens[index + 2].data() - program.data()) +
          1;
    } else if (tokens[index] == "gate" && index + 1 < tokens.size()) {
      definitions.insert(tokens[++index]);
    } else if (index + 1 < tokens.size() &&
               (tokens[index - 1] == ";" || tokens[index - 1] == "{" ||
                tokens[index - 1] == "}") &&
               ((tokens[index] == "ecr" &&
                 (tokens[index + 1] == "$" || name(tokens[index + 1]))) ||
                (tokens[index] == "rzz" && tokens[index + 1] == "("))) {
      calls.insert(tokens[index]);
    }
  }
  std::string declarations = standardGates ? "" : "\ninclude \"stdgates.inc\";";
  if (calls.contains("ecr") && !definitions.contains("ecr")) {
    declarations += "\ngate ecr a,b { gphase(-pi/4); s a; sx b; cx a,b; x a; }";
  }
  if (calls.contains("rzz") && !definitions.contains("rzz")) {
    declarations += "\ngate rzz(theta) a,b { cx a,b; rz(theta) b; cx a,b; }";
  }
  if (!declarations.empty()) {
    program.insert(insertion, declarations + '\n');
  }
  return program;
}

std::vector<Register> outputRegisters(const std::string& program) {
  const auto tokens = tokenize(program);
  require(tokens.size() >= 3 && tokens[0] == "OPENQASM" &&
          (tokens[1] == "3" || tokens[1] == "3.0" || tokens[1] == "3.1") &&
          tokens[2] == ";");
  std::vector<Register> registers;
  std::set<std::string_view> names;
  std::size_t depth = 0;
  std::size_t width = 0;
  std::size_t cursor = 3;
  const auto next = [&]() -> std::string_view {
    require(cursor < tokens.size());
    return tokens[cursor++];
  };
  while (cursor < tokens.size()) {
    const auto token = next();
    if (token == "{") {
      ++depth;
    } else if (token == "}") {
      require(depth != 0);
      --depth;
    } else if (token == "include") {
      // Other includes could introduce classical registers outside this file.
      require(depth == 0 && next() == "\"stdgates.inc\"" && next() == ";",
              QDMI_ERROR_NOTSUPPORTED);
    } else if (token == "bit" || token == "creg") {
      const bool legacy = token == "creg";
      auto registerName = legacy ? next() : std::string_view{};
      const auto field = next();
      std::size_t count = 1;
      if (field == "[") {
        count = number(next());
        require(next() == "]");
        if (!legacy) {
          registerName = next();
        }
      } else {
        require(!legacy);
        registerName = field;
      }
      if (!legacy && registerName == "(") {
        continue; // A bit cast does not declare output storage.
      }
      require(depth == 0, QDMI_ERROR_NOTSUPPORTED);
      require(next() == ";" && count != 0 && name(registerName) &&
              names.insert(registerName).second &&
              count <= std::numeric_limits<std::size_t>::max() - width);
      width += count;
      registers.push_back({.name = std::string(registerName), .width = count});
    } else {
      require(token != "input" && token != "pragma", QDMI_ERROR_NOTSUPPORTED);
    }
  }
  require(depth == 0);
  require(!registers.empty(), QDMI_ERROR_NOTSUPPORTED);
  return registers;
}
} // namespace ibm
