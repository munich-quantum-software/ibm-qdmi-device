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

#include "ibm_qdmi/export.h"

#ifdef __cplusplus
extern "C" {
#endif

/// Fixed, non-sensitive reason for the last QDMI call on the current thread.
// C callers require an unscoped enum and stable C names.
// NOLINTBEGIN
typedef enum IBM_QDMI_Diagnostic {
  IBM_QDMI_DIAGNOSTIC_NONE = 0,
  IBM_QDMI_DIAGNOSTIC_INVALID_ARGUMENT,
  IBM_QDMI_DIAGNOSTIC_BAD_STATE,
  IBM_QDMI_DIAGNOSTIC_NOT_SUPPORTED,
  IBM_QDMI_DIAGNOSTIC_AUTHENTICATION,
  IBM_QDMI_DIAGNOSTIC_NOT_FOUND,
  IBM_QDMI_DIAGNOSTIC_TIMEOUT,
  IBM_QDMI_DIAGNOSTIC_TRANSPORT,
  IBM_QDMI_DIAGNOSTIC_RATE_LIMIT,
  IBM_QDMI_DIAGNOSTIC_SERVICE,
  IBM_QDMI_DIAGNOSTIC_JOB_FAILED,
  IBM_QDMI_DIAGNOSTIC_INTERNAL
} IBM_QDMI_Diagnostic;
// NOLINTEND

/// Query the last call's diagnostic. Any later QDMI call on this thread
/// replaces it. The value does not contain server text, URLs, credentials, or
/// backend data.
IBM_QDMI_EXPORT IBM_QDMI_Diagnostic IBM_QDMI_device_last_diagnostic(void);

#ifdef __cplusplus
}
#endif
