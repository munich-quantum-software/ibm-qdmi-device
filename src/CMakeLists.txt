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

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
generate_prefixed_qdmi_headers(${QDMI_PREFIX})

if(BUILD_IBM_QDMI_DOCS)
  if(QDMI_INCLUDE_BUILD_DIR)
    set(IBM_QDMI_UPSTREAM_HEADERS "${QDMI_INCLUDE_BUILD_DIR}/qdmi")
  else()
    set(IBM_QDMI_UPSTREAM_HEADERS "${qdmi_INCLUDE_DIR}/qdmi")
  endif()
  configure_file("${PROJECT_SOURCE_DIR}/docs/Doxyfile.in" "${PROJECT_BINARY_DIR}/Doxyfile" @ONLY)
endif()

add_library(ibm-qdmi-core STATIC Auth.cpp Http.cpp Metadata.cpp)
target_compile_features(ibm-qdmi-core PUBLIC cxx_std_20)
target_include_directories(ibm-qdmi-core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}"
                                                "${CMAKE_CURRENT_BINARY_DIR}/include")
target_link_libraries(
  ibm-qdmi-core
  PUBLIC cpr::cpr nlohmann_json::nlohmann_json
  PRIVATE qdmi::qdmi_project_warnings)
set_target_properties(ibm-qdmi-core PROPERTIES CXX_VISIBILITY_PRESET hidden
                                               VISIBILITY_INLINES_HIDDEN ON)

add_library(${QDMI_TARGET_NAME} SHARED Device.cpp)
add_library(ibm-qdmi-device::ibm-qdmi-device ALIAS ${QDMI_TARGET_NAME})
target_compile_features(${QDMI_TARGET_NAME} PRIVATE cxx_std_20)
target_compile_definitions(${QDMI_TARGET_NAME} PRIVATE IBM_QDMI_device_EXPORTS)
target_link_libraries(${QDMI_TARGET_NAME} PRIVATE ibm-qdmi-core qdmi::qdmi_project_warnings)
set_target_properties(
  ${QDMI_TARGET_NAME}
  PROPERTIES VERSION ${PROJECT_VERSION}
             SOVERSION ${PROJECT_VERSION_MAJOR}.${PROJECT_VERSION_MINOR}
             C_VISIBILITY_PRESET hidden
             CXX_VISIBILITY_PRESET hidden
             VISIBILITY_INLINES_HIDDEN ON)
target_sources(
  ${QDMI_TARGET_NAME}
  PUBLIC FILE_SET
         public_headers
         TYPE
         HEADERS
         BASE_DIRS
         "${CMAKE_CURRENT_BINARY_DIR}/include"
         "${PROJECT_SOURCE_DIR}/include"
         FILES
         "${CMAKE_CURRENT_BINARY_DIR}/include/ibm_qdmi/device.h"
         "${CMAKE_CURRENT_BINARY_DIR}/include/ibm_qdmi/constants.h"
         "${CMAKE_CURRENT_BINARY_DIR}/include/ibm_qdmi/types.h"
         "${CMAKE_CURRENT_BINARY_DIR}/include/ibm_qdmi/export.h")
target_sources(
  ${QDMI_TARGET_NAME} PUBLIC FILE_SET public_headers TYPE HEADERS FILES
                             "${PROJECT_SOURCE_DIR}/include/ibm-qdmi-device/constants.h")

if(IBM_QDMI_ENABLE_COVERAGE)
  target_link_libraries(ibm-qdmi-core PRIVATE qdmi::qdmi_coverage_flags)
  target_link_libraries(${QDMI_TARGET_NAME} PRIVATE qdmi::qdmi_coverage_flags)
endif()

set(IBM_QDMI_CONFIG_INSTALL_DIR "${CMAKE_INSTALL_DATADIR}/cmake/${QDMI_TARGET_NAME}")
configure_package_config_file(
  "${PROJECT_SOURCE_DIR}/cmake/${QDMI_TARGET_NAME}-config.cmake.in"
  "${CMAKE_CURRENT_BINARY_DIR}/${QDMI_TARGET_NAME}-config.cmake"
  INSTALL_DESTINATION ${IBM_QDMI_CONFIG_INSTALL_DIR}
  NO_SET_AND_CHECK_MACRO NO_CHECK_REQUIRED_COMPONENTS_MACRO)
write_basic_package_version_file(
  "${CMAKE_CURRENT_BINARY_DIR}/${QDMI_TARGET_NAME}-config-version.cmake"
  VERSION ${PROJECT_VERSION}
  COMPATIBILITY SameMinorVersion)
install(
  FILES "${CMAKE_CURRENT_BINARY_DIR}/${QDMI_TARGET_NAME}-config.cmake"
        "${CMAKE_CURRENT_BINARY_DIR}/${QDMI_TARGET_NAME}-config-version.cmake"
  DESTINATION ${IBM_QDMI_CONFIG_INSTALL_DIR}
  COMPONENT ${QDMI_TARGET_NAME}_Development)
install(
  TARGETS ${QDMI_TARGET_NAME}
  EXPORT ${QDMI_TARGET_NAME}-targets
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR} COMPONENT ${QDMI_TARGET_NAME}_Runtime
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
          COMPONENT ${QDMI_TARGET_NAME}_Runtime
          NAMELINK_COMPONENT ${QDMI_TARGET_NAME}_Development
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
          COMPONENT ${QDMI_TARGET_NAME}_Development
          FILE_SET public_headers
          DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
          COMPONENT ${QDMI_TARGET_NAME}_Development)
install(
  EXPORT ${QDMI_TARGET_NAME}-targets
  NAMESPACE ibm-qdmi-device::
  DESTINATION ${IBM_QDMI_CONFIG_INSTALL_DIR}
  COMPONENT ${QDMI_TARGET_NAME}_Development)
