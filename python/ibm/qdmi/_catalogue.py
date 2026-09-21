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

"""Register packaged catalogue entries without replacing driver configuration."""

from __future__ import annotations

import json

from mqt.core.qdmi import driver

from . import IBM_QDMI_CATALOG_PATH, IBM_QDMI_LIBRARY_PATH, IBM_QDMI_PREFIX


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
