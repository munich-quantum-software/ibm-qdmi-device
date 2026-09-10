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

include(FetchContent)
include(GNUInstallDirs)

if(NOT USE_INSTALLED_IBM_QDMI_DEVICE)
  set(ENABLE_COVERAGE ${IBM_QDMI_ENABLE_COVERAGE})
  set(QDMI_MINIMUM_VERSION
      1.3.3
      CACHE STRING "Minimum QDMI version")
  set(QDMI_VERSION
      1.3.3
      CACHE STRING "QDMI version")
  set(QDMI_REV
      "18cfb67fd9042761d3005c2f8655751c1758f9c5"
      CACHE STRING "QDMI revision (v1.3.3)")
  set(QDMI_REPO_OWNER
      "Munich-Quantum-Software-Stack"
      CACHE STRING "QDMI repository owner")
  set(INSTALL_QDMI
      OFF
      CACHE BOOL "Install the upstream QDMI package")
  FetchContent_Declare(
    qdmi
    GIT_REPOSITORY https://github.com/${QDMI_REPO_OWNER}/qdmi.git
    GIT_TAG ${QDMI_REV}
    FIND_PACKAGE_ARGS ${QDMI_MINIMUM_VERSION})
  FetchContent_MakeAvailable(qdmi)

  FetchContent_Declare(
    nlohmann_json URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
                      FIND_PACKAGE_ARGS 3.12.0)
  set(JSON_SystemInclude
      ON
      CACHE INTERNAL "Treat JSON headers as system headers")
  set(CPR_BUILD_TESTS
      OFF
      CACHE BOOL "Disable CPR tests" FORCE)
  set(CPR_CURL_USE_LIBPSL
      OFF
      CACHE BOOL "Disable libpsl" FORCE)
  set(CPR_USE_SYSTEM_CURL
      OFF
      CACHE BOOL "Use system curl for CPR")
  set(BUILD_STATIC_CURL
      ON
      CACHE BOOL "Build static curl" FORCE)
  set(BUILD_SHARED_LIBS
      OFF
      CACHE BOOL "Build static dependencies" FORCE)
  FetchContent_Declare(
    cpr
    GIT_REPOSITORY https://github.com/libcpr/cpr.git
    GIT_TAG 1.14.2
    FIND_PACKAGE_ARGS 1.14.2)
  FetchContent_MakeAvailable(nlohmann_json cpr)
endif()

if(BUILD_IBM_QDMI_TESTS)
  set(gtest_force_shared_crt
      ON
      CACHE BOOL "Use the shared runtime" FORCE)
  set(INSTALL_GTEST
      OFF
      CACHE BOOL "Do not install GoogleTest" FORCE)
  set(GTEST_VERSION
      1.17.0
      CACHE STRING "GoogleTest version")
  FetchContent_Declare(
    googletest URL https://github.com/google/googletest/archive/refs/tags/v${GTEST_VERSION}.tar.gz
                   FIND_PACKAGE_ARGS ${GTEST_VERSION} NAMES GTest)
  FetchContent_MakeAvailable(googletest)
endif()
