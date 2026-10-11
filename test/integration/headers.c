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

#include <ibm-qdmi-device/constants.h>
#include <ibm_qdmi/device.h>

int cSessionLifecycle(void);
int cSessionLifecycle(void) {
  IBM_QDMI_Device_Session session = NULL;
  int result = IBM_QDMI_device_session_alloc(&session);
  if (result != QDMI_SUCCESS) {
    return result;
  }
  result = IBM_QDMI_device_session_set_parameter(
      session, IBM_QDMI_DEVICE_SESSION_PARAMETER_BACKEND, 0, NULL);
  IBM_QDMI_device_session_free(session);
  return result;
}

int cProgramInterface(void);
int cProgramInterface(void) {
  QDMI_Job_Status status = QDMI_JOB_STATUS_CREATED;
  if (IBM_QDMI_device_job_set_programs(NULL, QDMI_PROGRAM_FORMAT_QASM3, 1, NULL,
                                       NULL) != QDMI_ERROR_INVALIDARGUMENT ||
      IBM_QDMI_device_job_get_program(NULL, 0, 0, NULL, NULL) !=
          QDMI_ERROR_INVALIDARGUMENT ||
      IBM_QDMI_device_job_get_program_status(NULL, 0, &status) !=
          QDMI_ERROR_INVALIDARGUMENT ||
      IBM_QDMI_device_job_get_results(NULL, 0, QDMI_JOB_RESULT_SHOTS, 0, NULL,
                                      NULL) != QDMI_ERROR_INVALIDARGUMENT) {
    return QDMI_ERROR_FATAL;
  }
  return QDMI_SUCCESS;
}
