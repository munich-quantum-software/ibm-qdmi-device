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

#include <errno.h>
#include <ibm-qdmi-device/constants.h>
#include <ibm_qdmi/device.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static bool succeeded(int status, const char* operation) {
  if (status != QDMI_SUCCESS) {
    // The fixed format writes only a diagnostic label and status to stderr.
    // NOLINTNEXTLINE(clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling)
    fprintf(stderr, "%s: QDMI status %d\n", operation, status);
    return false;
  }
  return true;
}

static bool setText(IBM_QDMI_Device_Session session,
                    QDMI_Device_Session_Parameter parameter, const char* text) {
  return succeeded(IBM_QDMI_device_session_set_parameter(
                       session, parameter, strlen(text) + 1, text),
                   "Set session parameter");
}

static unsigned long positiveNumber(const char* text, unsigned long maximum) {
  char* end = NULL;
  if (*text < '1' || *text > '9') {
    return 0;
  }
  errno = 0;
  const unsigned long value = strtoul(text, &end, 10);
  return errno == 0 && *end == '\0' && value <= maximum ? value : 0;
}

int main(int argc, char** argv) {
  if (argc == 1 || (argc == 2 && strcmp(argv[1], "--help") == 0)) {
    puts("Usage: ibm-qdmi-execute --run BACKEND [--timeout SECONDS] "
         "[--test-port PORT]\n"
         "Run 16 shots with a 60-second QPU cap. Timeout: 1..60 seconds "
         "(default: 60).\n"
         "Set IBM_QUANTUM_API_KEY and IBM_QUANTUM_INSTANCE_CRN. "
         "The test port connects to a local service at 127.0.0.1.");
    return EXIT_SUCCESS;
  }
  if (argc < 3 || strcmp(argv[1], "--run") != 0 || argv[2][0] == '\0' ||
      argc % 2 == 0) {
    fputs("Expected --run BACKEND; use --help for options.\n", stderr);
    return EXIT_FAILURE;
  }

  unsigned long testPort = 0;
  unsigned long timeout = 60;
  bool timeoutSet = false;
  for (int i = 3; i < argc; i += 2) {
    if (strcmp(argv[i], "--timeout") == 0 && !timeoutSet) {
      timeout = positiveNumber(argv[i + 1], 60);
      timeoutSet = true;
      if (timeout == 0) {
        fputs("Timeout must be an integer from 1 to 60.\n", stderr);
        return EXIT_FAILURE;
      }
    } else if (strcmp(argv[i], "--test-port") == 0 && testPort == 0) {
      testPort = positiveNumber(argv[i + 1], 65535);
      if (testPort == 0) {
        fputs("The test port must be an integer from 1 to 65535.\n", stderr);
        return EXIT_FAILURE;
      }
    } else {
      fputs("Unknown or duplicate option; use --help for options.\n", stderr);
      return EXIT_FAILURE;
    }
  }

  IBM_QDMI_Device_Session session = NULL;
  IBM_QDMI_Device_Job job = NULL;
  char* results = NULL;
  bool submitted = false;
  bool finished = false;
  int exitCode = EXIT_FAILURE;
  if (!succeeded(IBM_QDMI_device_initialize(), "Initialize library")) {
    return exitCode;
  }
  if (!succeeded(IBM_QDMI_device_session_alloc(&session), "Allocate session") ||
      !setText(session, IBM_QDMI_DEVICE_SESSION_PARAMETER_BACKEND, argv[2])) {
    goto cleanup;
  }
  if (testPort != 0) {
    char endpoint[32];
    char authUrl[64];
    // The port is bounded and both lengths are checked before use.
    // NOLINTBEGIN(clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling)
    const int endpointLength =
        snprintf(endpoint, sizeof(endpoint), "http://127.0.0.1:%lu", testPort);
    const int authLength = snprintf(authUrl, sizeof(authUrl),
                                    "http://127.0.0.1:%lu/auth", testPort);
    // NOLINTEND(clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling)
    if (endpointLength < 0 || (size_t)endpointLength >= sizeof(endpoint) ||
        authLength < 0 || (size_t)authLength >= sizeof(authUrl) ||
        !setText(session, QDMI_DEVICE_SESSION_PARAMETER_BASEURL, endpoint) ||
        !setText(session, QDMI_DEVICE_SESSION_PARAMETER_AUTHURL, authUrl)) {
      goto cleanup;
    }
  }
  // Session initialization resolves credentials from the environment.
  if (!succeeded(IBM_QDMI_device_session_init(session), "Initialize session")) {
    goto cleanup;
  }

  size_t qubits = 0;
  if (!succeeded(IBM_QDMI_device_session_query_device_property(
                     session, QDMI_DEVICE_PROPERTY_QUBITSNUM, sizeof(qubits),
                     &qubits, NULL),
                 "Query qubit count") ||
      qubits == 0) {
    goto cleanup;
  }
  char program[256];
  // The fixed program has one bounded integer substitution and a checked
  // length.
  // NOLINTBEGIN(clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling)
  const int programLength =
      snprintf(program, sizeof(program),
               "OPENQASM 3.0;\ninclude \"stdgates.inc\";\nqubit[%zu] q;\n"
               "bit[1] c;\nx q[0];\nc[0] = measure q[0];\n",
               qubits);
  // NOLINTEND(clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling)
  if (programLength < 0 || (size_t)programLength >= sizeof(program)) {
    fputs("Cannot construct the program.\n", stderr);
    goto cleanup;
  }
  const QDMI_Program_Format format = QDMI_PROGRAM_FORMAT_QASM3;
  const size_t shots = 16;
  const uint64_t maximumExecutionTime = 60;
  if (!succeeded(IBM_QDMI_device_session_create_device_job(session, &job),
                 "Create job") ||
      !succeeded(IBM_QDMI_device_job_set_parameter(
                     job, QDMI_DEVICE_JOB_PARAMETER_PROGRAMFORMAT,
                     sizeof(format), &format),
                 "Set program format") ||
      !succeeded(IBM_QDMI_device_job_set_parameter(
                     job, QDMI_DEVICE_JOB_PARAMETER_PROGRAM,
                     (size_t)programLength + 1, program),
                 "Set program") ||
      !succeeded(
          IBM_QDMI_device_job_set_parameter(
              job, QDMI_DEVICE_JOB_PARAMETER_SHOTSNUM, sizeof(shots), &shots),
          "Set shots") ||
      !succeeded(IBM_QDMI_device_job_set_parameter(
                     job, IBM_QDMI_DEVICE_JOB_PARAMETER_MAX_EXECUTION_TIME,
                     sizeof(maximumExecutionTime), &maximumExecutionTime),
                 "Set execution cap") ||
      !succeeded(IBM_QDMI_device_job_submit(job), "Submit job")) {
    goto cleanup;
  }
  submitted = true;
  if (!succeeded(IBM_QDMI_device_job_wait(job, timeout), "Wait for job")) {
    goto cleanup;
  }
  QDMI_Job_Status status = QDMI_JOB_STATUS_CREATED;
  if (!succeeded(IBM_QDMI_device_job_check(job, &status), "Check job") ||
      status != QDMI_JOB_STATUS_DONE) {
    fputs("The job did not complete successfully.\n", stderr);
    goto cleanup;
  }
  finished = true;

  size_t required = 0;
  if (!succeeded(IBM_QDMI_device_job_get_results(job, QDMI_JOB_RESULT_SHOTS, 0,
                                                 NULL, &required),
                 "Query result size") ||
      required == 0) {
    goto cleanup;
  }
  results = malloc(required);
  if (results == NULL) {
    fputs("Cannot allocate the result buffer.\n", stderr);
    goto cleanup;
  }
  if (!succeeded(IBM_QDMI_device_job_get_results(job, QDMI_JOB_RESULT_SHOTS,
                                                 required, results, NULL),
                 "Read shots")) {
    goto cleanup;
  }
  puts(results);
  exitCode = EXIT_SUCCESS;

cleanup:
  free(results);
  if (submitted && !finished) {
    const int cancellation = IBM_QDMI_device_job_cancel(job);
    if (cancellation != QDMI_ERROR_INVALIDARGUMENT) {
      (void)succeeded(cancellation, "Cancel job");
    }
  }
  if (job != NULL) {
    IBM_QDMI_device_job_free(job);
  }
  if (session != NULL) {
    IBM_QDMI_device_session_free(session);
  }
  if (!succeeded(IBM_QDMI_device_finalize(), "Finalize library")) {
    exitCode = EXIT_FAILURE;
  }
  return exitCode;
}
