"""
lw_mcp_modeler_query.py

Read-path plug-in for Modeler (ROADMAP.md item 5). Modeler has no
Master-plugin/LWComRing equivalent - its Python plugin architecture is
CommandSequence-only (confirmed via Glob against the local install:
support/plugins/scripts/Python/Modeler/ only has a CommandSequence
folder, no Master folder). That turns out not to matter.

A CommandSequence plug-in registers as a normal invocable command,
exactly like built-in commands "New", "MergePoints", etc. - and
`modeler_run_command` in server.py already proves arbitrary named
commands are invocable over Modeler's Command Port (confirmed live
earlier this project via command="new" changing the title bar). A
public third-party Modeler plug-in
(github.com/heimlich1024/OD_CopyPasteExternal, found via web search)
confirmed that `mod_command.argument` carries whatever trailing text
was passed when the command was invoked - that project's Layout side
runs `lwsdk.command('ModCommand_OD_LWPasteFromExternal Layout')` and its
Modeler side reads `mod_command.argument` to get back `"Layout"`.

So: invoke this command by name with a trailing "command arg"-style
argument, read it back via mod_command.argument inside process(),
dispatch, and write the answer to a response file. Each call runs
synchronously and returns - no listener, no ring, no persistent state,
so none of the crash risk or activation flakiness that Layout's
LWComRing path had (see PLAN.md).

The mesh-reading pattern in _get_object_info is lifted directly from
NewTek's own bundled sample
(support/plugins/scripts/Python/Modeler/CommandSequence/
enumerate_surfaces.py) - editBegin/fastPointScan/fastPolyScan/
polyInfo/done - proven safe, and used here read-only (nothing is
modified).

SETUP (once per fresh Modeler session):
  Utilities > Plugins > Add Plugins > lw_mcp_modeler_query.py
  (registers the command - no separate "activation" step needed, unlike
  Layout's Master Plugins panel).
"""
import json
import os

import lwsdk

__lwver__ = "11"

import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # in case LightWave hasn't put this folder on sys.path
    sys.path.insert(0, _HERE)
import lw_mcp_config  # noqa: E402 - shared ports/exchange folder, see .env.example

RESPONSE_PATH = lw_mcp_config.exchange_path("_mcp_modeler_response.json")
DEBUG_LOG_PATH = lw_mcp_config.exchange_path("_mcp_modeler_debug.log")


def _log(line):
    try:
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _write_response(payload):
    tmp_path = RESPONSE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(payload, f)
    try:
        os.remove(RESPONSE_PATH)
    except OSError:
        pass
    os.rename(tmp_path, RESPONSE_PATH)


def _get_object_info(mod_command):
    """Point/poly counts and surface names for the foreground layer.
    Read-only: the edit op is engaged (required to query mesh data at
    all) but nothing is modified before done() is called."""
    points = []
    polys = []
    surfaces = set()

    def scan_point(pt_list, pt_id):
        pt_list.append(pt_id)
        return lwsdk.EDERR_NONE

    def scan_poly(poly_list, poly_id):
        poly_list.append(poly_id)
        return lwsdk.EDERR_NONE

    mesh_edit_op = mod_command.editBegin(0, 0, lwsdk.OPLYR_FG)
    if not mesh_edit_op:
        return {"error": "failed to engage mesh edit operations"}
    try:
        mesh_edit_op.fastPointScan(mesh_edit_op.state, scan_point, (points,), lwsdk.OPLYR_FG, 0)
        mesh_edit_op.fastPolyScan(mesh_edit_op.state, scan_poly, (polys,), lwsdk.OPLYR_FG, 0)
        for poly in polys:
            info = mesh_edit_op.polyInfo(mesh_edit_op.state, poly)
            surfaces.add(info.surface)
    finally:
        mesh_edit_op.done(mesh_edit_op.state, lwsdk.EDERR_NONE, 0)

    return {
        "point_count": len(points),
        "poly_count": len(polys),
        "surfaces": sorted(surfaces),
    }


class mcp_modeler_query(lwsdk.ICommandSequence):
    def __init__(self, context):
        super(mcp_modeler_query, self).__init__()
        _log("mcp_modeler_query instantiated")

    # LWCommandSequence -----------------------------------
    def process(self, mod_command):
        raw = (mod_command.argument or "").replace('"', '').strip()
        _log("process: argument=%r" % (raw,))
        parts = raw.split(None, 1)
        command = parts[0] if parts else "ping"
        arg = parts[1].strip() if len(parts) > 1 else ""

        try:
            if command == "ping":
                payload = {"result": "pong"}
            elif command == "get_object_info":
                payload = {"result": _get_object_info(mod_command)}
            else:
                payload = {"error": "unknown command: %s" % command}
        except Exception as exc:  # noqa: BLE001
            payload = {"error": str(exc)}

        _write_response(payload)
        return lwsdk.AFUNC_OK


ServerTagInfo = [
    ("LW MCP Modeler Query", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.CommandSequenceFactory("LW_MCP_ModelerQuery", mcp_modeler_query): ServerTagInfo,
}
