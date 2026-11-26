# C/C++ API reference

The library implements the QDMI device interface with the `IBM_` symbol prefix.
Include `ibm_qdmi/device.h` for the device API and `ibm-qdmi-device/constants.h`
or `ibm-qdmi-device/diagnostics.h` for IBM extensions. See the
[usage guide](api.md) for supported properties and job behavior, and
[native installation](installation.md#native-package) for CMake integration.

The reference is generated directly from the public headers:

<!-- rumdl-disable MD033 -->
| Reference                                                                   | Contents                                         |
| --------------------------------------------------------------------------- | ------------------------------------------------ |
| <a href="cpp/index.html">Native API</a>                                     | Complete generated reference                     |
| <a href="cpp/group__device__interface.html">Device lifecycle</a>            | Initialization and finalization                  |
| <a href="cpp/group__device__session__interface.html">Sessions</a>           | Configuration and resource ownership             |
| <a href="cpp/group__device__query__interface.html">Queries</a>              | Device, site, and operation properties           |
| <a href="cpp/group__device__job__interface.html">Jobs</a>                   | Submission, results, cancellation, and retrieval |
| <a href="cpp/include_2ibm-qdmi-device_2constants_8h.html">IBM constants</a> | Custom parameters and formats                    |
| <a href="cpp/diagnostics_8h.html">Diagnostics</a>                           | Fixed failure categories                         |
<!-- rumdl-enable MD033 -->

The
[QDMI reference](https://munich-quantum-software-stack.github.io/QDMI/v1.4.0/)
documents the client interface and shared types.
