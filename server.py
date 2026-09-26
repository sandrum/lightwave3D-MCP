"""
server.py

MCP bridge between Claude and LightWave Layout, built on LightWave's
official Command Port.

VERIFIED STATUS (tested live against LightWave 2019.1.5, see PLAN.md for
the full log of what was tried):

- WRITES work end to end. lw.AddNull("TestFromMCP") sent from this
  machine's Python over UDP to Layout's Command Port produced a real Null
  item in the live scene, confirmed visually. Any of the ~800 native
  Layout commands exposed by the bundled `lwcommandport` client (copied
  here from support/python/lwcommandport in the LightWave install) should
  work the same way via lw_run_command below.

- READS now work too, via LWComRing (not LWEVNT_COMMAND - that was a
  confirmed dead end, see PLAN.md). The working mechanism, found in
  NewTek's own bundled sample
  (support/plugins/scripts/Python/Layout/Master/command_port_test.py):
  a Master plug-in calls lwsdk.LWComRing().ringAttach(
  lwsdk.LW_PORT_COMMAND_PORT, self, self.ring_event) and receives Command
  Port traffic wrapped as "{Topic} message". The client-side Ring(topic,
  command) method that formats that wrapper already existed in NewTek's
  bundled lwcommandport client - but it has a real bug under Python 3:
  `"{{0}} {1}".format(topic, command)` produces the literal string
  "{0} message" instead of "{MCP} message" (doubled braces escape to a
  literal brace instead of substituting). Confirmed live via
  _mcp_ring_debug.log. Fixed in lwcommandport/__init__.py.

  See lw_mcp_ring.py for the Master plug-in that must be loaded (Add
  Plugins) AND activated (Master Plugins panel) once per Layout session,
  alongside lw_enable_command_port.py.

Requires: pip install "mcp[cli]"
"""

import json
import os
import time

from mcp.server.fastmcp import FastMCP

from lwcommandport.layout import Layout
from lwcommandport.modeler import Modeler

HOST = "localhost"
PORT = 9735  # must match lw_enable_command_port.py
MODELER_PORT = 9736  # must match lw_enable_modeler_command_port.py

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_response.json")
MODELER_RESPONSE_PATH = os.path.join(_HERE, "_mcp_modeler_response.json")

mcp = FastMCP("lightwave")


def _layout():
    return Layout(address=HOST, port=PORT)


def _modeler():
    return Modeler(address=HOST, port=MODELER_PORT)


@mcp.tool()
def lw_run_command(command: str, args: list = None) -> str:
    """Send any native LightWave Layout command by name over the Command
    Port (e.g. command="AddLight", args=["Distant"]). This is a direct,
    one-way passthrough to LightWave's command language - the same
    commands available via hotkeys/menus/LScript. Confirmed working with
    AddNull; most of the ~800 commands in lwcommandport/layout/__init__.py
    should behave the same way. There is no response - this only tells
    you the command was sent, not whether LightWave accepted it."""
    lw = _layout()
    method = getattr(lw, command, None)
    if method is None:
        return json.dumps({"error": "no such command: %s" % command})
    try:
        method(*(args or []))
        return json.dumps({"result": "sent %s %s" % (command, args or [])})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def modeler_run_command(command: str, args: list = None) -> str:
    """Send any native LightWave Modeler command by name over Modeler's
    Command Port (a different mechanism than Layout's - see
    lw_enable_modeler_command_port.py). E.g. command="new" for New
    Object, command="boolean" for Boolean CSG, command="load",
    args=["path/to/file.lwo"] to load an object. See the Modeler class
    in lwcommandport/modeler/__init__.py for the full wrapped command
    list (mesh cleanup, extrude/clone/array tools, file ops). One-way,
    no confirmation LightWave accepted it - requires
    lw_enable_modeler_command_port.py to have been run in the current
    Modeler session first."""
    m = _modeler()
    method = getattr(m, command, None)
    if method is None:
        return json.dumps({"error": "no such command: %s" % command})
    try:
        method(*(args or []))
        return json.dumps({"result": "sent %s %s" % (command, args or [])})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


MODELER_QUERY_COMMAND = "LW_MCP_ModelerQuery"


def _modeler_query(command, arg="", timeout=5.0):
    """DOES NOT WORK OVER THE NETWORK - kept for the record and in case a
    future in-process invocation path is found. ROADMAP.md item 5:
    confirmed live (three ways, including against NewTek's own bundled
    sample plug-in, not just this project's code) that Modeler's network
    Command Port only reaches native/compiled commands, not
    Python-registered CommandSequence commands like
    lw_mcp_modeler_query.py's LW_MCP_ModelerQuery - unlike Layout, there
    is no LWComRing-style escape hatch for Modeler. This function will
    reliably time out. See PLAN.md "Modeler read path" for the full
    investigation. The plug-in itself works correctly when invoked from
    inside Modeler (e.g. Utilities > Additional menu) - it's specifically
    the external network call that never reaches it."""
    before_mtime = os.path.getmtime(MODELER_RESPONSE_PATH) if os.path.exists(MODELER_RESPONSE_PATH) else None

    cmd_string = ("%s %s %s" % (MODELER_QUERY_COMMAND, command, arg)).strip()
    m = _modeler()
    m._send_command(cmd_string)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(MODELER_RESPONSE_PATH):
            mtime = os.path.getmtime(MODELER_RESPONSE_PATH)
            if before_mtime is None or mtime > before_mtime:
                try:
                    with open(MODELER_RESPONSE_PATH) as f:
                        return json.load(f)
                except (ValueError, OSError):
                    pass
        time.sleep(0.1)

    return {"error": "timed out - is lw_mcp_modeler_query.py loaded (Add Plugins) in Modeler this session?"}


@mcp.tool()
def modeler_ping() -> str:
    """WILL ALWAYS TIME OUT - confirmed dead end, see PLAN.md "Modeler
    read path". Modeler's network Command Port doesn't route to
    Python-registered plug-in commands (unlike native ones like "new"),
    and Modeler has no LWComRing-style listener mechanism the way Layout
    does. Kept only for the record / in case a future workaround is
    found - don't spend time retrying this."""
    resp = _modeler_query("ping")
    return resp.get("result") or resp.get("error", "no response")


@mcp.tool()
def modeler_get_object_info() -> str:
    """WILL ALWAYS TIME OUT - see modeler_ping's docstring and PLAN.md
    "Modeler read path". Kept for the record only.

    (Intended behavior, unreachable over the network: point count,
    polygon count, and surface names for the foreground layer of the
    object currently open in Modeler, via lw_mcp_modeler_query.py.)"""
    return json.dumps(_modeler_query("get_object_info"))


@mcp.tool()
def lw_create_null(name: str = "MCP_Null") -> str:
    """Create a Null item in the current LightWave scene. Verified
    working: this sends AddNull over the Command Port and LightWave
    creates the item immediately."""
    try:
        _layout().AddNull(name)
        return json.dumps({"result": "sent AddNull %s" % name})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_load_object(filename: str) -> str:
    """Load a real mesh object (.lwo file) into the current LightWave
    scene - ROADMAP2.md item 2, closing this connector's biggest
    remaining capability gap (previously only Nulls could be created
    directly in Layout; real geometry needed a separate Modeler
    round-trip). Wraps the native LoadObject(filename) command -
    filename must be an absolute path LightWave's process can read
    (this is a one-way fire-and-forget send like every other write
    here, so there is no confirmation the file was found or loaded
    successfully beyond checking lw_get_scene_info afterward)."""
    try:
        _layout().LoadObject(filename)
        return json.dumps({"result": "sent LoadObject %s" % filename})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_save_scene_as(filename: str) -> str:
    """Save the current scene to a file - ROADMAP2.md item 3. Wraps
    SaveSceneAs(filename), not the bare SaveScene() (which takes no
    arguments and saves to the scene's already-known filename - not
    useful for a fresh unnamed scene, which is what every scene in this
    connector's testing has been so far). filename must be an absolute
    path LightWave's process can write to. Confirmed live: the saved
    file genuinely reflects real scene state (correct item names and
    numeric IDs), not a stub."""
    try:
        _layout().SaveSceneAs(filename)
        return json.dumps({"result": "sent SaveSceneAs %s" % filename})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_load_scene(filename: str) -> str:
    """Load a scene file, replacing the current scene - ROADMAP2.md
    item 3. Wraps the native LoadScene(filename) command. filename must
    be an absolute path LightWave's process can read. Confirmed live:
    a full save/clear/load round trip correctly restored every item.
    KNOWN GOTCHA: loading from a path outside LightWave's configured
    Content Directory pops a blocking "Change Content Directory?"
    dialog that a one-way command can't dismiss - answering "No"
    (keep the existing content path) still lets the scene load."""
    try:
        _layout().LoadScene(filename)
        return json.dumps({"result": "sent LoadScene %s" % filename})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_clear_scene() -> str:
    """Clear the current scene back to its default empty state (a
    default Light and Camera, no other items) - ROADMAP2.md item 3.
    Wraps the native ClearScene() command. Does not prompt to save
    unsaved changes first - this is a one-way fire-and-forget command
    like every other write here. Confirmed live: correctly removed
    every item down to just the default Light/Camera."""
    try:
        _layout().ClearScene()
        return json.dumps({"result": "sent ClearScene"})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_save_object(name: str, filename: str) -> str:
    """Save one object to its own file - ROADMAP2.md item 3. Wraps the
    native SaveObject(filename) command, which operates on the
    "current object" the same way several other single-argument
    commands in this connector do (see lw_set_keyframe).

    KNOWN LIMITATION, confirmed live, not yet solved: for a real
    multi-layer object loaded via lw_load_object, SelectItem(name)
    does NOT reliably switch the current object - unlike every other
    case in this connector (PLAN.md's "Second finding" established
    this for Camera/Light; it now also applies here). Resolving to the
    item's numeric ID (like every other lw_set_* tool does) is closer
    but still not sufficient on its own the FIRST time a freshly-loaded
    object is selected this session - Cmd History showed a genuine
    manual click sends a second, differently-scoped SelectItem call
    first (e.g. "SelectItem 40010000", not the object's own ID from
    lw_get_item_id) before the object's own numeric ID reliably takes
    effect afterward. That scoped ID's exact derivation is unconfirmed
    from a single data point, so it is NOT reproduced here - baking in
    an unverified formula would be worse than an honest limitation. If
    this silently saves the wrong object (check lw_get_selection
    before relying on the result), click the target object once in
    Layout's Scene Editor or viewport first, then retry - this appears
    to be a one-time per-object-per-session activation, not a
    per-call requirement, once the manual selection touches the object
    a single time. See PLAN.md 'Scene file I/O' for the full
    investigation. filename must be an absolute path LightWave's
    process can write to."""
    id_resp = _query("get_item_id", name)
    item_id = id_resp.get("result", {}).get("id")
    lw = _layout()
    try:
        lw.SelectItem(item_id or name)
        lw.SaveObject(filename)
        return json.dumps({"result": "saved %s to %s" % (name, filename), "resolved_id": item_id})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_keyframe(name: str, frame: int, position: list = None, rotation: list = None, scale: list = None) -> str:
    """Create a keyframe for an item at a given frame, optionally setting
    its position/rotation/scale first. Wraps the common by-hand animation
    sequence (ROADMAP.md item 4) - select the item, go to the frame, set
    the transform, create the key - into one call instead of chaining
    4+ separate lw_run_command calls. Any of position/rotation/scale left
    as None (the default) is not touched - the item keeps whatever value
    it currently has at this frame, so you can create a key on just one
    channel type if that's all you want. position and scale are each
    [x, y, z] triples; rotation is [heading, pitch, bank] in degrees,
    matching Layout's UI and command-line convention (confirmed live:
    values entered here appear in the Motion Options panel unchanged -
    note this is a different unit than the read-path's lw_get_transform,
    which reports rotation in radians per the LWItemInfo SDK global).
    Uses the native SelectItem/GoToFrame/Position/Rotation/Scale/CreateKey
    commands - all proven-reachable via lw_run_command already."""
    lw = _layout()
    try:
        lw.SelectItem(name)
        lw.GoToFrame(frame)
        if position is not None:
            lw.Position(*position)
        if rotation is not None:
            lw.Rotation(*rotation)
        if scale is not None:
            lw.Scale(*scale)
        lw.CreateKey(frame)
        return json.dumps({"result": "keyframed %s at frame %d" % (name, frame)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


RING_TOPIC = "MCP"


def _query(command, arg="", timeout=5.0):
    """Read path over LWComRing. Requires lw_mcp_ring.py to be loaded AND
    activated (Utilities > Master Plugins) in the current Layout session -
    see lw_mcp_ring.py's docstring for the two-step setup. Sends
    "{MCP} <command> <arg>" via the (bug-fixed) Ring() method, then polls
    _mcp_response.json for the plug-in's answer."""
    before_mtime = os.path.getmtime(RESPONSE_PATH) if os.path.exists(RESPONSE_PATH) else None

    cmd_string = ("%s %s" % (command, arg)).strip()
    _layout().Ring(RING_TOPIC, cmd_string)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(RESPONSE_PATH):
            mtime = os.path.getmtime(RESPONSE_PATH)
            if before_mtime is None or mtime > before_mtime:
                try:
                    with open(RESPONSE_PATH) as f:
                        return json.load(f)
                except (ValueError, OSError):
                    pass
        time.sleep(0.1)

    return {"error": "timed out - is lw_mcp_ring.py loaded AND activated in Master Plugins this session?"}


@mcp.tool()
def lw_ping() -> str:
    """Round-trip check that the read path (LWComRing) is alive. Returns
    "pong" if lw_mcp_ring.py is loaded and activated in the current Layout
    session, otherwise a timeout error explaining the two-step setup."""
    resp = _query("ping")
    return resp.get("result") or resp.get("error", "no response")


@mcp.tool()
def lw_get_scene_info() -> str:
    """Get the current scene name, filename, and item list (objects,
    lights, cameras) from the live LightWave scene via the LWComRing read
    path (see lw_mcp_ring.py)."""
    return json.dumps(_query("get_scene_info"))


@mcp.tool()
def lw_get_selection() -> str:
    """Get every item's name/type and whether it's currently selected in
    Layout, plus a convenience list of just the selected names. Confirmed
    live against LWItemInfo().selected() - note that flags() &
    LWITEMF_SELECTED does NOT reliably reflect selection state despite
    the name (tested, returned the same value for every item)."""
    return json.dumps(_query("get_selection"))


@mcp.tool()
def lw_add_to_selection(item: str) -> str:
    """Add an item to the current multi-selection without replacing it
    (ROADMAP2.md item 6) - unlike lw_set_parent's SelectItem-then-command
    shape, AddToSelection(itemid) IS the command, so this just resolves
    the numeric ID and sends it directly, no preceding SelectItem.

    Confirmed live end to end: after SelectItem on one Object then this
    on a second, lw_get_selection correctly showed BOTH as
    selected: true, and a Scene Editor screenshot confirmed both rows
    genuinely highlighted - not just an artifact of the read side. This
    closes out the original suspicion that AddToSelection "does
    nothing" (see PLAN.md "Multi-item / bulk selection investigation")
    - that read used the unreliable flags() & LWITEMF_SELECTED check
    lw_get_selection's own docstring warns about, not
    LWItemInfo().selected().

    IMPORTANT real limitation, also confirmed live: multi-selection
    does NOT make write commands apply to every selected item. Sending
    AddPosition(1, 0, 0) with two Objects selected this way only moved
    the second (the one most recently touched by AddToSelection) -
    the first, still shown as selected: true, did not move. Write
    commands sent over the Command Port act on a single "current item"
    pointer, not the highlighted selection set - this tool is for
    building a visual/selection-state result, not for batching writes
    across multiple items in one call. Every other write tool in this
    connector still needs its own per-item SelectItem/resolve-and-send
    loop."""
    item_id, id_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": id_resp})
    lw = _layout()
    try:
        lw.AddToSelection(item_id)
        return json.dumps({"result": "added %s (id %s) to selection" % (item, item_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_remove_from_selection(item: str) -> str:
    """Remove one item from the current multi-selection without
    affecting the rest (ROADMAP2.md item 6) - the inverse of
    lw_add_to_selection, same shape. Confirmed live: removing one of
    two Objects added via lw_add_to_selection correctly dropped it back
    to selected: false in lw_get_selection while the other stayed
    selected: true."""
    item_id, id_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": id_resp})
    lw = _layout()
    try:
        lw.RemoveFromSelection(item_id)
        return json.dumps({"result": "removed %s (id %s) from selection" % (item, item_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_get_camera_info(name: str = "Camera") -> str:
    """Get a camera's resolution, focal length, f-stop, field of view,
    zoom factor, shutter open time, shutter efficiency, and rolling
    shutter skew. Animatable values (focal length, f-stop, fov, zoom,
    and the shutter fields) are evaluated at LightWave's actual live
    playhead position (ROADMAP.md's long-standing "querying current
    time" limitation is solved - see lw_get_current_time), not a
    hardcoded time - the response's evaluated_at_time field reports
    exactly what time was used. The shutter_* fields (ROADMAP2.md item
    4, added as the read-side companion to lw_set_camera) use
    LWCameraInfo signatures not independently confirmed against NewTek
    docs the way the other fields were - if one is missing from a
    response, look for a "<field>_error" key instead; it degrades
    gracefully rather than breaking the whole query."""
    return json.dumps(_query("get_camera_info", name))


@mcp.tool()
def lw_get_light_info(name: str = "Light") -> str:
    """Get a light's type, falloff, color (RGB), intensity, and range.
    Same live-playhead evaluation as lw_get_camera_info for the
    animatable values. Known limitation: falloff is a stale read - it
    reports the scene-default value and does not reflect writes made
    via lw_set_light's falloff_type, confirmed live (UI screenshot
    showed the write took effect while this field kept reporting the
    old value). See lw_mcp_ring.py's _get_light_info for the
    investigation. color_rgb is intensity-multiplied, not the raw
    light color - LWLightInfo.color() behaves that way; there's a
    separate rawColor() accessor this doesn't use."""
    return json.dumps(_query("get_light_info", name))


@mcp.tool()
def lw_get_transform(name: str = "TransformTest") -> str:
    """Get an item's position, rotation, and scale from the live scene.
    Uses LWItemInfo().param() - confirmed via NewTek's C SDK docs and
    real-world Python plugin code, NOT the LWChannelInfo/nextGroup path
    that crashed Layout during development (see PLAN.md). Same
    live-playhead evaluation as lw_get_camera_info/lw_get_light_info -
    confirmed live on an animated item: correctly returned the
    interpolated frame-15 position, not the frame-0 default, when
    queried after GoToFrame(15)."""
    return json.dumps(_query("get_transform", name))


@mcp.tool()
def lw_get_current_time() -> str:
    """Get the time (seconds) and frame LightWave's live playhead is
    currently at - the same value lw_get_camera_info/lw_get_light_info/
    lw_get_transform now evaluate animatable channels at. Useful to
    confirm what time a read will use without needing an animated item,
    or to check the playhead position without moving it via GoToFrame.
    Uses lwsdk.LWTimeInfo() - a plain-attribute class in the same style
    as LWSceneInfo, found via a widened keyword search after the
    original introspection pass never looked for time/frame-related
    names at all. See PLAN.md 'live playhead time query' for the full
    investigation."""
    return json.dumps(_query("get_current_time"))


@mcp.tool()
def lw_get_surface_info(name: str) -> str:
    """Get a surface/material's color, diffuse, luminosity, specularity,
    glossiness, reflection, transparency, and smoothing by surface name.
    Uses LWSurfaceFuncs(), confirmed via real-world Python plugin code
    for calling conventions. Confirmed live against a real textured
    surface (ROADMAP2.md item 8): a loaded object's "CONNECTOR" surface
    read back color_rgb [0.784, 0.784, 0.784] (matching the Surface
    Editor's 200/200/200 - colors are 0.0-1.0 fraction here, 0-255 in
    the UI, same convention as lw_set_light's LightColor), glossiness
    0.4 (40%), diffuse 1.0 (100%), everything else 0.0 - exact match to
    the visible UI panel."""
    return json.dumps(_query("get_surface_info", name))


@mcp.tool()
def lw_set_surface(surface: str, color: list = None, diffuse: float = None,
                    luminosity: float = None, specularity: float = None,
                    glossiness: float = None, reflection: float = None,
                    transparency: float = None, smoothing: float = None) -> str:
    """Set a surface/material's properties (ROADMAP2.md item 8) - the
    write-side counterpart to lw_get_surface_info, and the FIRST write
    in this whole connector that goes through the read-path's Master
    plugin (LWComRing) instead of the one-way Command Port, since
    LWSurfaceFuncs (already used to read surfaces) is where the setter
    methods actually live - there's no native SurfaceEditor Command
    Port command, it just opens the UI panel. color is [r, g, b], each
    0.0-1.0 (same convention as lw_set_light's color); all other
    properties are 0.0-1.0 fractions matching lw_get_surface_info's
    read-back (e.g. glossiness=0.4 shows as "40.0%" in the UI).

    Confirmed live end to end against a real object's real surface
    ("CONNECTOR", from a loaded .lwo): sent diffuse=0.5 alone first, a
    Surface Editor screenshot showed 50.0% and lw_get_surface_info read
    back 0.5; then color=[1,0,0]+glossiness=0.8 in one call, screenshot
    showed a genuinely red color swatch (255/0/0) and "Glossiness 80.0%"
    (grayed out since Specular is 0% - a real UI precondition, not a
    sign anything's wrong), both matching lw_get_surface_info's
    read-back exactly.

    This call was briefly, INCORRECTLY believed to hang Layout forever
    on the first attempt - see lw_mcp_ring.py's _set_surface docstring
    for the full story. The real bug was a transport-level regex
    (_TOPIC_RE) that silently dropped any message containing its own
    "{"/"}" characters, which this tool's JSON-encoded wire format
    introduces - setFlt() was never actually reached that first time.
    Fixed by making that regex non-greedy, then re-verified live from
    scratch rather than trusting the fix on paper - see PLAN.md
    'Surface/material writes' for the full investigation, including why
    the original diagnosis was wrong and how it was caught."""
    props = {}
    if color is not None:
        props["color"] = list(color)
    for key, value in (
        ("diffuse", diffuse), ("luminosity", luminosity), ("specularity", specularity),
        ("glossiness", glossiness), ("reflection", reflection),
        ("transparency", transparency), ("smoothing", smoothing),
    ):
        if value is not None:
            props[key] = value
    arg = "%s|%s" % (surface, json.dumps(props))
    return json.dumps(_query("set_surface", arg))


@mcp.tool()
def lw_probe_channels(name: str = "TransformTest") -> str:
    """DIAGNOSTIC, temporary: probes lwsdk.LWChannelInfo() group/channel
    traversal against the named item, routed through the proven
    lw_mcp_ring.py listener (the dedicated diag4/5/6 Master plugins never
    received ring_event callbacks at all - root-caused to a stale/GC'd
    instance, see PLAN.md). Will be replaced by lw_get_transform once the
    real API shape is known."""
    return json.dumps(_query("probe_channels", name))


@mcp.tool()
def lw_probe_surf() -> str:
    """DIAGNOSTIC, temporary: lists SURF_* constants from lwsdk, routed
    through lw_mcp_ring.py. Will be replaced by lw_get_surface_info."""
    return json.dumps(_query("probe_surf"))


@mcp.tool()
def lw_set_camera_resolution(width: int, height: int) -> str:
    """Set the render resolution (ROADMAP.md item 6 camera setup half).
    Wraps the native FrameSize(width, height) command - this is a
    scene-wide render global in LightWave, not a per-camera setting
    (LightWave only renders through one camera at a time, selected via
    SelectItem), despite the name suggesting otherwise."""
    try:
        _layout().FrameSize(width, height)
        return json.dumps({"result": "sent FrameSize %d %d" % (width, height)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_camera(camera: str, zoom_factor: float = None, f_stop: float = None,
                   aperture_height: float = None, shutter_open: float = None,
                   shutter_efficiency: float = None, rolling_shutter: float = None) -> str:
    """Set camera properties - ROADMAP2.md item 4, the write-side
    counterpart to lw_get_camera_info (which has been read-only until
    now). Wraps ZoomFactor/LensFStop/ApertureHeight/ShutterOpen/
    ShutterEfficiency/RollingShutter, following lw_set_keyframe's
    pattern: any parameter left as None (the default) is not touched,
    so a single call can set just one property or several at once.

    Resolves `camera` to its numeric ID before calling SelectItem,
    rather than trusting SelectItem(name) - PLAN.md's "Second finding"
    already established SelectItem(name) is not reliable for Camera/
    Light the way it is for Objects, and every camera/light-targeting
    tool in this connector (lw_set_target, etc.) resolves to numeric
    IDs unconditionally for exactly this reason.

    CONFIRMED LIVE: zoom_factor and aperture_height take effect
    immediately (aperture_height's effect on focal_length_mm, given a
    fixed zoom_factor, is a real physical relationship, not a
    coincidence). f_stop ALSO confirmed live, but only after Depth of
    Field is enabled on the camera (native DepthOfField() command, a
    toggle with no direct read-back) - LightWave pops "This option only
    applies when Depth of Field is turned on" and silently no-ops
    otherwise. shutter_open/shutter_efficiency/rolling_shutter have the
    same kind of precondition (LightWave pops "This option only applies
    when Particle Blur or Motion Blur is turned on") - RESOLVED (see
    PLAN.md "Camera property writes" for the full story): the wrapped
    MotionBlur() was missing its argument entirely (fixed in
    lwcommandport/layout/__init__.py, same class of bug as the earlier
    Ring()/SetRenderDisplay() fixes) - it's a real enable/disable
    command (MotionBlur(1)/MotionBlur(0)), not the argument-less toggle
    it looked like from its own docstring. Confirmed live: after
    sending MotionBlur(1), all three shutter properties correctly read
    back the values previously set (they'd been silently accepted but
    not yet visible, the same way f_stop is before DepthOfField() is
    on - the underlying value sticks even while the precondition
    blocks it from taking visible effect). Call
    lw_run_command("MotionBlur", [1]) once per session before relying
    on these three properties, the same way lw_run_command
    ("DepthOfField", []) is needed once before f_stop."""
    camera_id, id_resp = _resolve_item_id(camera)
    if not camera_id:
        return json.dumps({"error": "could not resolve camera: %s" % camera, "detail": id_resp})
    lw = _layout()
    sent = []
    try:
        lw.SelectItem(camera_id)
        if zoom_factor is not None:
            lw.ZoomFactor(zoom_factor)
            sent.append("ZoomFactor")
        if f_stop is not None:
            lw.LensFStop(f_stop)
            sent.append("LensFStop")
        if aperture_height is not None:
            lw.ApertureHeight(aperture_height)
            sent.append("ApertureHeight")
        if shutter_open is not None:
            lw.ShutterOpen(shutter_open)
            sent.append("ShutterOpen")
        if shutter_efficiency is not None:
            lw.ShutterEfficiency(shutter_efficiency)
            sent.append("ShutterEfficiency")
        if rolling_shutter is not None:
            lw.RollingShutter(rolling_shutter)
            sent.append("RollingShutter")
        return json.dumps({"result": "set %s on %s (id %s)" % (sent, camera, camera_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_light(light: str, intensity: float = None, color: list = None,
                  falloff_type: int = None, cone_angle: float = None) -> str:
    """Set light properties - ROADMAP2.md item 5, the write-side
    counterpart to lw_get_light_info. Wraps LightIntensity/LightColor
    (color is [r, g, b], each 0.0-1.0)/LightFalloffType/LightConeAngle,
    following lw_set_camera's bundled-optional-params shape. Same
    numeric-ID SelectItem fix as lw_set_camera/lw_set_target. Confirmed
    live: intensity and color take effect immediately.

    falloff_type write confirmed live via UI screenshot (Light
    Properties showed the new "Intensity Falloff" setting immediately)
    - but lw_get_light_info's own falloff field is a known-stale read
    that never reflects it, an unfixed limitation documented in
    lw_mcp_ring.py's _get_light_info. falloff_type is also a real
    LightWave constraint, not a bug: it only applies to Point/Spot
    lights, confirmed via LightWave's own error dialog ("This option
    does not apply to the current light type") when tried on a Distant
    light. cone_angle only matters for spot/cone-type lights - not
    independently visually confirmed the way falloff_type was.

    Deliberately does NOT cover LightVisibleToCamera/LightCastsShadows.
    Both are confirmed-live, genuine argument-less TOGGLES (Cmd History
    shows a bare "LightVisibleToCamera"/"LightCastsShadows" with no
    following number after clicking their checkboxes - unlike
    MotionBlur, which looked the same way but turned out to take a real
    argument; this pair does not), so there's no way to set them to a
    known state or read one back. Use lw_run_command
    ("LightVisibleToCamera", []) / lw_run_command("LightCastsShadows",
    []) directly if needed, the same way lw_run_command("DepthOfField",
    []) is used to satisfy lw_set_camera's f_stop precondition. Also
    confirmed live: "Visible to Camera" is itself grayed out/disabled
    in the UI for Point lights - only Spot and Distant lights can use
    it at all, the mirror image of falloff_type's Point/Spot-only
    restriction.

    Also fixed a real bug found while building this: lwcommandport's
    LightFalloffType was defined TWICE (once correctly taking a `type`
    argument, then again with no arguments right after it) - Python
    silently keeps only the second definition, so the argument version
    was completely unreachable before this fix."""
    light_id, id_resp = _resolve_item_id(light)
    if not light_id:
        return json.dumps({"error": "could not resolve light: %s" % light, "detail": id_resp})
    lw = _layout()
    sent = []
    try:
        lw.SelectItem(light_id)
        if intensity is not None:
            lw.LightIntensity(intensity)
            sent.append("LightIntensity")
        if color is not None:
            lw.LightColor(*color)
            sent.append("LightColor")
        if falloff_type is not None:
            lw.LightFalloffType(falloff_type)
            sent.append("LightFalloffType")
        if cone_angle is not None:
            lw.LightConeAngle(cone_angle)
            sent.append("LightConeAngle")
        return json.dumps({"result": "set %s on %s (id %s)" % (sent, light, light_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_render_frame(frame: int = None) -> str:
    """Render a single frame (ROADMAP.md item 6). If frame is given,
    goes to that frame first (GoToFrame), then sends RenderFrame - both
    proven-reachable native commands. This call returns immediately once
    the command is sent, same one-way-fire-and-forget limitation as
    every other command here (see lwcommandport/__init__.py's
    _send_command) - it does NOT wait for the render to finish. Poll
    lw_get_render_status() afterward to know when it's actually done;
    see that tool's docstring for the required one-time setup."""
    lw = _layout()
    try:
        if frame is not None:
            lw.GoToFrame(frame)
        lw.RenderFrame()
        return json.dumps({"result": "sent RenderFrame%s" % (" (frame %d)" % frame if frame is not None else "")})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_render_scene() -> str:
    """Render the full configured frame range to disk/animation output
    (native RenderScene command). Same fire-and-forget caveat as
    lw_render_frame - use lw_get_render_status() to track progress and
    completion."""
    try:
        _layout().RenderScene()
        return json.dumps({"result": "sent RenderScene"})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_abort_render() -> str:
    """Abort an in-progress render (native AbortRender command)."""
    try:
        _layout().AbortRender()
        return json.dumps({"result": "sent AbortRender"})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_get_render_status() -> str:
    """Get the live render state - whether a render is in progress, the
    resolution, and a frame_count (see lw_mcp_render_monitor.py).
    Solves the actual problem in ROADMAP.md item 6: lw_render_frame/
    lw_render_scene are one-way fire-and-forget commands with no
    built-in completion signal, so this reads real callback-driven
    state over the LWComRing read path instead of guessing based on
    elapsed time.

    Multi-frame lw_render_scene progress tracking confirmed live and
    working: frame_count correctly climbs across a multi-frame render
    rather than jumping straight to done or stalling (not once per
    whole render session - open()/close() fire only once for the
    entire sequence; the real per-frame signal is IFrameBuffer.begin(),
    found via NewTek's own bundled sample plug-in after this project's
    own code had never overridden it). One real subtlety: begin() fires
    once per ENABLED RENDER BUFFER per frame (Render Properties >
    Buffers), not once per frame alone - confirmed live with
    Final_Render+Alpha both enabled (frame_count reached 8 for a
    4-frame render) vs. Final_Render alone (a clean 4). Divide
    frame_count by the number of enabled Render-column buffers if an
    exact frame count matters for a given scene. Also fixed a real bug
    in the same investigation: frame_count was continuing to climb
    across separate lw_render_scene calls within one Layout session
    instead of resetting - now resets on each new render.

    Requires a ONE-TIME manual setup step beyond the usual Add Plugins +
    Master Plugins dance: lw_mcp_render_monitor.py must additionally be
    selected as the active Render Display (Render Globals > Render
    Display tab). This can now also be done over the network via
    lw_run_command("SetRenderDisplay", ["LW MCP Render Monitor"]) -
    contrary to this tool's own earlier assumption, the native command
    does take an argument (confirmed via Cmd History showing a real
    "SetRenderDisplay LW MCP Render Monitor" entry); the wrapped
    lwcommandport method was just missing it (fixed). Before the
    display is set, or before any render has been triggered this
    session, rendering will be null, not a real in-progress/done state.
    Also: the Render Display dropdown selection appears to persist as a
    UI preference across sessions even though the underlying plug-in
    class needs re-loading via Add Plugins each fresh session, AND that
    reload can lock if the plugin is currently the active display -
    switch the display away first (e.g. to "Image Viewer"), reload,
    then switch back."""
    return json.dumps(_query("get_render_status"))


@mcp.tool()
def lw_get_item_id(name: str) -> str:
    """Get the plain numeric ID string (e.g. "10000000") LightWave's
    native item-reference commands (ParentItem, TargetItem, GoalItem,
    PoleItem) actually expect as their argument over the Command Port -
    NOT the item's name, despite their docstrings saying "(itemid)" the
    same way SelectItem's does. Root-caused by comparing Cmd History's
    log of a real, working UI-driven reparent (logged as literally
    "ParentItem 10000000") against this connector's failed attempts with
    a name string (logged as "TargetItem 0" - silently coerced to a
    no-op ID, no error, no dialog). SelectItem is the one exception that
    really does resolve names internally. See lw_set_parent for the
    wrapped fix; use this directly only if you need the raw ID for a
    command lw_set_parent doesn't cover yet (TargetItem/GoalItem/
    PoleItem)."""
    return json.dumps(_query("get_item_id", name))


def _resolve_item_id(name):
    """Shared by lw_set_parent/lw_set_target/lw_set_goal/lw_set_pole/
    lw_set_ik_options/lw_toggle_ik_flag - all these native commands
    share the same "wants a numeric ID, not a name" quirk (see
    lw_get_item_id's docstring), so they share this
    resolve-then-select-then-send shape too.

    A purely numeric `name` (e.g. "40000000") is passed through as-is
    rather than looked up by name. Needed for bones (ROADMAP2.md item
    7): lw_get_item_id/_find_item only searches Objects/Lights/Cameras,
    never bones (a separate LWI_BONE traversal, see lw_mcp_ring.py's
    _get_bones), so a bone has no name this resolver can look up at
    all - the caller must get its ID from lw_get_hierarchy (which
    reports each bone's "id" field) and pass that numeric string
    straight through."""
    if name.isdigit():
        return name, {"result": {"name": name, "id": name}}
    id_resp = _query("get_item_id", name)
    return id_resp.get("result", {}).get("id"), id_resp


def _set_reference_item(command, item, reference):
    """Common body for lw_set_parent/lw_set_target/lw_set_goal/
    lw_set_pole. Resolves BOTH item and reference to numeric IDs -
    confirmed live that SelectItem(name) only reliably switches the
    "current item" pointer this command family reads for Objects.
    Tested targeting a Camera by name ("SelectItem Camera"): the
    current OBJECT (an unrelated Null) got the target applied instead
    of the Camera. Cmd History of the equivalent manual action (select
    Camera, Motion Options, set Target Item) showed the real working
    sequence uses SelectItem on the Camera's own numeric ID (e.g.
    "SelectItem 30000000" - Camera/Light/Object each have their own ID
    range, confirmed 10000000/20000000/30000000 respectively), not its
    name. See PLAN.md 'ParentItem argument format' for the original
    numeric-ID finding this extends."""
    item_id, item_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": item_resp})
    ref_id, ref_resp = _resolve_item_id(reference)
    if not ref_id:
        return json.dumps({"error": "could not resolve item: %s" % reference, "detail": ref_resp})
    lw = _layout()
    try:
        lw.SelectItem(item_id)
        getattr(lw, command)(ref_id)
        return json.dumps({"result": "%s(%s) -> %s (ids %s -> %s)" % (command, item, reference, item_id, ref_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_parent(child: str, parent: str) -> str:
    """Reparent one item to another (ROADMAP.md's previously-unsolved
    write gap - see PLAN.md 'ParentItem argument format'). Confirmed
    root cause: ParentItem (and this whole command family - TargetItem/
    GoalItem/PoleItem) silently no-ops when given a name string instead
    of the numeric item ID it actually expects, AND relying on
    SelectItem(name) to pick the item being modified is only reliable
    for Objects - resolves both child and parent to their numeric IDs
    before sending, rather than trusting SelectItem's name resolution
    at all. Confirmed live: lw_get_hierarchy correctly showed the new
    parent afterward, matching ground truth from the Motion Options
    panel, on a fresh untouched pair of Nulls."""
    return _set_reference_item("ParentItem", child, parent)


@mcp.tool()
def lw_set_target(item: str, target: str) -> str:
    """Set an item's IK/camera/light target (e.g. point a Camera or
    Light at a Null) - same fix as lw_set_parent. Confirmed live for
    all three categories: targeting by Camera name alone
    (SelectItem("Camera")) applied the target to an unrelated,
    already-current Object instead of the Camera - Cmd History of the
    equivalent manual action showed the real working sequence selects
    the Camera by its own numeric ID (e.g. "SelectItem 30000000", not
    "SelectItem Camera"). Object/Light/Camera IDs live in separate
    numeric ranges (confirmed 10000000/20000000/30000000 respectively).
    Fixed by resolving both `item` and `target` to numeric IDs first.
    Confirmed live after the fix: both Camera.target and Light.target
    correctly showed the new target via lw_get_hierarchy. See PLAN.md
    'ParentItem argument format' for the full history."""
    return _set_reference_item("TargetItem", item, target)


@mcp.tool()
def lw_set_goal(item: str, goal: str) -> str:
    """Set an item's IK goal (GoalItem) - same numeric-ID-for-both-
    arguments fix as lw_set_parent/lw_set_target. Confirmed live: no
    bones/true IK chain needed to test, since goal()/pole() are
    generic per-item properties in the SDK (lw_get_hierarchy already
    queries them for every item type) - set on a plain Null,
    lw_get_hierarchy correctly showed the new goal afterward."""
    return _set_reference_item("GoalItem", item, goal)


@mcp.tool()
def lw_set_pole(item: str, pole: str) -> str:
    """Set an item's IK pole (PoleItem) - same fix as lw_set_goal.
    Confirmed live the same way, set alongside a goal on the same
    plain Null with lw_get_hierarchy correctly showing both
    afterward."""
    return _set_reference_item("PoleItem", item, pole)


@mcp.tool()
def lw_set_ik_options(item: str, goal_strength: float = None, ik_fk_blending: float = None) -> str:
    """Set an item's chain-level IK numeric properties (ROADMAP2.md item
    7, the piece lw_set_goal/lw_set_pole don't cover - those handle
    which item is the goal/pole, this handles how strongly the chain
    follows it). Wraps GoalStrength/IKFKBlending, following
    lw_set_camera/lw_set_light's bundled-optional-params shape and the
    same numeric-ID SelectItem pattern. Both already took a real
    argument in lwcommandport - no stub bug found here, unlike several
    other commands surveyed this phase.

    Confirmed live on a real bone (Bone1, in an actual BoneTestObject
    chain, with a Goal Object already assigned via lw_set_goal): sent
    goal_strength=0.5, ik_fk_blending=0.3, and a Motion Options
    screenshot showed "Goal Strength: 0.5" and "IK/FK Blending: 30.0%"
    immediately. ik_fk_blending is a 0.0-1.0 fraction displayed as a
    percentage, the same convention as lw_set_camera's
    shutter_efficiency - 0.3 shows as 30.0%, not 0.3%. Neither property
    showed a precondition the way FullTimeIK does (see
    lw_toggle_ik_flag) - both were visible and settable in Motion
    Options before any Goal Object was assigned."""
    item_id, id_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": id_resp})
    lw = _layout()
    sent = []
    try:
        lw.SelectItem(item_id)
        if goal_strength is not None:
            lw.GoalStrength(goal_strength)
            sent.append("GoalStrength")
        if ik_fk_blending is not None:
            lw.IKFKBlending(ik_fk_blending)
            sent.append("IKFKBlending")
        return json.dumps({"result": "set %s on %s (id %s)" % (sent, item, item_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_toggle_ik_flag(item: str, flag: str) -> str:
    """Flip FullTimeIK or UnaffectedByIK for an item's IK chain
    (ROADMAP2.md item 7). flag must be "full_time_ik" or
    "unaffected_by_ik".

    Both are confirmed live to be genuine argument-less TOGGLES, same
    situation as lw_set_light's deliberately-unwrapped
    LightVisibleToCamera/LightCastsShadows: Cmd History showed a bare
    "FullTimeIK"/"UnaffectedByIK" with no argument following after
    clicking each real checkbox in Motion Options > IK and Modifiers on
    a live bone. There is no way to read either flag's current state
    back, so this FLIPS whatever it currently is rather than setting a
    known value - call it once, then check the Motion Options panel (or
    just call it again to flip back) if the direction matters.

    Real precondition confirmed live: "Full-time IK" is grayed out and
    unclickable in the UI until the item has a Goal Object assigned
    (lw_set_goal) - LightWave auto-checked it as a side effect of
    assigning the goal, before this tool was ever called, rather than
    requiring a separate command. "Unaffected by IK of Descendants" had
    no such precondition - it was clickable immediately."""
    item_id, id_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": id_resp})
    command = {"full_time_ik": "FullTimeIK", "unaffected_by_ik": "UnaffectedByIK"}.get(flag)
    if not command:
        return json.dumps({"error": "flag must be 'full_time_ik' or 'unaffected_by_ik', got %r" % flag})
    lw = _layout()
    try:
        lw.SelectItem(item_id)
        getattr(lw, command)()
        return json.dumps({"result": "toggled %s on %s (id %s)" % (command, item, item_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_include_light(light: str, obj: str) -> str:
    """Add an object to a light's inclusion list (Light Properties >
    Objects tab, "Include" mode - unchecked "Exclude" column) - the
    light will only illuminate objects on this list once that mode is
    set. ROADMAP2.md item 1. Same numeric-ID-for-both-arguments fix as
    lw_set_parent/lw_set_target - confirmed live this generalizes
    cleanly to this command pair too (Cmd History showed the correctly
    resolved numeric IDs, e.g. "IncludeObject 10000000", not a raw
    name). Confirmed live end to end via the actual UI panel, not just
    the command log. The same relationship is also visible, and
    settable, from the object's own side - see lw_include_object_light -
    via its Item Properties > Lights tab (opened with the native
    ItemProperties command); both panels stay in sync since it's the
    same underlying data, not two separate lists."""
    return _set_reference_item("IncludeObject", light, obj)


@mcp.tool()
def lw_exclude_light(light: str, obj: str) -> str:
    """Add an object to a light's exclusion list (Light Properties >
    Objects tab, "Exclude" mode - checked "Exclude" column) - the light
    will illuminate every object except those on this list once that
    mode is set. Same fix as lw_include_light. Confirmed live: toggling
    an object from Include to Exclude (or vice versa) correctly updates
    the same list entry's checkbox rather than creating a duplicate."""
    return _set_reference_item("ExcludeObject", light, obj)


@mcp.tool()
def lw_include_object_light(obj: str, light: str) -> str:
    """Add a light to an object's inclusion list - the same
    relationship as lw_include_light, set from the object's side via
    the native IncludeLight command instead of IncludeObject. Confirmed
    live: visible on the object's own Item Properties > Lights tab
    (open via the native ItemProperties command with the object
    selected), which stays in sync with the light's own Objects tab -
    the same underlying data either way, not two separate lists."""
    return _set_reference_item("IncludeLight", obj, light)


@mcp.tool()
def lw_exclude_object_light(obj: str, light: str) -> str:
    """Add a light to an object's exclusion list - the ExcludeLight
    counterpart to lw_include_object_light, same relationship as
    lw_exclude_light set from the object's side. Confirmed live: after
    calling this, both the object's own Item Properties > Lights tab
    AND the light's own Properties > Objects tab correctly showed the
    "Exclude" checkbox checked for each other."""
    return _set_reference_item("ExcludeLight", obj, light)


@mcp.tool()
def lw_get_hierarchy() -> str:
    """Get parent/child and IK (target/goal/pole) relationships for every
    object, light, and camera in the scene - e.g. before rigging on top
    of an object that's already parented to something else. Each item
    reports its own name/type plus the name of its parent (None if it
    has none), and its IK target/goal/pole items if any are set. Uses
    LWItemInfo.parent()/target()/goal()/pole(), confirmed via NewTek's
    official SDK docs - the same LWItemInfo class already proven safe
    elsewhere in this connector (lw_get_transform), not the LWChannelInfo
    path that crashed Layout during development (see PLAN.md).

    Also walks bone chains within each object (STATUS.md's last real
    open item, now closed) - LWItemInfo.first(LWI_BONE, object)/next(),
    confirmed live and safe against a real 2-bone chain (unlike
    LWChannelInfo/nextGroup, which crashed Layout outright - see
    PLAN.md). Bones don't need a real mesh object to test against:
    AddBone/AddChildBone attach directly to a Null. Each object's
    entry gets a "bones" list (only present if non-empty) with the
    same name/parent/target/goal/pole shape as every other item here."""
    return json.dumps(_query("get_hierarchy"))


if __name__ == "__main__":
    mcp.run()
