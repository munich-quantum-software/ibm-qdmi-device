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

"""Explicit opt-in and redacted diagnostics for live metadata checks."""

from __future__ import annotations

import pytest
from metadata_checks import BACKENDS


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the live test controls without reading credentials."""
    parser.addoption("--run-live", action="store_true", help="Authorize metadata-only IBM requests")
    parser.addoption("--ibm-backend", default="both", help="both, ibm_berlin, or ibm_aachen")


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Validate selection and restrict diagnostics for an explicit live run.

    Raises:
        UsageError: A live run selected an unsupported backend.
    """
    config.addinivalue_line("markers", "live: explicitly authorized IBM metadata requests (disabled by default)")
    if config.getoption("run_live"):
        if config.getoption("ibm_backend") not in {"both", *BACKENDS}:
            msg = "live metadata: invalid backend selection"
            raise pytest.UsageError(msg)
        config.option.numprocesses = 0
        config.option.dist = "no"
        config.option.tx = []
        config.option.tbstyle = "line"
        config.option.showlocals = False
        config.option.fulltrace = False
        config.option.showcapture = "no"
        config.option.log_cli_level = "CRITICAL"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip live tests unless the invocation explicitly enables them."""
    for item in items:
        if item.get_closest_marker("live") is None:
            continue
        if not config.getoption("run_live"):
            item.add_marker(pytest.mark.skip(reason="live metadata is opt-in"))
        elif isinstance(item, pytest.Function) and config.getoption("ibm_backend") not in {
            "both",
            item.callspec.params["backend"],
        }:
            item.add_marker(pytest.mark.skip(reason="backend not selected"))
