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
    FIND_PACKAGE_ARGS ${QDMI_VERSION})
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
  set(ZLIB_COMPAT ON)
  set(BUILD_TESTING OFF)
  FetchContent_Declare(
    zlib
    URL https://github.com/zlib-ng/zlib-ng/archive/2.3.3.tar.gz
    URL_HASH SHA256=f9c65aa9c852eb8255b636fd9f07ce1c406f061ec19a2e7d508b318ca0c907d1)
  FetchContent_Declare(
    cpr
    GIT_REPOSITORY https://github.com/libcpr/cpr.git
    GIT_TAG 1.15.1)
  if(APPLE)
    FetchContent_MakeAvailable(nlohmann_json zlib cpr)
  else()
    FetchContent_MakeAvailable(nlohmann_json zlib curl cpr)
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
      1.18.0
      CACHE STRING "GoogleTest version")
  FetchContent_Declare(
    googletest URL https://github.com/google/googletest/archive/refs/tags/v${GTEST_VERSION}.tar.gz
                   FIND_PACKAGE_ARGS ${GTEST_VERSION} NAMES GTest)
  FetchContent_MakeAvailable(googletest)
endif()
