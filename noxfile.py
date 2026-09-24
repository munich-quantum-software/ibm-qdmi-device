#!/usr/bin/env -S uv run --script --quiet
# Copyright (c) 2025 - 2026 Munich Quantum Software Company GmbH
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

# /// script
# dependencies = ["nox"]
# ///

"""Nox sessions."""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import nox

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

nox.needs_version = ">=2026.8.10"
nox.options.default_venv_backend = "uv"


PYTHON_ALL_VERSIONS = ["3.11", "3.12", "3.13", "3.14"]

if os.environ.get("CI", None):
    nox.options.error_on_missing_interpreters = True


@contextlib.contextmanager
def preserve_lockfile() -> Generator[None, None, None]:
    """Preserve the lockfile by moving it to a temporary directory."""
    with tempfile.TemporaryDirectory() as temp_dir_name:
        shutil.move("uv.lock", f"{temp_dir_name}/uv.lock")
        try:
            yield
        finally:
            shutil.move(f"{temp_dir_name}/uv.lock", "uv.lock")


@nox.session(reuse_venv=True, default=True)
def lint(session: nox.Session) -> None:
    """Run the linter."""
    if shutil.which("prek") is None:
        session.install("prek")

    session.run("prek", "run", "--all-files", *session.posargs, external=True)


def _run_tests(
    session: nox.Session,
    *,
    install_args: Sequence[str] = (),
    dependency_groups: Sequence[str] = (),
    extra_command: Sequence[str] = (),
    pytest_run_args: Sequence[str] = (),
) -> None:
    env = {"UV_PROJECT_ENVIRONMENT": session.virtualenv.location}
    run_args = [
        "uv",
        "run",
        "--no-dev",
        "--group",
        "test",
        *(argument for group in dependency_groups for argument in ("--group", group)),
        *install_args,
    ]
    if extra_command:
        session.run(*run_args, *extra_command, env=env)
    session.run(
        *run_args,
        "pytest",
        *pytest_run_args,
        *session.posargs,
        "--cov-config=pyproject.toml",
        env=env,
    )


@nox.session(python=PYTHON_ALL_VERSIONS, reuse_venv=True, default=True)
def tests(session: nox.Session) -> None:
    """Run the test suite."""
    _run_tests(session)


@nox.session(python="3.14", reuse_venv=True)
def native_tests(session: nox.Session) -> None:
    """Test the native transport in a process independent of framework drivers."""
    _run_tests(session, pytest_run_args=("-m", "integration", "-n", "0"))


@nox.session(python=PYTHON_ALL_VERSIONS, reuse_venv=True, venv_backend="uv", default=True)
def minimums(session: nox.Session) -> None:
    """Test the minimum versions of dependencies."""
    with preserve_lockfile():
        _run_tests(
            session,
            install_args=["--resolution=lowest-direct"],
            pytest_run_args=["-Wdefault"],
        )
        env = {"UV_PROJECT_ENVIRONMENT": session.virtualenv.location}
        session.run("uv", "tree", "--frozen", env=env)


@nox.session(python="3.14", reuse_venv=True)
def examples(session: nox.Session) -> None:
    """Exercise the runnable examples with local simulators and loopback IBM."""
    _run_tests(
        session,
        dependency_groups=["examples"],
        extra_command=["python", "test/examples/build_native.py"],
        pytest_run_args=["test/examples", "-n", "0"],
    )


@nox.session(python="3.14", reuse_venv=True)
def docs(session: nox.Session) -> None:
    """Build the documentation. Pass ``-b linkcheck`` to check links."""
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", dest="builder", default="html", help="Build target (default: html)")
    args, posargs = parser.parse_known_args(session.posargs)

    env = {"UV_PROJECT_ENVIRONMENT": session.virtualenv.location}
    session.run(
        "uv",
        "run",
        "--no-dev",
        "--group",
        "docs",
        "--group",
        "examples",
        "--config-settings-package",
        "ibm-qdmi:build-dir=build/docs",
        "--config-settings-package",
        "ibm-qdmi:cmake.define.BUILD_IBM_QDMI_DOCS=ON",
        "sphinx-build",
        "-n",
        "-T",
        "-W",
        f"-b={args.builder}",
        "docs",
        f"docs/_build/{args.builder}",
        *posargs,
        env=env,
    )


@nox.session(name="live-metadata", python="3.14", reuse_venv=True, default=False)
def live_metadata(session: nox.Session) -> None:
    """Build the wheel, then explicitly validate IBM metadata without jobs."""
    selection = session.posargs or ["both"]
    if len(selection) != 1 or selection[0] not in {"both", "ibm_berlin", "ibm_aachen"}:
        session.error("live metadata: invalid backend selection")
    if not all(os.environ.get(name) for name in ("IBM_QUANTUM_API_KEY", "IBM_QUANTUM_INSTANCE_CRN")):
        session.error("live metadata: missing credentials")
    build_env = {
        "IBM_QUANTUM_API_KEY": "",
        "IBM_QUANTUM_INSTANCE_CRN": "",
        "SKBUILD_BUILD_DIR": "build/live/wheel/{wheel_tag}/{build_type}",
    }
    with tempfile.TemporaryDirectory(dir=session.create_tmp()) as dist:
        session.run("uv", "build", "--wheel", "--out-dir", dist, env=build_env)
        wheel = next(Path(dist).glob("*.whl"))
        session.run(
            "uv",
            "pip",
            "install",
            "--python",
            session.virtualenv.location,
            "--group",
            "test",
            "--reinstall-package",
            "ibm-qdmi",
            str(wheel),
            env=build_env,
        )
    session.run(
        "python",
        "-m",
        "pytest",
        "test/python/test_live_metadata.py",
        "--run-live",
        "--ibm-backend",
        selection[0],
        "-n",
        "0",
        "--tb=line",
        "--show-capture=no",
    )


if __name__ == "__main__":
    nox.main()
