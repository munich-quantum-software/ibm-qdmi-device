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

#include "Job.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace ibm {
inline constexpr std::size_t MAX_QPY_SIZE = 64 * 1024 * 1024;
/// Read the output layout of one QPY 13–17 circuit without interpreting gates.
std::vector<Register> qpyRegisters(const std::string& program,
                                   std::size_t qubits);
/// Encode QPY using IBM's zlib-compressed, base64 transport.
std::string encodeQpy(const std::string& program);
/// Decode IBM's transport, limiting inflated programs to 64 MiB.
std::string decodeQpy(const std::string& encoded);
} // namespace ibm
