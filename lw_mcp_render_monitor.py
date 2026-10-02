"""
lw_mcp_render_monitor.py

Render-completion signal for ROADMAP.md item 6. Layout's Command Port
render commands (RenderFrame, RenderScene, RenderSelected) are one-way
fire-and-forget UDP sends (see lwcommandport/__init__.py's
_send_command - no response is ever read back), so there is no way to
know from the client side when a render actually finishes without
extending the read path. Firing RenderFrame and immediately assuming
success would just be guessing, which is exactly what ROADMAP.md item 6
calls out as the thing to avoid.

The real mechanism: register a custom "Frame Buffer" / Render Display
plug-in (lwsdk.IFrameBuffer / FrameBufferFactory), confirmed via
NewTek's official Python SDK docs (docs.lightwave3d.com/2025/
frame-buffer-class.html - fetched live since no docs ship with this
2019.1.5 install; this handler type's Python surface is not called out
as having changed across SDK versions). Real callbacks driven by the
render engine itself, not something we have to poll or guess at:

  - open(width, height): called when a rendering session begins.
  - write(r, g, b, a): called once per scanline as the frame renders.
  - close(): called when the rendering session is complete.
  - pause(display_name): called for F9/manual frame advance, but NOT
    during automatic (batch) rendering - useful signal on its own that
    a render is running non-interactively.

This plug-in ignores actual pixel data in write() - we don't need to
see the image, just know the render's state - and writes state to
_mcp_render_status.json on open()/close(). lw_mcp_ring.py's
"get_render_status" query reads that file and returns it over the
already-proven LWComRing read path, so no second polling mechanism is
needed on the client side beyond what lw_ping/_query already do.

RESOLVED (see PLAN.md "Multi-frame RenderScene progress tracking" for
the full investigation): open()/close() fire ONCE per whole render
session, not once per frame - confirmed live via a 4-frame RenderScene
producing exactly one open()/close() pair. The real per-frame(-ish)
signal is begin() (resets the scanline counter to 0 before write()
calls) - not previously implemented here, found by reading NewTek's
own bundled sample (support/plugins/scripts/Python/Layout/FrameBuffer/
framebuffer.py), which overrides it but this file originally didn't.
pause(display_name) does fire during automatic/batch RenderScene
rendering too (disproving this docstring's original assumption that it
was F9-only), alternating 'Alpha'/None - not used for frame_count.

IMPORTANT CORRECTION to an earlier version of this note: begin() is
NOT a clean scene-independent per-frame signal - it fires once per
ENABLED RENDER BUFFER per frame (confirmed live: Render Properties >
Buffers > Final_Render + Alpha both checked produced 8 begin() calls
for a 4-frame render; Final_Render alone produced a clean 4). See
begin()'s own docstring below. Also fixed a real bug found in the same
investigation: the plugin instance persists across separate
RenderScene calls within one Layout session, so frame_count was
continuing to climb across renders instead of resetting - now reset in
open(), not just __init__.

Bonus finding from the same investigation, unrelated to frame_count:
SetRenderDisplay DOES take an argument over the network
(SetRenderDisplay(display_name), e.g. "LW MCP Render Monitor") despite
this file's setup notes below (and lw_get_render_status's docstring)
originally claiming there was no networked way to select the active
Render Display - found via Cmd History showing a real
"SetRenderDisplay LW MCP Render Monitor" entry. The wrapped
lwcommandport method was simply missing its argument (fixed in
lwcommandport/layout/__init__.py, same class of bug as the Ring() fix
in lwcommandport/__init__.py). The one-time-per-session UI step below
is no longer strictly required if scripting the initial selection is
useful - though switching away and back is still sometimes needed to
force a fresh bind, the same activation flakiness this project's Master
Plugins already exhibit.

SETUP (once per fresh Layout session):
  1. Utilities > Plugins > Add Plugins > lw_mcp_render_monitor.py
  2. Render > Render Globals (or F9's panel) > Render Display tab (the
     UI location for the active Frame Buffer/display server) > select
     "LW MCP Render Monitor". This is a one-time manual UI step, same
     as the Master Plugins activation dance the rest of this project
     already depends on - confirmed via the local build's command list
     that SetRenderDisplay/RenderDisplayOptions take no arguments (see
     lwcommandport/layout/__init__.py), so there's no way to select it
     over the network; it must be chosen once in the UI.
"""
import json
import os
import time

import lwsdk

__lwver__ = "11"

import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # in case LightWave hasn't put this folder on sys.path
    sys.path.insert(0, _HERE)
import lw_mcp_config  # noqa: E402 - shared ports/exchange folder, see .env.example

STATUS_PATH = lw_mcp_config.exchange_path("_mcp_render_status.json")
DEBUG_LOG_PATH = lw_mcp_config.exchange_path("_mcp_render_debug.log")


def _log(line):
    try:
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _write_status(payload):
    payload["updated"] = time.time()
    tmp_path = STATUS_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(payload, f)
    try:
        os.remove(STATUS_PATH)
    except OSError:
        pass
    os.rename(tmp_path, STATUS_PATH)


class mcp_render_monitor(lwsdk.IFrameBuffer):
    def __init__(self, context):
        super(mcp_render_monitor, self).__init__()
        self._frame_count = 0
        self._width = None
        self._height = None
        _log("mcp_render_monitor instantiated, context=%r" % (context,))

    # LWFrameBuffer -------------------------------------------------------
    def open(self, width, height):
        # Fixes a real bug found live: the same plugin instance persists
        # across separate RenderScene invocations within one Layout
        # session (confirmed: a second render's begin() count continued
        # from the first's total instead of starting fresh), so
        # frame_count must reset here, not just in __init__.
        self._frame_count = 0
        self._width = width
        self._height = height
        _log("open: width=%d height=%d" % (width, height))
        _write_status({
            "rendering": True,
            "width": width,
            "height": height,
            "frame_count": self._frame_count,
        })
        return None

    def begin(self):
        # The real per-frame*buffer boundary signal - see this file's
        # module docstring. Not previously overridden here at all.
        # NOTE: fires once per ENABLED RENDER BUFFER per frame, not once
        # per frame alone - confirmed live with Render Properties >
        # Buffers > Final_Render + Alpha both enabled (8 begin() calls
        # for a 4-frame render) vs. Final_Render alone (a clean 4).
        # frame_count is therefore frame_count-times-enabled-buffers in
        # scenes with more than one Render-column buffer checked, not a
        # literal frame count - divide by the number of enabled buffers
        # if an exact frame count matters for a given scene.
        self._frame_count += 1
        _log("begin: frame_count=%d" % self._frame_count)
        _write_status({
            "rendering": True,
            "width": self._width,
            "height": self._height,
            "frame_count": self._frame_count,
        })

    def write(self, r, g, b, a):
        # Intentionally ignoring pixel data - we only care about the
        # begin/close lifecycle as a completion signal.
        return None

    def close(self):
        _log("close: frame_count=%d" % self._frame_count)
        _write_status({
            "rendering": False,
            "frame_count": self._frame_count,
        })

    def pause(self, display_name):
        _log("pause: display_name=%r" % (display_name,))


ServerTagInfo = [
    ("LW MCP Render Monitor", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.FrameBufferFactory("LW_MCP_RenderMonitor", mcp_render_monitor): ServerTagInfo,
}
