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

"""Resolve IBM catalogue entries and shared session overrides."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from mqt.core.qdmi import driver

from . import IBM_QDMI_CATALOG_PATH, IBM_QDMI_DEVICE_ID, IBM_QDMI_LIBRARY_PATH, IBM_QDMI_PREFIX

if TYPE_CHECKING:
    from mqt.core.typing import QDMISessionParameters


def session_parameters(
    device_id: str,
    *,
    backend_name: str | None,
    api_key: str | None,
    instance_crn: str | None,
    base_url: str | None,
    auth_url: str | None,
) -> QDMISessionParameters:
    """Map explicit connection values and environment defaults to QDMI.

    Returns:
        Session overrides, preserving catalogue backends for concrete IDs.
    """
    if device_id == IBM_QDMI_DEVICE_ID and backend_name is None:
        backend_name = os.environ.get("IBM_QUANTUM_BACKEND")
    return {
        "token": api_key if api_key is not None else os.environ.get("IBM_QUANTUM_API_KEY"),
        "custom2": instance_crn if instance_crn is not None else os.environ.get("IBM_QUANTUM_INSTANCE_CRN"),
        "custom1": backend_name,
        "base_url": base_url,
        "auth_url": auth_url,
    }


def register_device(device_id: str) -> None:
    """Register the selected packaged entry if no driver definition exists.

    Args:
        device_id: Stable catalogue identifier.

    Raises:
        ValueError: The selected identifier is absent from the packaged catalogue.
    """
    entries = json.loads(IBM_QDMI_CATALOG_PATH.read_text(encoding="utf-8"))["qdmi"]["devices"]
    entry = next((item for item in entries if item["id"] == device_id), None)
    if entry is None:
        # Administrators can provide additional definitions through MQT Core.
        if device_id in driver.registered_device_ids():
            return
        msg = "Unknown IBM QDMI catalogue identifier."
        raise ValueError(msg)
    driver.register_device_if_absent(
        driver.DeviceDefinition(
            device_id,
            IBM_QDMI_LIBRARY_PATH,
            IBM_QDMI_PREFIX,
            custom1=entry.get("session", {}).get("custom1"),
        )
    )
