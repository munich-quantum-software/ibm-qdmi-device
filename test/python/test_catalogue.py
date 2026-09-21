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

"""Exercise discovery through the installed driver and relocated artifacts."""

# Subprocess arguments are fixed test code and synthetic fixture values.
# ruff: file-ignore[subprocess-without-shell-equals-true]

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ibm import qdmi

if TYPE_CHECKING:
    from offline_service import Service


@pytest.mark.parametrize("device_id", ["ibm.default", "ibm.berlin", "ibm.aachen"])
def test_relocated_driver(device_id: str, service: Service, tmp_path: Path) -> None:
    """The real MQT Core driver opens each entry after library relocation."""
    # Wheel repair can put dependencies beside the Python package. Preserve the
    # distribution's relative layout so the loader's relative paths still work.
    destination = tmp_path / "runtime"
    package = distribution("ibm-qdmi")
    root = Path(str(package.locate_file(""))).resolve()
    assert package.files is not None
    for file in package.files:
        if file.is_absolute() or ".." in file.parts:
            continue  # Installed CLI launchers are outside the runtime payload.
        target = destination / file
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(package.locate_file(file)), target)
    catalogue = destination / qdmi.IBM_QDMI_CATALOG_PATH.relative_to(root)
    entries = json.loads(catalogue.read_text(encoding="utf-8"))["qdmi"]["devices"]
    entry = next(item for item in entries if item["id"] == device_id)
    assert entry["prefix"] == "IBM"
    assert (catalogue.parent / entry["library"]).is_file()
    backend = entry.get("session", {}).get("custom1", "ibm_test")
    service.data["configuration"]["backend_name"] = backend
    script = """
import sys
from mqt.core.qdmi import driver
assert set(('ibm.default', 'ibm.berlin', 'ibm.aachen')) <= set(driver.registered_device_ids())
options = dict(base_url=sys.argv[2], token='synthetic-key', auth_url=sys.argv[2] + '/auth',
               custom2='crn:v1:bluemix:public:quantum-computing:us-east:a:instance::')
if sys.argv[1] == 'ibm.default':
    options['custom1'] = 'ibm_test'
device = driver.open_device(sys.argv[1], **options)
assert device.name() == sys.argv[3]
assert len(device.sites()) == 2
assert {operation.name() for operation in device.operations()} == {'x', 'rz', 'cx'}
print('installed driver passed')
"""
    env = {key: value for key, value in os.environ.items() if not key.startswith("MQT_CORE_QDMI_CONFIG_")}
    env["MQT_CORE_QDMI_CONFIG_FILE"] = str(catalogue)
    result = subprocess.run(
        [sys.executable, "-c", script, device_id, service.url, backend],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "installed driver passed"
    assert service.requests
    assert all("127.0.0.1" in headers["Host"] for _, headers, _ in service.requests)


@pytest.mark.parametrize(
    ("option", "expected"),
    [
        ("version", qdmi.__version__),
        ("include_dir", str(qdmi.IBM_QDMI_INCLUDE_DIR)),
        ("cmake_dir", str(qdmi.IBM_QDMI_CMAKE_DIR)),
        ("lib_path", str(qdmi.IBM_QDMI_LIBRARY_PATH)),
        ("catalog_path", str(qdmi.IBM_QDMI_CATALOG_PATH)),
    ],
)
def test_information_cli(option: str, expected: str) -> None:
    """Both CLI entry points expose installed paths without loading the driver."""
    for command in ([sys.executable, "-m", "ibm.qdmi"], [shutil.which("ibm-qdmi") or "ibm-qdmi"]):
        result = subprocess.run([*command, f"--{option}"], check=True, capture_output=True, text=True, timeout=10)
        assert result.stdout.strip() == expected


def test_import_needs_no_optional_dependencies() -> None:
    """The base package and its CLI never import a quantum framework or driver."""
    script = """
import sys
class BlockFrameworks:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mqt', 'qiskit'}:
            raise AssertionError('base import loaded an optional dependency')
sys.meta_path.insert(0, BlockFrameworks())
from ibm import qdmi
from ibm.qdmi import __main__
assert qdmi.IBM_QDMI_LIBRARY_PATH.is_file()
assert qdmi.IBM_QDMI_CATALOG_PATH.is_file()
assert qdmi.IBM_QDMI_INCLUDE_DIR.is_dir()
assert qdmi.IBM_QDMI_CMAKE_DIR.is_dir()
assert qdmi.IBM_QDMI_DEVICE_ID == 'ibm.default'
assert qdmi.IBM_QDMI_PREFIX == 'IBM'
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, timeout=10)
