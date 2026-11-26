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
  # Use QDMI develop for the exported CMake target version.
  set(QDMI_REV
      "d336c4ca6e972201f49b834da7d57dcb550f59f7"
      CACHE STRING "QDMI identifier (tag, branch or commit hash)")
  set(QDMI_REPO_OWNER
      "Munich-Quantum-Software-Stack"
      CACHE STRING "QDMI repository owner")
  set(INSTALL_QDMI
      OFF
      CACHE BOOL "Install the upstream QDMI package")
  FetchContent_Declare(
    qdmi
    GIT_REPOSITORY https://github.com/${QDMI_REPO_OWNER}/qdmi.git
    GIT_TAG ${QDMI_REV})
  FetchContent_MakeAvailable(qdmi)

  # renovate: datasource=github-releases depName=nlohmann/json
  set(JSON_TAG v3.12.0)
  string(REGEX REPLACE "^v" "" JSON_VERSION "${JSON_TAG}")
  FetchContent_Declare(
    nlohmann_json URL https://github.com/nlohmann/json/releases/download/${JSON_TAG}/json.tar.xz
                      FIND_PACKAGE_ARGS ${JSON_VERSION})
  set(JSON_SystemInclude
      ON
      CACHE INTERNAL "Treat JSON headers as system headers")
  set(CPR_BUILD_TESTS
      OFF
      CACHE BOOL "Disable CPR tests" FORCE)
  if(APPLE)
    if(NOT TARGET CURL::libcurl)
      # Prefer the SDK curl over an optional Homebrew installation.
      set(_curl_sdk "${CMAKE_OSX_SYSROOT}")
      if(NOT _curl_sdk)
        set(_curl_sdk macosx)
      endif()
      if(NOT IS_DIRECTORY "${_curl_sdk}")
        execute_process(
          COMMAND xcrun --sdk "${_curl_sdk}" --show-sdk-path
          OUTPUT_VARIABLE _curl_sdk
          OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
      endif()
      add_library(CURL::libcurl UNKNOWN IMPORTED)
      set_target_properties(
        CURL::libcurl PROPERTIES IMPORTED_LOCATION "${_curl_sdk}/usr/lib/libcurl.tbd"
                                 INTERFACE_INCLUDE_DIRECTORIES "${_curl_sdk}/usr/include")
    endif()
  else()
    if(UNIX)
      find_package(OpenSSL 3 REQUIRED)
    endif()
    set(BUILD_CURL_EXE OFF)
    set(CURL_DISABLE_INSTALL ON)
    foreach(
      PROTOCOL
      DICT
      FILE
      FTP
      GOPHER
      IMAP
      IPFS
      LDAP
      LDAPS
      MQTT
      POP3
      RTSP
      SMTP
      TELNET
      TFTP
      WEBSOCKETS)
      set(CURL_DISABLE_${PROTOCOL} ON)
    endforeach()
    set(CURL_USE_OPENSSL ${UNIX})
    set(CURL_USE_SCHANNEL ${WIN32})
    set(CURL_USE_LIBSSH2 OFF)
    set(USE_LIBIDN2 OFF)
    set(CURL_USE_LIBPSL OFF)
    set(CURL_ZLIB OFF)
    FetchContent_Declare(
      curl
      URL https://github.com/curl/curl/releases/download/curl-8_23_0/curl-8.23.0.tar.xz
      URL_HASH SHA256=8dadd7d2536a314f982ad05a651b713f426bf7d02cc2c76cffb9796f2218e6c5)
  endif()
  set(CPR_ENABLE_INSTALL OFF)
  set(CPR_USE_EXISTING_CURL_TARGET ON)
  set(CPR_FORCE_OPENSSL_BACKEND OFF)
  set(CPR_CURL_NOSIGNAL ON)
  set(BUILD_SHARED_LIBS OFF)
  set(ZLIB_COMPAT OFF)
  set(BUILD_TESTING OFF)
  FetchContent_Declare(
    zlib
    URL https://github.com/zlib-ng/zlib-ng/archive/2.3.3.tar.gz
    URL_HASH SHA256=f9c65aa9c852eb8255b636fd9f07ce1c406f061ec19a2e7d508b318ca0c907d1)
  # renovate: datasource=github-tags depName=libcpr/cpr
  set(CPR_REV "3139b2682f0b1d6af8c7ae48cf400f9d9988deec" # tag=1.15.1
  )
  FetchContent_Declare(
    cpr
    GIT_REPOSITORY https://github.com/libcpr/cpr.git
    GIT_TAG ${CPR_REV})
  if(APPLE)
    FetchContent_MakeAvailable(nlohmann_json zlib cpr)
  else()
    FetchContent_MakeAvailable(nlohmann_json zlib curl cpr)
  endif()
  # Build only S3; the device uses its signer and retains its own HTTP transport.
  set(BUILD_ONLY
      "s3"
      CACHE STRING "AWS services" FORCE)
  set(ENABLE_TESTING
      OFF
      CACHE BOOL "Disable AWS tests" FORCE)
  set(USE_CRT_HTTP_CLIENT
      ON
      CACHE BOOL "Use CRT for SDK initialization without a second curl" FORCE)
  set(NO_HTTP_CLIENT
      OFF
      CACHE BOOL "SDK initialization requires a client factory" FORCE)
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
  if(CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND CMAKE_CXX_SIMULATE_ID STREQUAL "MSVC")
    # The SDK's clang-cl AVX512 flags omit crc32 needed by this fallback.
    set_property(
      SOURCE
        "${aws_sdk_SOURCE_DIR}/crt/aws-crt-cpp/crt/aws-checksums/source/intel/intrin/crc32c_sse42_avx512.c"
        TARGET_DIRECTORY
        aws-checksums
      APPEND
      PROPERTY COMPILE_OPTIONS "/clang:-mcrc32")
  endif()
  # Ship only the device's install components, not the private SDK's headers.
  set_property(DIRECTORY "${aws_sdk_SOURCE_DIR}" PROPERTY EXCLUDE_FROM_ALL YES)
endif()

if(BUILD_IBM_QDMI_TESTS)
  set(GTEST_VERSION
      1.18.0
      CACHE STRING "Minimum installed GoogleTest version")
  # renovate: datasource=github-tags depName=google/googletest
  set(GTEST_REV
      "063de7e9578f82b369302001269680b4b1553359" # tag=v1.18.0
      CACHE STRING "GoogleTest source revision")
  FetchContent_Declare(
    googletest URL https://github.com/google/googletest/archive/${GTEST_REV}.tar.gz
                   EXCLUDE_FROM_ALL FIND_PACKAGE_ARGS ${GTEST_VERSION} NAMES GTest)
  FetchContent_MakeAvailable(googletest)
endif()
