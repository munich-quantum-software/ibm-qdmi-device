# Python package

The `ibm-qdmi` distribution provides the `ibm.qdmi` namespace and bundles the
native library, device catalogue, headers, and CMake configuration. Follow
[installation](installation.md#python-package) to install from a checkout.
Importing the package does not load a device or contact IBM.

## Installed paths

Use the exported `pathlib.Path` constants to locate installed files:

| Constant                                   | Installed resource          |
| :----------------------------------------- | :-------------------------- |
| {py:data}`~ibm.qdmi.IBM_QDMI_LIBRARY_PATH` | Native shared library       |
| {py:data}`~ibm.qdmi.IBM_QDMI_CATALOG_PATH` | QDMI device catalogue       |
| {py:data}`~ibm.qdmi.IBM_QDMI_INCLUDE_DIR`  | Public headers              |
| {py:data}`~ibm.qdmi.IBM_QDMI_CMAKE_DIR`    | CMake package configuration |

The package also exports {py:data}`~ibm.qdmi.IBM_QDMI_DEVICE_ID`,
{py:data}`~ibm.qdmi.IBM_QDMI_PREFIX`, and `__version__`. The generated
{doc}`Python API <python-api/ibm/qdmi/index>` documents these exports and the
optional framework adapters.

```python
from ibm.qdmi import IBM_QDMI_CATALOG_PATH, IBM_QDMI_LIBRARY_PATH

print(IBM_QDMI_LIBRARY_PATH)
print(IBM_QDMI_CATALOG_PATH)
```

## Command-line interface

Inspect the installed package without opening a session:

```console
ibm-qdmi --version
ibm-qdmi --lib_path
ibm-qdmi --catalog_path
ibm-qdmi --include_dir
ibm-qdmi --cmake_dir
```

`python -m ibm.qdmi` accepts the same options. See
[device discovery](installation.md#device-discovery) for catalogue entries and
MQT Core configuration.

## Framework integrations

The optional [Qiskit integration](qiskit.md) supports transpilation, sampling,
and energy estimation. The [PennyLane integration](pennylane.md) supports
finite-shot QNodes and gradients. Both use MQT Core's shared QDMI adapters.
Start with the [examples](examples.md) to run workloads on a local simulator
before selecting IBM hardware.
