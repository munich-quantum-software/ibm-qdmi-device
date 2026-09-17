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

get_filename_component(library_directory "${IBM_QDMI_LIBRARY}" DIRECTORY)
file(READ "${library_directory}/ibm-qdmi-device.qdmi.json" catalogue)
string(JSON version GET "${catalogue}" schema-version)
string(JSON count LENGTH "${catalogue}" qdmi devices)
if(NOT version EQUAL 1 OR NOT count EQUAL 3)
  message(FATAL_ERROR "Invalid installed catalogue")
endif()
foreach(index RANGE 0 2)
  string(
    JSON
    library
    GET
    "${catalogue}"
    qdmi
    devices
    ${index}
    library)
  if(IS_ABSOLUTE "${library}" OR NOT EXISTS "${library_directory}/${library}")
    message(FATAL_ERROR "Catalogue library does not resolve after relocation")
  endif()
  string(
    JSON
    prefix
    GET
    "${catalogue}"
    qdmi
    devices
    ${index}
    prefix)
  if(NOT prefix STREQUAL "IBM")
    message(FATAL_ERROR "Invalid catalogue prefix")
  endif()
endforeach()
