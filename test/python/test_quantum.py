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

"""Paid hardware validation; skipped before credentials unless explicitly enabled."""

from __future__ import annotations

import os

import pytest
from metadata_checks import BACKENDS
from quantum_checks import validate_execution

from ibm.qdmi.qiskit import IBMBackend


@pytest.mark.quantum
@pytest.mark.parametrize("backend", BACKENDS)
def test_quantum(backend: str) -> None:
    """Execute exactly one 128-shot job, then reopen it without resubmission."""
    key = os.environ.get("IBM_QUANTUM_API_KEY", "")
    crn = os.environ.get("IBM_QUANTUM_INSTANCE_CRN", "")
    if not key or not crn:
        pytest.fail("quantum: missing credentials", pytrace=False)
    failure = None
    try:
        failure = validate_execution(lambda: IBMBackend(backend_name=backend, api_key=key, instance_crn=crn))
    except Exception:  # ruff: ignore[blind-except] -- never expose native or credential diagnostics
        failure = "unexpected failure"
    if failure is not None:
        pytest.fail(f"quantum: {failure}", pytrace=False)
