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

#include <gtest/gtest.h>
#include <ibm_qdmi/constants.h>
#include <string>
#include <utility>
#include <vector>

namespace {
const std::string PROGRAM =
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

TEST(Program, PreservesDeclarationOrderAndPhysicalIndices) {
  const auto named = ibm::outputRegisters(
      "OPENQASM 3; bit[1] q; qubit[5] physical; q[0] = measure physical[4];",
      5);
  ASSERT_EQ(named.size(), 1);
  EXPECT_EQ(named[0].name, "q");
  const auto layout = ibm::outputRegisters(PROGRAM, 2);
  ASSERT_EQ(layout.size(), 2);
  EXPECT_EQ(layout[0].name, "z");
  EXPECT_EQ(layout[0].width, 2);
  EXPECT_EQ(layout[1].name, "a");
  EXPECT_EQ(ibm::outputRegisters("OPENQASM 3; // bit[9] ignored;\n bit[1] c; "
                                 "/* ignored */ x $119; c[0] = measure $119;",
                                 120)
                .size(),
            1);
  EXPECT_EQ(ibm::outputRegisters("OPENQASM 3; qreg q[2]; creg c[2]; rz(-pi/2) "
                                 "q[0]; measure q[0] -> c[1];",
                                 2)
                .at(0)
                .width,
            2);
}
TEST(Program, RejectsAmbiguousOrUnsupportedPrograms) {
  for (const auto* source :
       {"OPENQASM 2;", "OPENQASM 3; bit[0] c;", "OPENQASM 3; bit[2] c; bit c;",
        "OPENQASM 3; bit c; c = measure $2;", "OPENQASM 3; /* unterminated",
        "OPENQASM 3; bit c; c = measure $0",
        "OPENQASM 3; qubit[2] physical; bit physical;",
        "OPENQASM 3; bit physical; qubit[2] physical;"}) {
    fails([&] { (void)ibm::outputRegisters(source, 2); },
          QDMI_ERROR_INVALIDARGUMENT);
  }
  for (const auto* source :
       {"OPENQASM 3; qubit[1] q;", "OPENQASM 3; input float theta;",
        "OPENQASM 3; bit c; if (true) { c = measure $0; }",
        "OPENQASM 3; bit c; rz(theta) $0; c = measure $0;",
        "OPENQASM 3; bit c; c = true; c = measure $0;"}) {
    fails([&] { (void)ibm::outputRegisters(source, 2); },
          QDMI_ERROR_NOTSUPPORTED);
  }
}
TEST(Program, PreservesResultsAcrossStaticGateDefinitions) {
  const auto registers = ibm::outputRegisters(
      "OPENQASM 3; include \"stdgates.inc\"; "
      "gate rzz(theta) a,b { cx a,b; rz(theta) b; cx a,b; } "
      "qubit[5] q; bit[2] c; rzz(pi/4) q[3],q[4]; c[1] = measure q[4];",
      5);
  ASSERT_EQ(registers.size(), 1);
  EXPECT_EQ(registers[0].name, "c");
  EXPECT_EQ(registers[0].width, 2);
  for (const auto* program :
       {"OPENQASM 3; gate g a { bit c; c = measure a; } bit c; c = measure $0;",
        "OPENQASM 3; gate g a { rz(unbound) a; } bit c; c = measure $0;",
        "OPENQASM 3; gate g a { x outside; } bit c; c = measure $0;",
        "OPENQASM 3; gate g a { reset a; } bit c; c = measure $0;",
        "OPENQASM 3; gate g a { if (true) { x a; } } bit c; c = measure $0;"}) {
    fails([&] { (void)ibm::outputRegisters(program, 5); },
          QDMI_ERROR_NOTSUPPORTED);
  }
  for (const auto* program :
       {"OPENQASM 3; gate g a { x a;",
        "OPENQASM 3; gate g(p,p) a { rz(p) a; } bit c; c = measure $0;",
        "OPENQASM 3; gate g a { x a; } gate g a { x a; } bit c; c = measure "
        "$0;"}) {
    fails([&] { (void)ibm::outputRegisters(program, 5); },
          QDMI_ERROR_INVALIDARGUMENT);
  }
}
