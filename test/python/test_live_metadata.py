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

"""Metadata-only IBM checks, disabled until explicitly requested."""

from __future__ import annotations

import os

import pytest
from metadata_checks import BACKENDS, validate_backend
from native_support import MetadataError, load_native


@pytest.mark.live
@pytest.mark.parametrize("backend", BACKENDS)
def test_live_metadata(backend: str) -> None:
    """Validate an authorized backend without submitting any quantum jobs."""
    key = os.environ.get("IBM_QUANTUM_API_KEY", "")
    crn = os.environ.get("IBM_QUANTUM_INSTANCE_CRN", "")
    if not key or not crn:
        pytest.fail("live metadata: missing credentials", pytrace=False)
    failure = None
    try:
        with load_native() as api:
            validate_backend(api, backend, BACKENDS[backend], {1: key, 999999995: backend, 999999996: crn})
    except MetadataError as error:
        failure = str(error)
    except Exception:  # ruff: ignore[blind-except] -- never expose unexpected native or credential diagnostics
        failure = "live metadata: unexpected failure"
    # Raise outside the handler so pytest cannot render the original exception chain.
    if failure is not None:
        pytest.fail(failure, pytrace=False)
