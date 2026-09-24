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

"""Public Qiskit execution through the real installed MQT Core/native stack."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.circuit import Parameter
from qiskit_service import open_backend

if TYPE_CHECKING:
    from qiskit_service import RuntimeProxy


def test_sampler_parameter_broadcast_and_registers(runtime: RuntimeProxy) -> None:
    """The shared BackendSamplerV2 expands bound PUBs and preserves registers."""
    backend = open_backend(runtime)
    theta = Parameter("theta")
    circuit = QuantumCircuit(QuantumRegister(1, "q"), ClassicalRegister(1, "z"), ClassicalRegister(1, "a"))
    circuit.sx(0)
    circuit.rz(theta, 0)
    circuit.sx(0)
    circuit.measure(0, circuit.cregs[0][0])
    circuit.measure(0, circuit.cregs[1][0])
    result = backend.sampler(default_shots=32).run([(circuit, {theta: np.array([[0.0], [math.pi]])})]).result()[0]
    assert result.data["z"].get_counts(0) == {"1": 32}
    assert result.data["z"].get_counts(1) == {"0": 32}
    assert result.data["a"].get_counts(0) == {"1": 32}
    assert len(runtime.snapshot()["submissions"]) == 2
    assert all(request["params"]["pubs"][0][2] == 32 for request in runtime.snapshot()["submissions"])
