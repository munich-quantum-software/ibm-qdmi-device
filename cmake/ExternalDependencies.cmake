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
  if(WIN32)
    # Both curl and AWS read this legacy option; use Windows crypto by default.
    set(USE_OPENSSL
        OFF
        CACHE BOOL "Use OpenSSL for AWS crypto" FORCE)
  endif()
  set(ENABLE_COVERAGE ${IBM_QDMI_ENABLE_COVERAGE})
  set(QDMI_MINIMUM_VERSION
      1.4.0
      CACHE STRING "Minimum QDMI version")
  set(QDMI_VERSION
      1.4.0
      CACHE STRING "QDMI version")
  set(QDMI_REV
      "6db03d83ad602aaa9fe928b5c3fc5cce84b10061"
      CACHE STRING "QDMI revision (v1.4.0)")
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
  # Build only S3; the device uses its signer and retains its own HTTP transport.
  set(BUILD_ONLY
      "s3"
      CACHE STRING "AWS services" FORCE)
  set(ENABLE_TESTING
      OFF
      CACHE BOOL "Disable AWS tests" FORCE)
  set(USE_CRT_HTTP_CLIENT
      ON
      CACHE BOOL "Avoid a second curl dependency in the signing SDK" FORCE)
  set(AUTORUN_UNIT_TESTS
      OFF
      CACHE BOOL "Disable AWS test execution" FORCE)
  set(BUILD_OPTEL
      OFF
      CACHE BOOL "Disable AWS telemetry" FORCE)
  set(ENABLE_UNITY_BUILD
      ON
      CACHE BOOL "Reduce AWS compilation time" FORCE)
  set(AWS_SDK_WARNINGS_ARE_ERRORS
      OFF
      CACHE BOOL "Keep vendor warnings visible" FORCE)
  FetchContent_Declare(
    aws_sdk
    GIT_REPOSITORY https://github.com/aws/aws-sdk-cpp.git
    GIT_TAG 1.11.700 # c9374f0f1f12b6817cb46bb38f298bef6738ada3
    GIT_SHALLOW TRUE)
  FetchContent_MakeAvailable(aws_sdk)
  # Ship only the device's install components, not the private SDK's headers.
  set_property(DIRECTORY "${aws_sdk_SOURCE_DIR}" PROPERTY EXCLUDE_FROM_ALL YES)
  if(TARGET zlib AND NOT TARGET ZLIB::ZLIB)
    add_library(ZLIB::ZLIB ALIAS zlib)
  elseif(NOT TARGET ZLIB::ZLIB)
    find_package(ZLIB REQUIRED)
  endif()
  if(CMAKE_CXX_COMPILER_ID STREQUAL "Clang"
     AND CMAKE_CXX_SIMULATE_ID STREQUAL "MSVC"
     AND TARGET cpr)
    get_target_property(IBM_QDMI_CPR_IMPORTED cpr IMPORTED)
    if(NOT IBM_QDMI_CPR_IMPORTED)
      # CPR 1.14.2 treats clang-cl as Unix Clang, combining /Wall with -Werror. Keep its diagnostics
      # visible without failing the dependency build.
      target_compile_options(cpr PRIVATE -Wno-error)
    endif()
  endif()
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
  if(CMAKE_CXX_COMPILER_ID STREQUAL "Clang"
     AND CMAKE_CXX_SIMULATE_ID STREQUAL "MSVC"
     AND CMAKE_CXX_COMPILER_VERSION VERSION_GREATER_EQUAL 22)
    # GoogleTest 1.17.0 uses /WX; Clang 22 diagnoses its char8_t printer. Apply this only to built
    # dependency targets, including GoogleMock's copies of gtest-all.cc, without changing warnings
    # for consumers.
    foreach(IBM_QDMI_GTEST_TARGET IN ITEMS gtest gtest_main gmock gmock_main)
      if(TARGET ${IBM_QDMI_GTEST_TARGET})
        get_target_property(IBM_QDMI_GTEST_IMPORTED ${IBM_QDMI_GTEST_TARGET} IMPORTED)
        if(NOT IBM_QDMI_GTEST_IMPORTED)
          target_compile_options(${IBM_QDMI_GTEST_TARGET} PRIVATE -Wno-error=character-conversion)
        endif()
      endif()
    endforeach()
  endif()
endif()
