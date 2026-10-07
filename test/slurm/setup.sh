#!/bin/sh
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

set -eu

# The shared synthetic service imports the existing pytest fixtures.
uv pip install --system --break-system-packages 'pytest>=9.1.1'
uv run --no-project python - <<'CATALOGUE'
import json
import os
from pathlib import Path
from ibm.qdmi import IBM_QDMI_CATALOG_PATH

catalogue = IBM_QDMI_CATALOG_PATH
if os.environ["PROVIDER_INSTALL_MODE"] == "native":
    catalogue = Path("/opt/provider-native/lib/ibm-qdmi-device.qdmi.json")
configuration = json.loads(catalogue.read_text())
definition = configuration["qdmi"]["devices"][0]
definition["id"] = "ibm.fixture"
definition["library"] = str((catalogue.parent / definition["library"]).resolve())
definition["session"] = {
    "custom1": "ibm_test",
    "base-url": "http://127.0.0.1:18080",
    "auth-url": "http://127.0.0.1:18080/auth",
}
configuration["qdmi"]["devices"] = [definition]
Path("/opt/provider-catalogue.json").write_text(json.dumps(configuration))
CATALOGUE

cat > /etc/systemd/system/ibm-fixture.service <<'SERVICE'
[Unit]
Description=Synthetic IBM API for Slurm tests
Before=slurmctld.service slurmd.service

[Service]
Type=notify
User=mqt-test
Environment=PYTHONPATH=/workload/test/python
ExecStart=/usr/bin/python3 /workload/test/slurm/server.py

[Install]
WantedBy=multi-user.target
SERVICE
systemctl enable ibm-fixture.service
