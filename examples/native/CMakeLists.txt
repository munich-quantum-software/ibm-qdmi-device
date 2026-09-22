# Copyright (c) 2026 Munich Quantum Software Company GmbH
# All rights reserved.
#
# Licensed under the Apache License v2.0 with LLVM Exceptions (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://llvm.org/LICENSE.txt
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
#
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception

cmake_minimum_required(VERSION 3.24)
project(ibm-qdmi-native-example LANGUAGES C)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
find_package(ibm-qdmi-device REQUIRED CONFIG)
add_executable(ibm-qdmi-execute execute.c)
target_compile_features(ibm-qdmi-execute PRIVATE c_std_17)
target_link_libraries(ibm-qdmi-execute PRIVATE ibm-qdmi-device::ibm-qdmi-device)

if(WIN32)
  add_custom_command(
    TARGET ibm-qdmi-execute
    POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different $<TARGET_FILE:ibm-qdmi-device::ibm-qdmi-device>
            $<TARGET_FILE_DIR:ibm-qdmi-execute>)
endif()

enable_testing()
add_test(NAME NativeExample.Help COMMAND ibm-qdmi-execute --help)
