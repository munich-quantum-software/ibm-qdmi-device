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
set(package ibm-qdmi-device)
get_filename_component(source "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
set(work "${source}/build/install-check")
string(
  RANDOM
  LENGTH 8
  ALPHABET 0123456789abcdef suffix)
set(prefix "${work}/prefix-${suffix}")
set(relocated "${work}/relocated-${suffix}")
set(consumer "${work}/consumer")

function(run)
  execute_process(COMMAND ${ARGV} COMMAND_ERROR_IS_FATAL ANY)
endfunction()

run("${CMAKE_COMMAND}"
    -S
    "${source}"
    -B
    "${work}/producer"
    -DCMAKE_BUILD_TYPE=Release
    -DBUILD_IBM_QDMI_TESTS=OFF)
run("${CMAKE_COMMAND}" --build "${work}/producer" --config Release)
foreach(component Runtime Development)
  run("${CMAKE_COMMAND}"
      --install
      "${work}/producer"
      --config
      Release
      --prefix
      "${prefix}"
      --component
      "${package}_${component}")
endforeach()
file(RENAME "${prefix}" "${relocated}")

file(
  WRITE "${consumer}/main.c"
  [=[
#include "ibm_qdmi/device.h"

int main(void) {
  return IBM_QDMI_device_initialize() != QDMI_SUCCESS ||
         IBM_QDMI_device_finalize() != QDMI_SUCCESS;
}
]=])
file(
  CONFIGURE
  OUTPUT
  "${consumer}/CMakeLists.txt"
  CONTENT
  [=[
cmake_minimum_required(VERSION 3.24)
project(installed-consumer LANGUAGES C)
find_package(@package@ REQUIRED CONFIG PATHS "@relocated@" NO_DEFAULT_PATH)
add_executable(consumer main.c)
target_compile_features(consumer PRIVATE c_std_11)
target_link_libraries(consumer PRIVATE ibm-qdmi-device::ibm-qdmi-device)
if(WIN32)
  add_custom_command(TARGET consumer POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      $<TARGET_FILE:ibm-qdmi-device::ibm-qdmi-device> $<TARGET_FILE_DIR:consumer>)
endif()
enable_testing()
add_test(NAME installed-consumer COMMAND consumer)
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
          "@source@/test/catalogue.cmake")
]=]
  @ONLY)
run("${CMAKE_COMMAND}" -S "${consumer}" -B "${work}/consumer-${suffix}" -DCMAKE_BUILD_TYPE=Release)
run("${CMAKE_COMMAND}" --build "${work}/consumer-${suffix}" --config Release)
run("${CMAKE_CTEST_COMMAND}"
    --test-dir
    "${work}/consumer-${suffix}"
    -C
    Release
    --output-on-failure
    --no-tests=error)
