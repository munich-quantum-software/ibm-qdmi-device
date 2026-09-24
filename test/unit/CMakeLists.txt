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

add_executable(
  unit_tests
  http_stub.cpp
  test_http_client.cpp
  test_ibm_api_config.cpp
  test_ibm_auth.cpp
  test_ibm_device.cpp
  test_jobs.cpp
  test_metadata.cpp
  test_program.cpp)
target_link_libraries(unit_tests PRIVATE ibm::qdmi_device_internals GTest::gtest_main)
target_compile_definitions(
  unit_tests PRIVATE IBM_QDMI_FIXTURE_FILE="${CMAKE_CURRENT_SOURCE_DIR}/../fixtures/backend.json")
gtest_discover_tests(unit_tests DISCOVERY_MODE PRE_TEST PROPERTIES LABELS unit DISCOVERY_TIMEOUT 60)
