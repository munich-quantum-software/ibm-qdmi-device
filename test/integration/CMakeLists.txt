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

add_executable(integration_tests headers.c test_ibm_device_integration.cpp)

target_compile_features(integration_tests PRIVATE cxx_std_20)
target_link_libraries(integration_tests PRIVATE ibm-qdmi-device::ibm-qdmi-device GTest::gtest_main)
if(WIN32)
  add_custom_command(
    TARGET integration_tests
    POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different $<TARGET_FILE:ibm-qdmi-device::ibm-qdmi-device>
            $<TARGET_FILE_DIR:integration_tests>)
endif()
gtest_discover_tests(integration_tests DISCOVERY_MODE PRE_TEST PROPERTIES LABELS integration
                                                                          DISCOVERY_TIMEOUT 60)
