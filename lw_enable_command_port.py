"""
lw_enable_command_port.py

Run this ONCE, inside LightWave Layout, to turn on Layout's built-in
Command Port (an official, NewTek-supplied network interface for
remotely driving Layout - see lwcommandport.html / globalcommandport.html
in the LightWave 2019 Python SDK docs, and the bundled Python client at
support/python/lwcommandport in your LightWave install).

This is a "single-shot" Generic plug-in (see "Anatomy of a LightWave
Python Plug-in" -> "Single-Shot Exceptions" in the SDK docs): no class,
no ServerRecord needed. Load it via Utilities > Plugins > Add Plugin,
then invoke it once from the Utilities/Python menu (or a hotkey). You
only need to do this again if you restart Layout.

Despite the SDK doc's phrasing ("TCP/IP port"), the underlying wire
protocol used by the bundled Python client is UDP - that's confirmed by
reading support/python/lwcommandport/__init__.py directly (it uses
socket.SOCK_DGRAM). Nothing to do about that here; just keep it in mind
if this doesn't connect and you go looking with a packet sniffer.
"""

try:
    import lwsdk
except ImportError:
    import sys
    print("This is a LightWave Python Generic plug-in. Please run it inside LightWave.")
    sys.exit(1)

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # in case LightWave hasn't put this folder on sys.path
    sys.path.insert(0, _HERE)
import lw_mcp_config  # noqa: E402 - shared with server.py, see .env.example

PORT = lw_mcp_config.LAYOUT_PORT

_ok = lwsdk.LWCommandPort().enable(PORT)

_msg = "MCP Command Port %s on port %d" % (("enabled" if _ok else "FAILED to enable"), PORT)
# LWMessageFuncs().info() mirrors the C API's msg->info(text, detail) - it
# takes two string args (detail may be None), not just one, despite what
# the SDK doc's abbreviated example shows.
lwsdk.LWMessageFuncs().info(_msg, None)
