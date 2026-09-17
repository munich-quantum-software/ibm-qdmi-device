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
#include <map>
#include <set>
#include <string>
#include <system_error>
#include <vector>

namespace ibm {
namespace {
void require(bool condition, int code = QDMI_ERROR_INVALIDARGUMENT) {
  if (!condition) {
    throw Failure{code};
  }
}
std::vector<std::string> tokenize(const std::string& source) {
  std::vector<std::string> tokens;
  for (std::size_t index = 0; index < source.size();) {
    const auto character = static_cast<unsigned char>(source[index]);
    if (std::isspace(character) != 0) {
      ++index;
    } else if (source.compare(index, 2, "//") == 0) {
      const auto end = source.find('\n', index + 2);
      index = end == std::string::npos ? source.size() : end;
    } else if (source.compare(index, 2, "/*") == 0) {
      const auto end = source.find("*/", index + 2);
      require(end != std::string::npos);
      index = end + 2;
    } else if (character == '"') {
      const auto end = source.find('"', index + 1);
      require(end != std::string::npos);
      tokens.push_back(source.substr(index, end - index + 1));
      index = end + 1;
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
      tokens.emplace_back(1, static_cast<char>(character));
      ++index;
    }
  }
  return tokens;
}
std::size_t number(const std::string& token) {
  std::size_t result = 0;
  const auto parsed =
      std::from_chars(token.data(), token.data() + token.size(), result);
  require(parsed.ec == std::errc{} &&
          parsed.ptr == token.data() + token.size());
  return result;
}
bool name(const std::string& token) {
  return !token.empty() &&
         (std::isalpha(static_cast<unsigned char>(token.front())) != 0 ||
          token.front() == '_') &&
         std::ranges::all_of(token, [](unsigned char ch) {
           return std::isalnum(ch) != 0 || ch == '_';
         });
}

void expression(const std::vector<std::string>& tokens, std::size_t& cursor,
                const std::set<std::string>& parameters = {}) {
  const std::set<std::string> constants{"pi",   "tau",    "euler",  "sin",
                                        "cos",  "tan",    "exp",    "ln",
                                        "sqrt", "arccos", "arcsin", "arctan"};
  int depth = 0;
  do {
    require(cursor < tokens.size());
    const auto& token = tokens[cursor++];
    if (token == "(") {
      ++depth;
    } else if (token == ")") {
      --depth;
    } else if (name(token)) {
      require(constants.contains(token) || parameters.contains(token),
              QDMI_ERROR_NOTSUPPORTED);
    } else {
      require(token != ";" && token != "{" && token != "}");
    }
  } while (depth > 0);
  require(depth == 0);
}

// Self-contained Qiskit exports declare native gates absent from stdgates.inc.
// Only static, unitary gate bodies are accepted; their local arguments cannot
// introduce classical storage or alter the top-level result layout.
void gateDefinition(const std::vector<std::string>& tokens, std::size_t& cursor,
                    std::set<std::string>& definitions) {
  const auto peek = [&]() -> const std::string& {
    require(cursor < tokens.size());
    return tokens[cursor];
  };
  ++cursor;
  require(name(peek()) && definitions.insert(peek()).second);
  ++cursor;
  std::set<std::string> parameters;
  const auto identifiers = [&](std::set<std::string>& values,
                               const std::string& end) {
    while (true) {
      require(name(peek()) && values.insert(peek()).second);
      ++cursor;
      if (peek() == end) {
        ++cursor;
        return;
      }
      require(peek() == ",");
      ++cursor;
    }
  };
  if (peek() == "(") {
    ++cursor;
    if (peek() == ")") {
      ++cursor;
    } else {
      identifiers(parameters, ")");
    }
  }
  std::set<std::string> qubits;
  identifiers(qubits, "{");
  require(std::ranges::none_of(
      qubits, [&](const auto& qubit) { return parameters.contains(qubit); }));
  const std::set<std::string> forbidden{
      "measure", "reset",  "bit",    "qubit",  "creg", "qreg",
      "input",   "output", "const",  "let",    "int",  "uint",
      "float",   "angle",  "bool",   "array",  "if",   "while",
      "for",     "switch", "def",    "extern", "gate", "defcal",
      "delay",   "box",    "pragma", "return", "end",  "include"};
  while (peek() != "}") {
    require(name(peek()) && !forbidden.contains(peek()),
            QDMI_ERROR_NOTSUPPORTED);
    ++cursor;
    if (peek() == "(") {
      expression(tokens, cursor, parameters);
    }
    while (true) {
      require(qubits.contains(peek()), QDMI_ERROR_NOTSUPPORTED);
      ++cursor;
      if (peek() == ";") {
        ++cursor;
        break;
      }
      require(peek() == ",");
      ++cursor;
    }
  }
  ++cursor;
}
} // namespace

std::vector<Register> outputRegisters(const std::string& program,
                                      std::size_t qubits) {
  const auto tokens = tokenize(program);
  require(tokens.size() >= 3 && tokens[0] == "OPENQASM" &&
          (tokens[1] == "3" || tokens[1] == "3.0") && tokens[2] == ";");
  std::map<std::string, std::size_t> classical;
  std::vector<Register> registers;
  std::set<std::string> definitions;
  std::string quantumRegister;
  bool measured = false;
  std::size_t width = 0;
  for (std::size_t cursor = 3; cursor < tokens.size();) {
    if (tokens[cursor] == "gate") {
      gateDefinition(tokens, cursor, definitions);
      continue;
    }
    const auto end =
        std::find(tokens.begin() + static_cast<std::ptrdiff_t>(cursor),
                  tokens.end(), ";");
    require(end != tokens.end());
    const std::vector<std::string> statement(
        tokens.begin() + static_cast<std::ptrdiff_t>(cursor), end);
    cursor += statement.size() + 1;
    require(!statement.empty());
    const auto& first = statement.front();
    if (first == "include") {
      require(statement.size() == 2 && statement[1] == "\"stdgates.inc\"",
              QDMI_ERROR_NOTSUPPORTED);
      continue;
    }
    if (first == "bit" || first == "creg" || first == "qubit" ||
        first == "qreg") {
      const bool legacy = first == "creg" || first == "qreg";
      const bool quantum = first == "qubit" || first == "qreg";
      std::string registerName;
      std::size_t count = 1;
      if (!legacy && statement.size() == 2) {
        registerName = statement[1];
      } else {
        require(statement.size() == 5);
        require(statement[legacy ? 2 : 1] == "[" &&
                statement[legacy ? 4 : 3] == "]");
        count = number(statement[legacy ? 3 : 2]);
        registerName = statement[legacy ? 1 : 4];
      }
      require(count != 0 && name(registerName));
      if (quantum) {
        require(quantumRegister.empty() && count == qubits,
                QDMI_ERROR_NOTSUPPORTED);
        require(!classical.contains(registerName));
        quantumRegister = registerName;
      } else {
        require(registerName != quantumRegister &&
                !classical.contains(registerName));
        require(count <= std::numeric_limits<std::size_t>::max() - width);
        width += count;
        classical.emplace(registerName, count);
        registers.push_back({.name = registerName, .width = count});
      }
      continue;
    }
    const std::set<std::string> unsupported{
        "input", "output", "const",  "let",    "int",  "uint",
        "float", "angle",  "bool",   "array",  "if",   "while",
        "for",   "switch", "def",    "extern", "gate", "defcal",
        "delay", "box",    "pragma", "return", "end"};
    require(!unsupported.contains(first), QDMI_ERROR_NOTSUPPORTED);
    std::size_t offset = 0;
    const auto reference = [&](bool quantum) {
      require(offset < statement.size());
      const auto& registerName = statement[offset++];
      if (quantum && registerName == "$") {
        require(offset < statement.size());
        require(number(statement[offset++]) < qubits);
        return;
      }
      const auto found = classical.find(registerName);
      require(quantum
                  ? !quantumRegister.empty() && registerName == quantumRegister
                  : found != classical.end());
      const auto count = quantum ? qubits : found->second;
      if (offset < statement.size() && statement[offset] == "[") {
        require(offset + 2 < statement.size() && statement[offset + 2] == "]");
        require(number(statement[offset + 1]) < count);
        offset += 3;
      } else {
        require(count == 1, QDMI_ERROR_NOTSUPPORTED);
      }
    };
    if (classical.contains(first)) {
      reference(false);
      require(offset < statement.size() && statement[offset] == "=");
      ++offset;
      require(offset < statement.size());
      if (statement[offset] == "measure") {
        ++offset;
        reference(true);
        measured = true;
      } else {
        require(statement[offset] == "false" || statement[offset] == "0",
                QDMI_ERROR_NOTSUPPORTED);
        ++offset;
      }
    } else if (first == "measure") {
      ++offset;
      reference(true);
      require(offset + 1 < statement.size() && statement[offset] == "-" &&
              statement[offset + 1] == ">");
      offset += 2;
      reference(false);
      measured = true;
    } else {
      require(name(first));
      ++offset;
      if (offset < statement.size() && statement[offset] == "(") {
        expression(statement, offset);
      }
      reference(true);
      while (offset < statement.size() && statement[offset] == ",") {
        ++offset;
        reference(true);
      }
    }
    require(offset == statement.size());
  }
  require(!registers.empty() && measured, QDMI_ERROR_NOTSUPPORTED);
  return registers;
}
} // namespace ibm
