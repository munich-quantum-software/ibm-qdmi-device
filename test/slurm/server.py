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

"""Run the existing synthetic IBM runtime on each Slurm fixture node."""

import os
import socket
from threading import Event

from offline_service import serve
from qiskit_service import configure

if __name__ == "__main__":
    with serve(address=("127.0.0.1", 18080)) as service:
        configure(service)
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notification:
            notification.sendto(b"READY=1", os.environ["NOTIFY_SOCKET"])
        Event().wait()
