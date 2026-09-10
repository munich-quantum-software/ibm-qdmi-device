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

#include <gtest/gtest.h>
#include <ibm_qdmi/device.h>
extern "C" int cSessionLifecycle();

TEST(Package, CAndCppHeadersLinkWithLibrary) {
  ASSERT_EQ(IBM_QDMI_device_initialize(), QDMI_SUCCESS);
  EXPECT_EQ(cSessionLifecycle(), QDMI_SUCCESS);
  EXPECT_EQ(IBM_QDMI_device_finalize(), QDMI_SUCCESS);
}

TEST(Session, ValidatesConfigurationAndLifetime) {
  ASSERT_EQ(IBM_QDMI_device_initialize(), QDMI_SUCCESS);
  EXPECT_EQ(IBM_QDMI_device_session_alloc(nullptr), QDMI_ERROR_INVALIDARGUMENT);
  IBM_QDMI_Device_Session session = nullptr;
  ASSERT_EQ(IBM_QDMI_device_session_alloc(&session), QDMI_SUCCESS);
  EXPECT_EQ(IBM_QDMI_device_session_init(session), QDMI_ERROR_PERMISSIONDENIED);
  EXPECT_EQ(IBM_QDMI_device_session_set_parameter(
                session, QDMI_DEVICE_SESSION_PARAMETER_TOKEN, 0, "key"),
            QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(IBM_QDMI_device_session_set_parameter(
                session, QDMI_DEVICE_SESSION_PARAMETER_TOKEN, 3, "key"),
            QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(IBM_QDMI_device_session_set_parameter(
                session, QDMI_DEVICE_SESSION_PARAMETER_TOKEN, 4, "key"),
            QDMI_SUCCESS);
  EXPECT_EQ(IBM_QDMI_device_session_init(session), QDMI_ERROR_INVALIDARGUMENT);
  EXPECT_EQ(IBM_QDMI_device_session_query_device_property(
                session, QDMI_DEVICE_PROPERTY_NAME, 0, nullptr, nullptr),
            QDMI_ERROR_BADSTATE);
  EXPECT_EQ(IBM_QDMI_device_finalize(), QDMI_ERROR_FATAL);
  IBM_QDMI_device_session_free(session);
  EXPECT_EQ(IBM_QDMI_device_session_init(session), QDMI_ERROR_INVALIDARGUMENT);
  IBM_QDMI_device_session_free(session);
  IBM_QDMI_device_session_free(nullptr);
  EXPECT_EQ(IBM_QDMI_device_finalize(), QDMI_SUCCESS);
}
