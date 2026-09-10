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

cmake_minimum_required(VERSION 3.24...4.4)
project(
  ibm-qdmi-device
  VERSION 0.1.0
  LANGUAGES C CXX
  DESCRIPTION "IBM QDMI Device")

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE
      Release
      CACHE STRING "Choose the type of build." FORCE)
  set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS Debug Release MinSizeRel RelWithDebInfo)
endif()

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
# There are no C++ modules; keep the compilation database usable before a build.
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)
set(CMAKE_VERIFY_INTERFACE_HEADER_SETS ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(QDMI_PREFIX IBM)
set(QDMI_TARGET_NAME ibm-qdmi-device)

option(BUILD_IBM_QDMI_TESTS "Build offline packaging tests" ${PROJECT_IS_TOP_LEVEL})
option(USE_INSTALLED_IBM_QDMI_DEVICE "Build tests against an installed package" OFF)
option(IBM_QDMI_ENABLE_COVERAGE "Enable native coverage reporting" OFF)
option(BUILD_IBM_QDMI_DOCS "Configure the native API documentation" OFF)

if(BUILD_IBM_QDMI_DOCS AND USE_INSTALLED_IBM_QDMI_DEVICE)
  message(FATAL_ERROR "Documentation requires a source build")
endif()

include(cmake/Sanitizers.cmake)
ibm_qdmi_apply_sanitizers()
include(cmake/ExternalDependencies.cmake)

if(USE_INSTALLED_IBM_QDMI_DEVICE)
  find_package(ibm-qdmi-device ${PROJECT_VERSION} REQUIRED CONFIG)
else()
  add_subdirectory(src)
endif()

if(BUILD_IBM_QDMI_TESTS)
  enable_testing()
  include(GoogleTest)
  add_subdirectory(test)
endif()
