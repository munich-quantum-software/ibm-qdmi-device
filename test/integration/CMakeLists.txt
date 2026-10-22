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

foreach(property QDMI_DEVICE_ID QDMI_DEVICE_PREFIX QDMI_MANIFEST_NAME)
  get_target_property(value ibm-qdmi-device::ibm-qdmi-device ${property})
  if(NOT value)
    message(FATAL_ERROR "Missing exported device property ${property}")
  endif()
endforeach()
get_target_property(device_id ibm-qdmi-device::ibm-qdmi-device QDMI_DEVICE_ID)
get_target_property(device_prefix ibm-qdmi-device::ibm-qdmi-device QDMI_DEVICE_PREFIX)
if(NOT device_id STREQUAL "ibm.default" OR NOT device_prefix STREQUAL "IBM")
  message(FATAL_ERROR "Unexpected QDMI device identity")
endif()
add_test(
  NAME Package.Catalogue
  COMMAND ${CMAKE_COMMAND} "-DIBM_QDMI_LIBRARY=$<TARGET_FILE:ibm-qdmi-device::ibm-qdmi-device>" -P
          "${CMAKE_CURRENT_SOURCE_DIR}/../catalogue.cmake")
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

add_executable(ibm-qdmi-native-example "${PROJECT_SOURCE_DIR}/examples/native/execute.c")
target_compile_features(ibm-qdmi-native-example PRIVATE c_std_17)
target_link_libraries(ibm-qdmi-native-example PRIVATE ibm-qdmi-device::ibm-qdmi-device)
