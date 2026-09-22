/*
 * Copyright (c) 2026 Munich Quantum Software Company GmbH
 * All rights reserved.
 *
 * Licensed under the Apache License v2.0 with LLVM Exceptions (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * https://llvm.org/LICENSE.txt
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 *
 * SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
 */

#pragma once

#include <ibm_qdmi/constants.h>

/// Null-terminated backend name; defaults to IBM_QUANTUM_BACKEND.
#define IBM_QDMI_DEVICE_SESSION_PARAMETER_BACKEND                              \
  QDMI_DEVICE_SESSION_PARAMETER_CUSTOM1
/// Null-terminated IBM Cloud instance CRN; defaults to
/// IBM_QUANTUM_INSTANCE_CRN.
#define IBM_QDMI_DEVICE_SESSION_PARAMETER_INSTANCE_CRN                         \
  QDMI_DEVICE_SESSION_PARAMETER_CUSTOM2

/// Positive decimal-string HTTP timeout in milliseconds (1..2147483647).
/// The default is 30000; a shorter job-wait deadline takes precedence.
#define IBM_QDMI_DEVICE_SESSION_PARAMETER_REQUEST_TIMEOUT                      \
  QDMI_DEVICE_SESSION_PARAMETER_CUSTOM3

/// Maximum QPU execution time in seconds (uint64_t, 1..10800); default: 60.
#define IBM_QDMI_DEVICE_JOB_PARAMETER_MAX_EXECUTION_TIME                       \
  QDMI_DEVICE_JOB_PARAMETER_CUSTOM1

/// Null-terminated dynamical-decoupling JSON object; disabled by default.
/// Accepts enable and skip_reset_qubits booleans, sequence_type (XX, XpXm,
/// XY4), extra_slack_distribution (middle, edges), and scheduling_method
/// (alap, asap). Each assignment replaces the previous options; omitted fields
/// default to false, false, XX, middle, and alap, respectively.
#define IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING                     \
  QDMI_DEVICE_JOB_PARAMETER_CUSTOM2
