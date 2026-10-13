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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mqt.core.typing import QDMISessionParameters


def session_parameters(
    *,
    backend_name: str | None,
    api_key: str | None,
    instance_crn: str | None,
    base_url: str | None,
    auth_url: str | None,
) -> QDMISessionParameters:
    """Map explicit connection overrides to QDMI session parameters.

    Returns:
        Explicit overrides; native session initialization resolves omitted values.
    """
    return {
        "token": api_key,
        "custom2": instance_crn,
        "custom1": backend_name,
        "base_url": base_url,
        "auth_url": auth_url,
    }
