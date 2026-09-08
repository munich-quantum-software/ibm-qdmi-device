# API status

## Native interface

The package installs IBM-prefixed QDMI 1.3.3 declarations. These declarations
describe the future device contract; no device function is implemented. There is
no registered device ID or discoverable device catalogue.

<!-- The native API link is generated alongside the Sphinx HTML. -->
<!-- rumdl-disable MD033 -->
The <a href="cpp/index.html">generated QDMI declaration reference</a>
accompanies HTML documentation builds.
<!-- rumdl-enable MD033 -->

It includes upstream client declarations to resolve references shared by the
QDMI client and device contracts. They are documentation context, not an IBM
client implementation.

## Python package

`ibm.qdmi.__version__` reports the installed distribution version. The package
exposes no backend, command-line interface, or quantum framework integration.
