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
import pytest
from qiskit import QuantumCircuit, transpile
from qiskit.circuit import Parameter
from qiskit.quantum_info import SparsePauliOp
from qiskit_service import open_backend

if TYPE_CHECKING:
    from qiskit_service import RuntimeProxy


@pytest.mark.parametrize("precision", [0, -0.1])
def test_invalid_estimator_precision_submits_nothing(runtime: RuntimeProxy, precision: float) -> None:
    """Invalid primitive precision cannot create a native job."""
    backend = open_backend(runtime)
    with pytest.raises(ValueError, match="precision"):
        backend.estimator().run([(QuantumCircuit(1), SparsePauliOp("Z"))], precision=precision).result()
    assert not runtime.snapshot()["submissions"]


def test_estimator_precision_observables_and_layout(runtime: RuntimeProxy) -> None:
    """The shared estimator maps observables and produces finite-shot expectations."""
    backend = open_backend(runtime)
    theta = Parameter("theta")
    circuit = QuantumCircuit(1)
    circuit.ry(theta, 0)
    mapped = transpile(circuit, backend, initial_layout=[4], optimization_level=0)
    observable = SparsePauliOp("Z").apply_layout(mapped.layout)
    result = (
        backend
        .estimator()
        .run([(mapped, observable, {theta: np.array([[0.0], [math.pi]])})], precision=0.125)
        .result()[0]
    )
    np.testing.assert_allclose(result.data["evs"], [1, -1], atol=1e-12)
    np.testing.assert_allclose(result.data["stds"], [0, 0], atol=1e-12)
    assert len(runtime.snapshot()["submissions"]) == 2
    assert all(request["params"]["pubs"][0][2] == 64 for request in runtime.snapshot()["submissions"])
    assert all(request["cost"] == 60 for request in runtime.snapshot()["submissions"])
