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

"""Sphinx configuration file."""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_ext"))

try:
    version = metadata.version("ibm-qdmi")
except metadata.PackageNotFoundError:
    msg = "ibm-qdmi must be installed to build the documentation"
    raise ModuleNotFoundError(msg) from None

release = version.split("+")[0]

project = "IBM QDMI Device"
author = "Munich Quantum Software Company GmbH"
copyright = "2025 - 2026 Munich Quantum Software Company GmbH"  # ruff: ignore[builtin-variable-shadowing]
language = "en"
master_doc = "index"

extensions = [
    "autoapi.extension",
    "native_api",
    "myst_nb",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
]

autoapi_dirs = ["../python/ibm"]
autoapi_root = "python-api"
autoapi_python_use_implicit_namespaces = True
autoapi_add_toctree_entry = False
autoapi_keep_files = False
autoapi_ignore = ["*/__main__.py"]
autoapi_options = ["members", "imported-members", "undoc-members", "show-inheritance", "show-module-summary"]

# MQT Core uses this type alias in signatures but does not publish it in its inventory.
nitpick_ignore = [("py:class", "mqt.core.plugins.qiskit.backend.ParametersType")]

source_suffix = [".rst", ".md"]
exclude_patterns = [
    "_build",
    "_static/README.md",
    "**.ipynb_checkpoints",
    "**.jupyter_cache",
    "**.jupyter_execute",
    "Thumbs.db",
    ".DS_Store",
]

html_theme = "furo"
html_static_path = ["_static"]
html_theme_options = {
    "light_logo": "logo-mqsc-light.svg",
    "dark_logo": "logo-mqsc-dark.svg",
    "source_repository": "https://github.com/munich-quantum-software/ibm-qdmi-device/",
    "source_branch": "main",
    "source_directory": "docs/",
    "navigation_with_keys": True,
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/munich-quantum-software/ibm-qdmi-device/",
            "html": "GitHub",
            "class": "",
        },
    ],
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "mqt-core": ("https://mqt.readthedocs.io/projects/core/en/stable", None),
    "qiskit": ("https://docs.quantum.ibm.com/api/qiskit", None),
    "qiskit-algorithms": ("https://qiskit-community.github.io/qiskit-algorithms", None),
    "pennylane": ("https://docs.pennylane.ai/en/stable", None),
}

myst_enable_extensions = [
    "amsmath",
    "colon_fence",
    "deflist",
    "dollarmath",
    "substitution",
]
myst_heading_anchors = 3
myst_substitutions = {"version": version}

modindex_common_prefix = ["ibm.qdmi."]
add_module_names = False
toc_object_entries_show_parents = "hide"
python_use_unqualified_type_names = True
napoleon_google_docstring = True
napoleon_numpy_docstring = False

nb_execution_mode = "off"
nb_execution_raise_on_error = True

copybutton_prompt_text = r"(?:\(\.?venv\) )?(?:\[.*\] )?\$ "
copybutton_prompt_is_regexp = True
copybutton_line_continuation_character = "\\"
