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

#include <fstream>
#include <gtest/gtest.h>
#include <ibm_qdmi/constants.h>
#include <ios>
#include <iterator>
#include <string>
#include <utility>
#include <vector>

namespace {
constexpr auto* PROGRAM =
    "OPENQASM 3.0; include \"stdgates.inc\"; qubit[2] q; "
    "bit[2] z; bit a; x q[1]; z[0] = measure q[1]; a = measure q[0];";
template <class Function> void fails(Function&& function, int expected) {
  try {
    std::forward<Function>(function)();
    FAIL() << "Expected a QDMI error";
  } catch (const ibm::Failure& error) {
    EXPECT_EQ(error.status, expected);
  }
}
} // namespace

TEST(Program, PreservesDeclarationOrderAcrossNativeInstructions) {
  const auto layout = ibm::outputRegisters(PROGRAM);
  ASSERT_EQ(layout.size(), 2);
  EXPECT_EQ(layout[0].name, "z");
  EXPECT_EQ(layout[0].width, 2);
  EXPECT_EQ(layout[1].name, "a");
  EXPECT_EQ(layout[1].width, 1);

  const auto registers = ibm::outputRegisters(
      "OPENQASM 3.1; include \"stdgates.inc\"; "
      "// bit[9] ignored;\n /* bit[8] ignored; */ "
      "gate rzz(theta) a,b { cx a,b; rz(theta) b; cx a,b; } "
      "qreg q[5]; bit[2] z; creg a[1]; gphase(pi/2); "
      "z[0] = measure q[4]; if (z[0]) { rzz(pi/4) q[3],q[4]; } "
      "else { x q[2]; } z = bit[2](uint[2](z)); measure q[3] -> a[0];");
  ASSERT_EQ(registers.size(), 2);
  EXPECT_EQ(registers[0].name, "z");
  EXPECT_EQ(registers[0].width, 2);
  EXPECT_EQ(registers[1].name, "a");
  EXPECT_EQ(registers[1].width, 1);
}

TEST(Program, RejectsAmbiguousOutputLayouts) {
  for (const auto* source : {
           "OPENQASM 2; bit c;",
           "OPENQASM 3; bit[0] c;",
           "OPENQASM 3; bit[2] c; bit c;",
           "OPENQASM 3; bit[18446744073709551616] c;",
           "OPENQASM 3; bit[18446744073709551615] c; bit d;",
           "OPENQASM 3; bit[2] c",
           "OPENQASM 3; bit[2 c;",
           "OPENQASM 3; /* unterminated",
           "OPENQASM 3; include \"unterminated",
           "OPENQASM 3; bit c; if (c) { x $0;",
       }) {
    fails([&] { (void)ibm::outputRegisters(source); },
          QDMI_ERROR_INVALIDARGUMENT);
  }
  for (const auto* source : {
           "OPENQASM 3; qubit[1] q;",
           "OPENQASM 3; input bit c;",
           "OPENQASM 3; bit c; if (c) { bit hidden; }",
           "OPENQASM 3; include \"registers.inc\"; bit c;",
           "OPENQASM 3; bit c; @annotation bit[2] hidden;\nc = measure $0;",
           "OPENQASM 3; bit c; pragma bit[2] hidden;\nc = measure $0;",
       }) {
    fails([&] { (void)ibm::outputRegisters(source); }, QDMI_ERROR_NOTSUPPORTED);
  }
}

TEST(Program, RejectsExplicitOutputs) {
  fails(
      [] {
        (void)ibm::outputRegisters(
            "OPENQASM 3; output bit result; bit internal; "
            "result = measure $0; internal = measure $1;");
      },
      QDMI_ERROR_NOTSUPPORTED);
}

TEST(Program, DeclaresBareNativeGatesWithoutRewritingSource) {
  const std::string program =
      "// ignored;\nOPENQASM /* ignored; */ 3;\nbit[2] c; "
      "ecr $3,$4; rzz(2.5e-1) $3,$4; "
      "c[1] = measure $3; c[0] = measure $4;";
  const auto prepared = ibm::declareNativeGates(program);
  EXPECT_NE(prepared.find("include \"stdgates.inc\";"), std::string::npos);
  EXPECT_NE(prepared.find("gate ecr"), std::string::npos);
  EXPECT_NE(prepared.find("gate rzz"), std::string::npos);
  EXPECT_TRUE(prepared.ends_with(program.substr(program.find("bit[2]"))));
  EXPECT_EQ(ibm::declareNativeGates(prepared), prepared);
  EXPECT_EQ(ibm::declareNativeGates(PROGRAM), PROGRAM);
  const std::string selfDeclared =
      "OPENQASM 3; gate x a { U(pi,0,pi) a; } bit c; x $0; c = measure $0;";
  EXPECT_EQ(ibm::declareNativeGates(selfDeclared), selfDeclared);
}

TEST(Qpy, ReadsQiskitFixturesAndPreservesBinaryTransport) {
  std::ifstream file(std::string(IBM_QDMI_QPY_FIXTURES) + "/v17.qpy",
                     std::ios::binary);
  const std::string program{std::istreambuf_iterator<char>(file), {}};
  ASSERT_FALSE(program.empty());
  const auto registers = ibm::qpyRegisters(program, 5);
  ASSERT_EQ(registers.size(), 2);
  EXPECT_EQ(registers[0].name, "z");
  EXPECT_EQ(registers[0].width, 2);
  EXPECT_EQ(registers[1].name, "a");
  EXPECT_EQ(ibm::decodeQpy(ibm::encodeQpy(program)), program);
  const std::string compressible(16384, 'x');
  EXPECT_EQ(ibm::decodeQpy(ibm::encodeQpy(compressible)), compressible);
  fails([&] { ibm::qpyRegisters(program.substr(0, 40), 5); },
        QDMI_ERROR_INVALIDARGUMENT);
  fails([&] { ibm::qpyRegisters(program, 1); }, QDMI_ERROR_INVALIDARGUMENT);
  auto invalid = program;
  invalid[6] = 16;
  fails([&] { ibm::qpyRegisters(invalid, 5); }, QDMI_ERROR_NOTSUPPORTED);
  invalid = program;
  invalid[49] = static_cast<char>(0xff);
  fails([&] { ibm::qpyRegisters(invalid, 5); }, QDMI_ERROR_INVALIDARGUMENT);
  fails([] { ibm::decodeQpy("invalid!"); }, QDMI_ERROR_INVALIDARGUMENT);
  fails([] { ibm::decodeQpy("AAAA"); }, QDMI_ERROR_INVALIDARGUMENT);
  // Nonzero padding bits must not alias a valid compressed payload.
  EXPECT_EQ(ibm::decodeQpy("eJyrqAAAAWoA8Q=="), "xx");
  fails([] { ibm::decodeQpy("eJyrqAAAAWoA8R=="); }, QDMI_ERROR_INVALIDARGUMENT);
}
