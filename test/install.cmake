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
get_filename_component(source "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
set(work "${source}/build/install")
if(NOT DEFINED IBM_QDMI_INSTALL_TEST_CONFIG)
  set(IBM_QDMI_INSTALL_TEST_CONFIG Release)
endif()

function(run)
  execute_process(COMMAND ${ARGV} COMMAND_ERROR_IS_FATAL ANY)
endfunction()

# Each run uses a fresh prefix so that stale artifacts cannot satisfy checks.
string(
  RANDOM
  LENGTH 10
  ALPHABET 0123456789abcdef suffix)
set(prefix "${work}/prefix-${suffix}")
set(relocated "${work}/relocated-${suffix}")
run("${CMAKE_COMMAND}"
    -S
    "${source}"
    -B
    "${work}/producer"
    "-DCMAKE_BUILD_TYPE=${IBM_QDMI_INSTALL_TEST_CONFIG}"
    -DBUILD_IBM_QDMI_TESTS=OFF)
run("${CMAKE_COMMAND}" --build "${work}/producer" --config "${IBM_QDMI_INSTALL_TEST_CONFIG}")
foreach(component Runtime Development)
  run("${CMAKE_COMMAND}"
      --install
      "${work}/producer"
      --config
      "${IBM_QDMI_INSTALL_TEST_CONFIG}"
      --prefix
      "${prefix}"
      --component
      "ibm-qdmi-device_${component}")
endforeach()
file(RENAME "${prefix}" "${relocated}")
run("${CMAKE_COMMAND}"
    -S
    "${source}"
    -B
    "${work}/consumer-${suffix}"
    "-DCMAKE_BUILD_TYPE=${IBM_QDMI_INSTALL_TEST_CONFIG}"
    -DUSE_INSTALLED_IBM_QDMI_DEVICE=ON
    -DBUILD_IBM_QDMI_TESTS=ON
    "-DCMAKE_PREFIX_PATH=${relocated}")
run("${CMAKE_COMMAND}" --build "${work}/consumer-${suffix}" --config
    "${IBM_QDMI_INSTALL_TEST_CONFIG}")
run("${CMAKE_CTEST_COMMAND}" --test-dir "${work}/consumer-${suffix}" -C
    "${IBM_QDMI_INSTALL_TEST_CONFIG}" --output-on-failure)
