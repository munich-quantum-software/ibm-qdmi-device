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

add_executable(ibm-qdmi-package-tests headers.c test_package.cpp)
target_compile_features(ibm-qdmi-package-tests PRIVATE cxx_std_20)
target_link_libraries(ibm-qdmi-package-tests PRIVATE ibm-qdmi-device::ibm-qdmi-device
                                                     GTest::gtest_main)
if(WIN32)
  add_custom_command(
    TARGET ibm-qdmi-package-tests
    POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different $<TARGET_FILE:ibm-qdmi-device::ibm-qdmi-device>
            $<TARGET_FILE_DIR:ibm-qdmi-package-tests>)
endif()
gtest_discover_tests(ibm-qdmi-package-tests DISCOVERY_MODE PRE_TEST)

if(NOT USE_INSTALLED_IBM_QDMI_DEVICE)
  add_executable(ibm-qdmi-backend-tests test_backend.cpp)
  target_link_libraries(ibm-qdmi-backend-tests PRIVATE ibm-qdmi-core GTest::gtest_main)
  target_compile_definitions(
    ibm-qdmi-backend-tests
    PRIVATE IBM_QDMI_FIXTURE_FILE="${CMAKE_CURRENT_SOURCE_DIR}/fixtures/backend.json")
  if(IBM_QDMI_ENABLE_COVERAGE)
    target_link_libraries(ibm-qdmi-backend-tests PRIVATE qdmi::qdmi_coverage_flags)
  endif()
  gtest_discover_tests(ibm-qdmi-backend-tests DISCOVERY_MODE PRE_TEST)
endif()
