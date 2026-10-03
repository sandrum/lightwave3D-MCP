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

import lw_mcp_config  # shared ports/exchange folder - see .env.example

HOST = lw_mcp_config.HOST
PORT = lw_mcp_config.LAYOUT_PORT
MODELER_PORT = lw_mcp_config.MODELER_PORT

RESPONSE_PATH = lw_mcp_config.exchange_path("_mcp_response.json")
MODELER_RESPONSE_PATH = lw_mcp_config.exchange_path("_mcp_modeler_response.json")

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
def lw_set_content_directory(path: str) -> str:
    """Set LightWave's Content Directory (ROADMAP3.md item 1). Wraps the
    native ContentDirectory(dirname) command - path must be an absolute
    directory LightWave's process can read.

    Confirmed live: this closes a real, previously-documented limitation
    (ROADMAP2.md item 3) - loading a scene from a path outside the
    configured Content Directory used to pop a blocking "Change Content
    Directory?" dialog that a one-way command couldn't dismiss (the only
    workaround was asking a human to click "No" every time). Calling
    this with the target path BEFORE lw_load_scene/lw_load_object
    eliminates the dialog entirely - confirmed by reloading the exact
    scene/path combination that previously triggered it and getting a
    silent, successful load instead, verified via lw_get_scene_info
    showing every item intact afterward. Call this once per session
    before loading from a path outside whatever Content Directory
    LightWave started with.

    See lw_set_content_type_directory for the per-content-type sub-path
    counterpart (Objects/Scenes/Images/etc.). CreateContentPath/
    RecentContentDirs also exist in the command list but weren't wrapped
    here - both look like one-shot UI actions (opening a dialog/menu)
    rather than pure setters."""
    try:
        _layout().ContentDirectory(path)
        return json.dumps({"result": "sent ContentDirectory %s" % path})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_content_type_directory(content_type: str, dirname: str) -> str:
    """Set a per-content-type sub-path under the base Content Directory
    (Preferences > Paths tab, the "Scenes"/"Objects"/"Images"/etc. button
    list). Wraps the native ContentTypeDirectory(type, dirname) command.

    `content_type` must exactly match one of the panel's own labels:
    "Scenes", "Hierarchies", "Objects", "Images", "Envelopes", "Motions",
    "Previews", "Animations", "Surfaces", "Nodes", "Shaders", "Dynamics",
    "Rigs", "Sounds", "Lights", "Radiosity", "Color Tables", "Image
    Cache", "Vert Cache", "Grid Cache", "Output Directory", or "Backup
    Directory" - confirmed live only for "Objects", the rest are
    inferred from the visible panel labels, not independently tested.

    Confirmed live: `content_type_directory("Objects", "TestObjDir")`
    changed the "Objects" row's own button label from "Objects" to
    "TestObjDir" - these buttons double as a live display of the
    current sub-path (not fixed captions), giving a built-in
    confirmation mechanism with no separate read-back needed. Reverting
    with `("Objects", "Objects")` correctly restored the "Objects"
    label. `dirname` can be given as an absolute path; LightWave
    displays only the portion beyond the base Content Directory when
    it's a sub-path of it."""
    try:
        _layout().ContentTypeDirectory(content_type, dirname)
        return json.dumps({"result": "sent ContentTypeDirectory %s %s" % (content_type, dirname)})
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
    file reflects real scene state (correct item names and
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
    KNOWN GOTCHA, NOW SOLVABLE: loading from a path outside LightWave's
    configured Content Directory pops a blocking "Change Content
    Directory?" dialog that a one-way command can't dismiss - answering
    "No" (keep the existing content path) still lets the scene load, but
    needs a human present. ROADMAP3.md item 1's lw_set_content_directory
    eliminates this dialog entirely when called with the target path
    first - confirmed live, no human intervention needed."""
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
    object is selected this session - Cmd History showed a real
    manual click sends a second, differently-scoped SelectItem call
    first (e.g. "SelectItem 40010000", not the object's own ID from
    lw_get_item_id) before the object's own numeric ID reliably takes
    effect afterward. That scoped ID's exact derivation is unconfirmed
    from a single data point, so it is NOT reproduced here - baking in
    an unverified formula would be worse than a known limitation. If
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
    highlighted - not just an artifact of the read side. This
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
def lw_get_antialiasing(camera: str = "Camera") -> str:
    """Read a camera's antialiasing/sampling settings: `min_samples`,
    `max_samples`, `filter_radius` (Camera Properties' "Filter Radius")
    and `noise_sampler` for that camera, plus `adaptive_sampling` (1/0),
    `adaptive_threshold` and the render's `reconstruction_filter` (e.g.
    "Gaussian"; `filter_raw` is the underlying bitfield) from the scene,
    which LightWave reports for the render camera."""
    return json.dumps(_query("get_antialiasing", camera))


@mcp.tool()
def lw_get_light_info(name: str = "Light") -> str:
    """Get a light's type, falloff, color (RGB), intensity, and range.
    Same live-playhead evaluation as lw_get_camera_info for the
    animatable values. `falloff` is the Intensity Falloff setting:
    0 = Off, 1 = Inv Distance^2 - the only two options LightWave 2019
    has, matching the SDK's LWLFALL_OFF/LWLFALL_ON. Confirmed live to
    follow both hand changes and lw_set_light writes - provided Light
    Properties is closed when a write arrives: with the panel open the
    reading stays stale (see lw_set_light). color_rgb is
    intensity-multiplied, not the raw light color - LWLightInfo.color()
    behaves that way; there's a separate rawColor() accessor this
    doesn't use."""
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
    showed a red color swatch (255/0/0) and "Glossiness 80.0%"
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
def lw_get_channels(name: str) -> str:
    """Get an item's real keyframe/envelope structure - which channels
    exist (Position.X, Rotation.H, etc.), and for each, every keyframe's
    frame/time, value, and interpolation shape (ROADMAP2.md item 9).
    Closes the gap lw_get_transform's single-point-in-time evaluation
    always had: that tool only ever reports the value at one instant,
    this reports the actual underlying keyframe data.

    Built on LWChannelInfo/LWEnvelopeFuncs, the exact SDK area with this
    project's one other confirmed real crash (LWChannelInfo().nextGroup
    called with an item's own ID - see PLAN.md 'LWChannelInfo crash').
    That crash is NOT re-triggered here: this uses
    LWItemInfo().chanGroup(item) (confirmed live to directly enumerate
    an item's own channels via nextChannel, no nextGroup() call needed
    at all for this purpose) plus nextKey/keyGet on each channel's
    envelope - every one of these calls was explicitly tested live, with
    user approval given the crash history, before this real bounded loop
    was written; see PLAN.md 'Keyframe/envelope reading' for the full
    staged investigation. "shape" is the raw LWKEY_SHAPE integer
    (LightWave's own interpolation-curve type, as seen in the Graph
    Editor) - not translated to a name, since no confirmed mapping was
    established this session. "frame" is derived from the raw seconds
    value via LWSceneInfo().framesPerSecond, the same convention
    lw_get_current_time already uses; "time_seconds" is also included.

    Confirmed live two ways: a static, never-keyframed Null correctly
    showed all 9 channels with exactly one implicit key each at frame 0
    (Position 0.0, Rotation 0.0, Scale 1.0 - LightWave's real defaults).
    A Null keyframed via lw_set_keyframe at frames 0 and 30 (position
    only) correctly showed the real multi-key data - and surfaced a
    new, previously-unobservable LightWave behavior: every
    channel also got an extra key at the scene's configured end frame
    (holding its last value), and channels whose value never actually
    changed between the two lw_set_keyframe calls (Rotation/Scale) got
    only that end-frame key, not a redundant real one at frame 30 -
    LightWave's CreateKey appears to skip adding a keyframe when the
    value hasn't changed. This was invisible before this tool existed,
    since lw_get_transform can only sample a value, never see whether a
    real key exists at a given frame."""
    return json.dumps(_query("get_channels", name))


@mcp.tool()
def lw_get_surface_nodes(surface: str = "CONNECTOR") -> str:
    """List every node in a surface's node graph (ROADMAP3.md item 2) -
    e.g. "Surface", "Input", "Standard (1)", "Principled BSDF (1)" for a
    surface with a Principled BSDF added. Each entry has node_name (the
    specific instance, with a "(N)" suffix when more than one of the
    same type exists) and server_user_name (the plain node-type name,
    e.g. "Principled BSDF", without that suffix) - use server_user_name
    to find a node type regardless of instance count, node_name to
    address one specific instance in lw_get_node_inputs/
    lw_get_node_channel.

    Confirmed live: even a "Standard"-material surface that was never
    manually node-edited already has an implicit 3-node graph ("Surface"/
    "Input"/"Standard (1)") - LightWave's nodal architecture underlies
    every surface, not just ones built by hand in the Node Editor."""
    return json.dumps(_query("get_surface_nodes", surface))


@mcp.tool()
def lw_get_node_inputs(surface: str = "CONNECTOR", node: str = "Principled BSDF (1)") -> str:
    """List a specific node's input parameter names (ROADMAP3.md item 2)
    - e.g. Principled BSDF's "Color"/"Roughness"/"Metallic"/etc. `node`
    must match a node_name from lw_get_surface_nodes exactly. Confirmed
    live to correctly enumerate all 27 real Principled BSDF parameters,
    exactly matching the Surface Editor panel.

    Does NOT report each input's current value - LightWave's
    LWNodeInputFuncs.evaluate_scalar/evaluate_vector both failed live
    needing extra shading context this connector has no way to supply
    outside an active render. Use lw_get_node_values for the values
    (read from the saved graph instead), and lw_get_node_channel for an
    enveloped parameter's keyframes."""
    return json.dumps(_query("get_node_inputs", "%s|%s" % (surface, node)))


@mcp.tool()
def lw_get_node_channel(surface: str = "CONNECTOR", node: str = "Principled BSDF (1)",
                         channel: str = "Roughness") -> str:
    """Read a node parameter's real keyframe data (ROADMAP3.md item 2) -
    frame/time, value, and interpolation shape, the same shape
    lw_get_channels already reports for item transform channels. `node`
    must match lw_get_surface_nodes' node_name, `channel` must match one
    of lw_get_node_inputs' parameter names.

    This was the core question of a full staged investigation (see
    PLAN.md "Node Editor / PrincipledBSDF nodes" for the complete
    writeup): the real path mirrors ROADMAP2.md item 9's item-channel
    discovery almost exactly. LWSurfaceFuncs().chanGrp(surf) is a
    surface's own top-level channel group; one nextGroup() hop reaches a
    "Nodes" container; a second nextGroup() hop within "Nodes", matched
    by name, reaches the specific node's own group; nextChannel() within
    THAT group finds the parameter - but ONLY once a human (or a future
    write tool) has explicitly added an envelope to it. An un-enveloped
    parameter's group has zero channels (confirmed live: not a crash,
    legitimately empty), and the exact same parameter appears the
    instant an envelope is added. Once found, channelEnvelope()/
    nextKey()/keyGet() are the identical, already-proven-safe calls
    lw_get_channels already uses.

    Confirmed live end to end: after enveloping Principled BSDF's
    "Roughness", this correctly read back value 0.1 at frame 0, matching
    the UI's "10.0%" exactly. Reports "channel not found" for any
    parameter that hasn't been enveloped - the current boundary,
    not a bug."""
    return json.dumps(_query("get_node_channel", "%s|%s|%s" % (surface, node, channel)))


@mcp.tool()
def lw_probe_surf() -> str:
    """DIAGNOSTIC, temporary: lists SURF_* constants from lwsdk, routed
    through lw_mcp_ring.py. Will be replaced by lw_get_surface_info."""
    return json.dumps(_query("probe_surf"))


@mcp.tool()
def lw_probe_node_write() -> str:
    """DIAGNOSTIC, temporary: safe dir() scan (zero risk) of the
    node-related SDK classes found during ROADMAP3.md item 2's read-side
    investigation (LWNodeFuncs/LWNodeEditorFuncs/LWNodeInputFuncs/
    LWNodeOutputFuncs/LWNodeUtilityFuncs/LWNodeDrawFuncs/
    LWNodeMenuFuncs), filtered for write-suggestive method names
    (add/create/new/insert/remove/delete/connect/set/etc.). Step 1 of
    the Node Editor writing investigation - no live SDK calls beyond
    constructing fresh instances and introspecting them, following the
    same staged discipline the read-side investigation used. Will be
    removed once the real write API shape is known and permanent tools
    are shipped."""
    return json.dumps(_query("probe_node_write"))


@mcp.tool()
def lw_probe_node_write_sigs() -> str:
    """DIAGNOSTIC, temporary: step 2 of the Node Editor writing
    investigation. Calls each write-candidate method found by
    lw_probe_node_write with zero arguments and captures the resulting
    Python TypeError message - the same safe signature-discovery
    technique already used for evaluate_scalar/evaluate_vector during
    the read-side investigation. Cannot touch scene state: a bad
    argument count fails in Python before any native LightWave call is
    made."""
    return json.dumps(_query("probe_node_write_sigs"))


@mcp.tool()
def lw_add_node(surface: str = "CONNECTOR", node_type: str = "Principled BSDF",
                x: int = 0, y: int = 0) -> str:
    """Create a new, unconnected node in a surface's node graph (Node
    Editor writing, step 1). Returns the new node's node_name (e.g.
    "Principled BSDF (2)" - one past the highest existing instance) and
    server_user_name, ready for lw_connect_nodes / lw_get_node_inputs.
    `x`/`y` place it in the Node Editor's graph view (default 0, 0 - the
    origin, where it can overlap other nodes); larger values go left/up,
    roughly a pixel per unit - see lw_move_node for the details.

    **CRITICAL, confirmed live: an invalid `node_type` freezes Layout.**
    `node_type` must be an exact server_user_name string already
    confirmed to exist via lw_get_surface_nodes on a real node instance
    (e.g. "Principled BSDF", "Standard") - NOT a category name from the
    Node Editor's own "Add Node" browser panel (e.g. "Constant" is a
    CATEGORY heading there, not a real node type name) and not a guess.
    An unknown type pops a modal "Plug-in Missing: No plug-in of type
    NodeHandler found..." dialog that freezes Layout's main thread until
    a human clicks "No" - the same failure shape as the Content
    Directory dialog from ROADMAP2.md item 3.

    Uses the same save/rewrite/load route as lw_connect_nodes: saves
    the graph as ASCII, appends a minimal node block (empty data, so
    the node starts from its own defaults), loads it back, and confirms
    the node exists afterwards. It does NOT use LWNodeEditorFuncs.addNode
    any more: nodes made by addNode look normal but poison the graph -
    a later load of it never returns and wedges the connector until
    Layout restarts (confirmed live twice; the identical load over a
    hand-added node worked), and they plausibly caused every
    LWNodeEditorFuncs.connect freeze too. A graph that still contains
    an addNode-made node from an older version of this tool will hang
    here as well - restart Layout without saving first.

    Close and reopen an open Surface Editor to see changes; safest with
    the Node Editor closed. See PLAN.md "Node Editor writing"."""
    return json.dumps(_query("add_node", "%s|%s|%d|%d" % (surface, node_type, x, y)))


@mcp.tool()
def lw_connect_nodes(surface: str = "CONNECTOR", from_node: str = "Principled BSDF (1)",
                     to_node: str = "Surface", input_name: str = "Material",
                     output_name: str = "") -> str:
    """Wire one node's output into another node's input in a surface's
    node graph (Node Editor writing, step 2), replacing whatever fed
    that input before.

    `from_node`/`to_node` are node_name values from lw_get_surface_nodes
    (e.g. "Principled BSDF (1)"); `to_node="Surface"` is the root output
    node. `input_name` is an input on `to_node` as listed by
    lw_get_node_inputs (for "Surface": Material, Normal, Bump,
    Displacement, Clip - its OpenGL input can't currently be addressed).
    `output_name` selects an output on `from_node`; empty means its
    first output (Principled BSDF has exactly one, "Material"). Unknown
    node/socket names return an error listing what's available, and
    nothing changes. To wire in a node that isn't in the graph yet, add
    it with lw_add_node first.

    Does NOT call LWNodeEditorFuncs.connect: that made the connection
    but froze Layout's UI in all three live runs (it had to be killed
    from Task Manager each time). Instead it saves the surface's whole
    graph as ASCII, rewrites the file's "{ Connections }" block (which
    names every wire by node and socket name), and loads it back -
    confirmed live to replace the graph exactly with Layout staying
    responsive. The graph is then saved again and the result reports
    the connections LightWave actually has afterwards (`connected`:
    true/false), plus the `before` list.

    An open Surface Editor does not refresh: close and reopen it to see
    the new Material. Safest with the Node Editor closed - the load
    route has only been tested that way. See PLAN.md "Node Editor
    writing" for the full investigation."""
    return json.dumps(_query("connect_nodes", "%s|%s|%s|%s|%s"
                             % (surface, from_node, to_node, input_name, output_name)))


@mcp.tool()
def lw_disconnect_nodes(surface: str = "CONNECTOR", to_node: str = "Surface",
                        input_name: str = "Material") -> str:
    """Remove the wire feeding one input in a surface's node graph -
    the counterpart of lw_connect_nodes, using the same save/rewrite/
    load route (not LWNodeEditorFuncs.connect/disconnect). `to_node` is
    a node_name from lw_get_surface_nodes ("Surface" for the root
    output node) and `input_name` an input on it. Returns an error if
    nothing is connected there. Reports `disconnected` and the
    connections LightWave has afterwards. Close and reopen an open
    Surface Editor to see the change; safest with the Node Editor
    closed."""
    return json.dumps(_query("disconnect_nodes", "%s|%s|%s" % (surface, to_node, input_name)))


@mcp.tool()
def lw_remove_node(node: str, surface: str = "CONNECTOR") -> str:
    """Delete a node from a surface's node graph, together with every
    wire to or from it. `node` is a node_name from lw_get_surface_nodes
    (e.g. "Principled BSDF (1)"); "Surface" and "Input" are built into
    every surface and are refused. Reports `removed`, the wires that
    went with it (`wires_removed`), and the nodes and connections
    LightWave has afterwards.

    Removing the node that feeds Surface > Material leaves the surface
    with no material - connect another one first (lw_connect_nodes) if
    that isn't intended.

    Uses the same save/rewrite/load route as lw_add_node and
    lw_connect_nodes (drops the node's block and its wires from the
    saved graph text, then loads it back), not
    LWNodeEditorFuncs.destroyNode - the node SDK's direct mutators have
    proven unsafe here (see lw_add_node). Close and reopen an open
    Surface Editor to see the change; safest with the Node Editor
    closed."""
    return json.dumps(_query("remove_node", "%s|%s" % (surface, node)))


@mcp.tool()
def lw_move_node(node: str, x: int, y: int, surface: str = "CONNECTOR") -> str:
    """Reposition a node in the Node Editor's graph view - purely
    cosmetic, no effect on shading. `node` is a node_name from
    lw_get_surface_nodes (any node, including "Surface" and "Input").
    `x`/`y` are the graph's own stored coordinates, as they appear in
    LightWave's saved node data. Reports `before`, the `coordinates`
    LightWave has afterwards, and `moved`.

    Confirmed live: both axes run BACKWARDS - a larger x moves a node
    left, a larger y moves it up - at roughly 1 screen pixel per unit at
    100% zoom (1.5-1.9 before the Node Editor has ever been opened).
    Exact screen placement isn't predictable: opening the Node Editor
    makes LightWave rewrite the stored coordinates in its own frame
    (a node set to -200, 100 read back as -421, -185 afterwards), so use
    this to space nodes apart - a few hundred units is plenty - and the
    Node Editor's own "Tidy Nodes" button for a proper layout. The
    Surface node is stored almost on top of Input and can hide behind
    it; move it clear if needed.

    Same save/rewrite/load route as the other node tools (rewrites the
    node's Coordinates line), not LWNodeEditorFuncs.setXY. Close and
    reopen the Node Editor to see the change."""
    return json.dumps(_query("move_node", "%s|%s|%d|%d" % (surface, node, x, y)))


@mcp.tool()
def lw_get_node_values(node: str, surface: str = "CONNECTOR") -> str:
    """Read every stored input value of a node - e.g. a Principled
    BSDF's Color, Roughness, Metallic - which lw_get_node_inputs can't
    (LWNodeInputFuncs' evaluate calls only work during a render). Each
    input reports `name`, `format`, `type` and `value` (a list).

    Values are in LightWave's internal units: "Percent" is a fraction
    (Roughness 10% = 0.1), "Color" is 0-1 per channel (200/255 =
    0.784), "Distance" is in metres, "Float" is a plain number. `type`
    is "vparam" (one number), "vparam3" (three) or "int" (a whole
    number); "unsupported" means a shape this connector doesn't parse
    (none seen yet), with no value. Inputs that only take a wire (e.g.
    Principled's Projection, Normal, Bump) have no stored value and
    aren't listed.

    Each input also reports `enveloped`. An animated (enveloped) input's
    animation is NOT in the saved graph - confirmed live, Roughness
    keyed 10% -> 50% still showed its plain stored 0.1 there - so its
    `value` is only the static base value, which the envelope
    overrides. For those, `envelope` holds the real keys (frame, value,
    shape) from the surface's animation channels, the same data
    lw_get_node_channel reads.

    Works by saving the surface's graph as ASCII and parsing the node's
    block - read-only, nothing is loaded back."""
    return json.dumps(_query("get_node_values", "%s|%s" % (surface, node)))


@mcp.tool()
def lw_set_node_input(node: str, input_name: str, value: float | list[float],
                      surface: str = "CONNECTOR") -> str:
    """Set one input value on a node - e.g. a Principled BSDF's
    Roughness or Color. `node` is a node_name from lw_get_surface_nodes;
    `input_name` one listed by lw_get_node_values.

    `value` uses LightWave's internal units, exactly as
    lw_get_node_values reports them: one number for a "vparam" or "int"
    input (Percent as a fraction - 25% is 0.25; Distance in metres), and
    a list of three 0-1 numbers for a "vparam3" Color (e.g. [1, 0, 0]
    for red). The wrong count, or a fraction for an "int" input, is
    refused without changing anything.

    Same save/rewrite/load route as the other node tools: rewrites that
    input's value line in the saved graph, loads it back, then re-saves
    and reports `before`, the `value` LightWave actually holds, and
    `set`. Adds a `warning` when a wire feeds the input, since the wire
    then overrides the value. Refuses an animated (enveloped) input,
    listing its keys instead - its stored value is overridden by the
    envelope, so changing it would do nothing. Close and reopen an open
    Surface Editor to see the change."""
    return json.dumps(_query("set_node_input", "%s|%s|%s|%s"
                             % (surface, node, input_name, json.dumps(value))))


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
def lw_set_render_globals(threads: int = None, tile_size: int = None) -> str:
    """Set scene-wide render quality/performance settings (ROADMAP3.md
    item 3) - the biggest remaining "can trigger renders but can't
    configure them" gap this connector had. Wraps RenderThreads(threads)
    and RenderTileSize(tilesize), both already correctly taking real
    arguments in the stub.

    Confirmed live: `tile_size` directly updated Render Properties >
    Render > "Render Tile Size" (64 -> 32), no precondition. `threads`
    directly updated "Multithreading Limit" (e.g. 4 -> "4 Threads") AND
    correctly auto-unchecked "Automatic Multithreading" as a side
    effect, with no separate precondition command needed - a cleaner
    result than lw_set_camera's MotionBlur precondition."""
    lw = _layout()
    sent = []
    try:
        if threads is not None:
            lw.RenderThreads(threads)
            sent.append("RenderThreads")
        if tile_size is not None:
            lw.RenderTileSize(tile_size)
            sent.append("RenderTileSize")
        return json.dumps({"result": "set %s" % sent})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


_POLYGON_INTERSECTION = {"fastest": 0, "watertight": 1, "double_precision": 2}
# "On - GPU" is NoiseFilter 2, deliberately not offered: on a machine
# without a supported GPU, LightWave pops a modal "A supported GPU is not
# available for Noise Filtering" error that blocks Layout until someone
# clicks OK (confirmed live).
_NOISE_FILTER = {"off": 0, "cpu": 1}


@mcp.tool()
def lw_get_color_space() -> str:
    """Read LightWave's colour space settings: each slot's current
    colour space by name (`slots`: viewer, surface_color, light_color,
    palette/8bit/float/alpha files, output, output_alpha, output_vpr,
    output_vpr_alpha, output_buffer), the four checkboxes (`flags`:
    auto_sense, correct_opengl, affect_picker, 8bit_to_float), and the
    names available to choose from (`available`: rgb, alpha - the alpha
    slots only take Linear/sRGB/rec709). Uses LWColorSpaceFuncs'
    read-only calls; changes nothing.

    Confirmed live against the CS tab. `output_buffer` (Default Buffer)
    always reads null even though the tab shows a value - LightWave's
    reader returns nothing for it - so a Default Buffer change can't be
    confirmed here. `output_vpr`/`output_vpr_alpha` read null too and
    aren't on the tab at all. These are preferences, not scene
    settings, and in testing they did NOT survive a Layout restart."""
    return json.dumps(_query("get_color_space"))


# (parameter, command, lw_get_color_space slot key, layer of names it takes)
_COLOR_SPACE_SETTINGS = (
    ("display", "ColorSpaceViewer", "viewer", "rgb"),
    ("picked_colors", "ColorSpaceSurfaceColor", "surface_color", "rgb"),
    ("light_color", "ColorSpaceLightColor", "light_color", "rgb"),
    ("palette_files", "ColorSpacePaletteFiles", "palette_files", "rgb"),
    ("eight_bit_files", "ColorSpace8BitFiles", "8bit_files", "rgb"),
    ("float_files", "ColorSpaceFloatFiles", "float_files", "rgb"),
    ("alpha", "ColorSpaceAlpha", "alpha_files", "alpha"),
    ("final_render", "ColorSpaceOutput", "output", "rgb"),
    ("buffer", "ColorSpaceOutputBuffer", "output_buffer", "rgb"),
    ("embedded_alpha", "ColorSpaceOutputAlpha", "output_alpha", "alpha"),
)
_COLOR_SPACE_FLAG_COMMANDS = (
    ("auto_sense", "ColorSpaceAutoSense"),
    ("correct_opengl", "ColorSpaceCorrectOpenGL"),
    ("affect_picker", "ColorSpaceAffectPicker"),
    ("convert_8bit_to_float", "ColorSpace8BitToFloat"),
)


@mcp.tool()
def lw_set_color_space(display: str = None, picked_colors: str = None,
                       light_color: str = None, palette_files: str = None,
                       eight_bit_files: str = None, float_files: str = None,
                       alpha: str = None, final_render: str = None, buffer: str = None,
                       embedded_alpha: str = None, auto_sense: bool = None,
                       correct_opengl: bool = None, affect_picker: bool = None,
                       convert_8bit_to_float: bool = None) -> str:
    """Set LightWave's colour spaces (Edit > General Options > CS tab).
    Any parameter left as None is not touched. Parameters follow the
    tab's labels: "Convert Color Space to Linear" - `picked_colors`,
    `light_color`, `palette_files`, `eight_bit_files`, `float_files`,
    `alpha`; "Apply Color Space" - `display`, `final_render` (the
    rendered output), `buffer`, `embedded_alpha`; and the four
    checkboxes `auto_sense`, `correct_opengl`, `affect_picker`,
    `convert_8bit_to_float`.

    A colour space is given by name - the built-ins are "Linear",
    "sRGB", "rec709", "Cineon" and "ciexyz"; lw_get_color_space lists
    what this install has (`available`). Names are matched without
    regard to case against that live list BEFORE anything is sent, and
    an unknown name is refused with the valid choices - LightWave's own
    reaction to a bad name is untested and could be a modal dialog.

    Command names are from Cmd History while each control was changed
    by hand; they don't all match their labels: Picked Colors is
    ColorSpaceSurfaceColor, Display is ColorSpaceViewer, Default Final
    Render is ColorSpaceOutput, Default Buffer is
    ColorSpaceOutputBuffer, Embedded Alpha Channel is
    ColorSpaceOutputAlpha. Every one takes its value as an argument
    (checkboxes 1/0, not toggles) although the stubs declare none, so
    they're sent raw. After sending, reads everything back and returns
    it as `state` (except Default Buffer, which can't be read - see
    lw_get_color_space). Confirmed live: Display and Final Render set
    to sRGB (from "srgb" - case-insensitive) and Auto Sense on, all
    matching the CS tab and Cmd History, then restored; an unknown name
    was refused with nothing sent."""
    values = {"display": display, "picked_colors": picked_colors,
              "light_color": light_color, "palette_files": palette_files,
              "eight_bit_files": eight_bit_files, "float_files": float_files,
              "alpha": alpha, "final_render": final_render, "buffer": buffer,
              "embedded_alpha": embedded_alpha}
    flags = {"auto_sense": auto_sense, "correct_opengl": correct_opengl,
             "affect_picker": affect_picker, "convert_8bit_to_float": convert_8bit_to_float}
    commands = []
    if any(v is not None for v in values.values()):
        current = _query("get_color_space").get("result")
        if not isinstance(current, dict) or not isinstance(current.get("available"), dict):
            return json.dumps({"error": "couldn't read the available colour spaces, "
                                        "so nothing was sent", "detail": current})
        for param, command, _slot, layer in _COLOR_SPACE_SETTINGS:
            value = values[param]
            if value is None:
                continue
            names = current["available"].get(layer)
            if not isinstance(names, list):
                return json.dumps({"error": "couldn't read the %s colour space list" % layer})
            match = [n for n in names if n.lower() == value.strip().lower()]
            if not match:
                return json.dumps({"error": "%s: unknown colour space %r (available: %s); "
                                            "nothing was sent" % (param, value, names)})
            if " " in match[0]:
                return json.dumps({"error": "%s: %r contains a space, which this "
                                            "connector can't send safely" % (param, match[0])})
            commands.append((command, match[0]))
    for param, command in _COLOR_SPACE_FLAG_COMMANDS:
        if flags[param] is not None:
            commands.append((command, int(flags[param])))
    lw = _layout()
    sent = []
    try:
        for command, value in commands:
            lw._send_command(command, [value])
            sent.append("%s %s" % (command, value))
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc), "sent": sent})
    time.sleep(0.3)
    state = _query("get_color_space")
    return json.dumps({"sent": sent, "state": state.get("result", state)})


@mcp.tool()
def lw_get_render_options() -> str:
    """Read the Render Properties > Render tab settings LightWave
    exposes: `raytrace_shadows`/`_reflection`/`_refraction` (plus
    `_transparency`/`_occlusion`), `ray_recursion_limit`,
    `transparency_/reflection_/refraction_recursion_limit`,
    `reflection_/refraction_/subsurface_samples`, and
    `indirect_bounce_count`, which is Diffuse Bounces (confirmed live).
    `ray_cutoff` is reported too but is NOT Ray Precision - it stayed
    0.01 when Ray Precision changed. Ray precision, polygon intersection
    mode, noise filter and despike can't be read back - LightWave
    doesn't expose them."""
    return json.dumps(_query("get_render_options"))


@mcp.tool()
def lw_set_render_options(raytrace_shadows: bool = None, raytrace_reflection: bool = None,
                          raytrace_refraction: bool = None, ray_recursion_limit: int = None,
                          transparency_recursion_limit: int = None,
                          reflection_recursion_limit: int = None,
                          refraction_recursion_limit: int = None, diffuse_bounces: int = None,
                          reflection_samples: int = None, refraction_samples: int = None,
                          subsurface_samples: int = None, ray_precision: float = None,
                          polygon_intersection: str = None, noise_filter: str = None,
                          despike: bool = None, despike_tolerance: float = None) -> str:
    """Set Render Properties > Render tab quality settings. Any
    parameter left as None is not touched. This install's renderer
    dropdown only offers VPR, so there is no engine to switch - these
    are the settings that trade speed for quality instead (raytracing,
    recursion/bounce limits, sample counts, noise filtering).

    `polygon_intersection` is "fastest", "watertight" (the default) or
    "double_precision"; `noise_filter` is "off" or "cpu". The GPU noise
    filter is deliberately not offered: on a machine without a supported
    GPU it pops a modal error that blocks Layout until someone clicks OK.

    Command names are from Cmd History while each control was changed by
    hand, and every one was confirmed live: the Raytrace checkboxes take
    an explicit 0/1 (not toggles); Polygon Intersection Mode logs as
    RenderAlgorithm (NOT a render engine choice) - Fastest 0, Watertight
    1, Double Precision 2; Noise Filter logs `NoiseFilter <n>` - Off 0,
    On-CPU 1 - and its stub takes no arguments, so every command here
    is sent raw.

    After sending, reads the tab back (lw_get_render_options) and
    returns it as `state` - the Command Port is one-way UDP, so trust
    that. Ray precision, polygon intersection, noise filter and despike
    aren't in it; check those in the UI."""
    for name, value, table in (("polygon_intersection", polygon_intersection, _POLYGON_INTERSECTION),
                               ("noise_filter", noise_filter, _NOISE_FILTER)):
        if value is not None and value not in table:
            return json.dumps({"error": "%s must be one of %s" % (name, sorted(table))})
    commands = []
    for value, command, convert in (
        (raytrace_shadows, "RayTraceShadows", int),
        (raytrace_reflection, "RayTraceReflection", int),
        (raytrace_refraction, "RayTraceRefraction", int),
        (ray_recursion_limit, "RayRecursionLimit", int),
        (transparency_recursion_limit, "TransparencyRecursionLimit", int),
        (reflection_recursion_limit, "ReflectionRecursionLimit", int),
        (refraction_recursion_limit, "RefractionRecursionLimit", int),
        (diffuse_bounces, "DiffuseBounces", int),
        (reflection_samples, "ReflectionSamples", int),
        (refraction_samples, "RefractionSamples", int),
        (subsurface_samples, "SubsurfaceScatteringSamples", int),
        (ray_precision, "RayPrecision", float),
        (despike, "EnableDespike", int),
        (despike_tolerance, "DespikeTolerance", float),
    ):
        if value is not None:
            commands.append((command, convert(value)))
    if polygon_intersection is not None:
        commands.append(("RenderAlgorithm", _POLYGON_INTERSECTION[polygon_intersection]))
    if noise_filter is not None:
        commands.append(("NoiseFilter", _NOISE_FILTER[noise_filter]))
    lw = _layout()
    sent = []
    try:
        for command, value in commands:
            lw._send_command(command, [value])
            sent.append("%s %s" % (command, value))
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc), "sent": sent})
    time.sleep(0.3)
    state = _query("get_render_options")
    return json.dumps({"sent": sent, "state": state.get("result", state)})


@mcp.tool()
def lw_toggle_global_illumination() -> str:
    """Flip the "Enable GI" checkbox (Render Properties > Global
    Illumination) (ROADMAP3.md item 3). Wraps EnableRadiosity0 -
    confirmed live to be a real argument-less TOGGLE (Cmd History
    logged it bare, repeatedly, after clicking the real checkbox
    on/off several times) - same limitation as every other confirmed
    toggle in this connector (lw_toggle_ik_flag, lw_toggle_object_
    visibility): no way to read current state back, so this flips
    rather than sets.

    A sibling command, EnableRadiosity1, was found in the same survey
    and definitively resolved this follow-up sweep: calling it live
    popped LightWave's own error dialog, "Unknown command:
    'EnableRadiosity1'" - proof, not a guess, that this command simply
    doesn't exist in LightWave 2019.1.5's command parser at all, despite
    being defined in the bundled lwcommandport stub (likely generated
    against a different LightWave version). Left permanently unwrapped -
    there is nothing real underneath it to wrap."""
    try:
        _layout().EnableRadiosity0()
        return json.dumps({"result": "toggled EnableRadiosity0 (Enable GI)"})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_gi_interpolated(enabled: int) -> str:
    """Set whether Global Illumination uses Interpolated mode (Render
    Properties > Global Illumination > "Interpolated" checkbox, under
    Monte Carlo) (ROADMAP3.md item 3). Wraps RadiosityInterpolation
    (enabled) - confirmed correctly taking a real argument in the stub
    already. Confirmed live: RadiosityInterpolation(1) correctly checked
    the "Interpolated" checkbox. `enabled=0` was not independently
    confirmed live this session, only inferred from the command's own
    name and argument-count requirement - treat with slightly less
    confidence than the confirmed `1` case.

    This gates lw_set_gi_radiosity_tolerance's precondition, but not
    completely - see that tool's docstring for a real, still-open
    limitation found while testing this."""
    try:
        _layout().RadiosityInterpolation(enabled)
        return json.dumps({"result": "sent RadiosityInterpolation %s" % enabled})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_gi_radiosity_tolerance(degrees: float) -> str:
    """Set Global Illumination's Angular Tolerance (Render Properties >
    Global Illumination > Interpolated > "Angular Tolerance")
    (ROADMAP3.md item 3). Wraps ObjGIRadiosityTolerance(degrees),
    already correctly taking a real argument in the stub.

    Real, unresolved precondition found live: LightWave pops "This
    option only applies when Global Illumination Mode is set to Monte
    Carlo Interpolated" - and this persisted even after enabling GI
    (lw_toggle_global_illumination) AND setting Interpolated mode
    (lw_set_gi_interpolated(1)), both confirmed to have taken visible
    effect in the UI beforehand. The "Type" dropdown this install
    offers only has one option, "Monte Carlo" - no distinct "Monte
    Carlo Interpolated" mode was ever reachable to select, despite the
    error message referencing it by that exact name. Shipped anyway,
    following the same precedent as lw_set_camera's MotionBlur-gated
    shutter properties: the write command itself is legitimate and its
    argument is confirmed correct, it just couldn't be exercised to a
    visible effect in this install this session. Also worth noting: two
    calls to this command were silently dropped somewhere between this
    connector and Layout during testing (never appeared in Cmd History
    at all, not even as the precondition error) - the one-way Command
    Port has no delivery guarantee, so an apparently-silent call here
    isn't necessarily this command's own fault."""
    try:
        _layout().ObjGIRadiosityTolerance(degrees)
        return json.dumps({"result": "sent ObjGIRadiosityTolerance %s" % degrees})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_backdrop(color: list = None, zenith_color: list = None, sky_color: list = None,
                     ground_color: list = None, nadir_color: list = None) -> str:
    """Set the scene's backdrop/environment colors (ROADMAP3.md item 4,
    Effects > Backdrop panel). `color` is the flat Backdrop Color
    (visible when Gradient Backdrop is off); `zenith_color`/`sky_color`/
    `ground_color`/`nadir_color` are the four gradient stops (visible
    when it's on - see lw_toggle_gradient_backdrop). Each is [r, g, b],
    0.0-1.0.

    All five confirmed live with zero precondition: `BackdropColor(1, 0,
    0)` showed red; `SkyColor(0, 1, 0)` showed green; with Gradient
    Backdrop on, `ZenithColor(1, 1, 0)`/`GroundColor(1, 0, 1)`/
    `NadirColor(0, 1, 1)` sent together correctly showed yellow/magenta/
    cyan respectively, exactly matching."""
    lw = _layout()
    sent = []
    try:
        if color is not None:
            lw.BackdropColor(*color)
            sent.append("BackdropColor")
        if zenith_color is not None:
            lw.ZenithColor(*zenith_color)
            sent.append("ZenithColor")
        if sky_color is not None:
            lw.SkyColor(*sky_color)
            sent.append("SkyColor")
        if ground_color is not None:
            lw.GroundColor(*ground_color)
            sent.append("GroundColor")
        if nadir_color is not None:
            lw.NadirColor(*nadir_color)
            sent.append("NadirColor")
        return json.dumps({"result": "set %s" % sent})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_toggle_gradient_backdrop() -> str:
    """Flip the "Gradient Backdrop" checkbox (Effects > Backdrop)
    (ROADMAP3.md item 4). Wraps GradientBackdrop - confirmed live to be
    a real argument-less TOGGLE (Cmd History logged it bare after
    clicking the real checkbox on and off). No way to read current
    state back, so this flips rather than sets - same limitation as
    every other confirmed toggle in this connector.

    Also found live: `Backdrop()` (no relation to this toggle despite
    the similar name) is NOT a setting at all - opening the Effects >
    Backdrop panel itself logged a bare `Backdrop` command, meaning it's
    a panel-opener like `SurfaceEditor`/`ItemProperties`, not wrapped
    here."""
    try:
        _layout().GradientBackdrop()
        return json.dumps({"result": "toggled GradientBackdrop"})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_toggle_volumetrics() -> str:
    """Flip the "Enable Volumetrics" checkbox (Render Properties >
    Volumetrics) (ROADMAP3.md item 4). Wraps EnableVolumetrics -
    confirmed live to be a real argument-less TOGGLE. No way to read
    current state back, so this flips rather than sets.

    Real precondition confirmed live for the whole Volumetrics panel,
    including Fog (lw_set_fog): every field under this checkbox
    (Fog Type, Fog Color, etc.) reads/shows as disabled/default until
    this is checked - sending Fog settings before checking this has no
    visible effect, confirmed live by sending FogType/FogColor before
    enabling Volumetrics and seeing no change, then resending the exact
    same values after enabling it and seeing FogType correctly update
    to "Linear". Call this once before lw_set_fog if Volumetrics isn't
    already enabled."""
    try:
        _layout().EnableVolumetrics()
        return json.dumps({"result": "toggled EnableVolumetrics"})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_toggle_volumetric_lights() -> str:
    """Flip the scene-wide "Enable Volumetric Lights" toggle
    (ROADMAP3.md item 4/6). Wraps EnableVolumetricLights - confirmed
    live to be a real argument-less TOGGLE via the definitive test
    (passing an explicit argument raises a clean Python arg-count error
    from the stub: "takes 1 positional argument but 2 were given").

    Worth noting as a methodology finding: Cmd History displayed this
    particular toggle's calls as "EnableVolumetricLights 0"/"...1"
    alternating with each click, even though no argument was ever
    actually sent - LightWave apparently echoes some toggle commands'
    resulting boolean state into Cmd History for readability, purely as
    a display convention unrelated to what's on the wire. Do not treat a
    numeric suffix in Cmd History alone as proof a command takes an
    argument - the arg-count test above is the reliable signal, and it
    confirms this one doesn't. No way to read current state back, so
    this flips rather than sets. Distinct from lw_toggle_volumetrics'
    scene Volumetrics/Fog panel and from lw_set_light's
    volumetric_samples/volumetric_intensity, which are per-light."""
    try:
        _layout().EnableVolumetricLights()
        return json.dumps({"result": "toggled EnableVolumetricLights"})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_get_fog() -> str:
    """Read the scene fog (Render Properties > Volumetrics) via
    LWFogInfo: `type` and `type_name` (0 Off, 1 Linear, 2 Nonlinear 1,
    3 Nonlinear 2, 4 Realistic - lwrender.h's LWFOG_* values),
    `min_distance`, `max_distance`, `min_amount`, `max_amount` and
    `color` ([r, g, b], 0-1), evaluated at the live playhead.

    Confirmed live to follow the Volumetrics panel: setting Fog Type to
    Linear by hand read back as type 1. Read-only - there is no working
    way to set fog from here: the Fog* commands are accepted but have no
    effect in LightWave 2019, and a hand change in the panel logs no
    command at all."""
    return json.dumps(_query("get_fog"))


# DELIBERATELY NOT REGISTERED as an MCP tool: in LightWave 2019 the Fog*
# commands are accepted and logged in Cmd History but change nothing -
# confirmed live against lw_get_fog, both with and without "Use Legacy
# Volumetrics". See PLAN.md "Fog commands have no effect". Kept for
# reference; use lw_get_fog to read the fog and the UI to set it.
def lw_set_fog(fog_type: int = None, min_distance: float = None, max_distance: float = None,
               min_amount: float = None, max_amount: float = None, color: list = None) -> str:
    """Set scene fog (Render Properties > Volumetrics > Fog Type/Min-Max
    Distance/Min-Max Amount/Fog Color) (ROADMAP3.md item 4). `color` is
    [r, g, b], 0.0-1.0. Requires "Enable Volumetrics" checked first (see
    lw_toggle_volumetrics) - confirmed live that Fog settings sent
    before enabling it have no visible effect, even though they're
    accepted without error and logged in Cmd History.

    `fog_type` confirmed live and its enum mapping confirmed by
    selecting the matching UI dropdown entry after sending it:
    `fog_type=1` correctly showed "Linear" in the dropdown (0 is
    presumably "Off", matching the dropdown's default/unset state, but
    that specific value was never explicitly sent and confirmed - the
    dropdown also lists "Nonlinear 1"/"Nonlinear 2"/"Realistic", whose
    numeric values were not tested). `min_distance`/`max_distance`/
    `min_amount`/`max_amount` (FogMinDistance/FogMaxDistance/
    FogMinAmount/FogMaxAmount) were NOT independently tested live -
    same confirmed-`*args` signature shape as every other command in
    this survey, shipped by pattern-confidence, not verified. After
    sending, the fog is read back (lw_get_fog) and returned as `state`,
    so each of these can now be checked against what LightWave holds.

    `color` (FogColor) has a real, unresolved gap: sent successfully
    (logged cleanly in Cmd History, no error) both before AND after
    enabling Volumetrics, but the Fog Color swatch never visibly updated
    from its default white (255/255/255) in either case, unlike
    BackdropColor/SkyColor/FogType, which all updated correctly under
    the same connector. Left shipped rather than removed, since the
    command is accepted without error and the failure mode is
    ambiguous (could be a UI redraw lag rather than a real no-op,
    similar to FogType's own initial-looking staleness that turned out
    to just need a UI interaction to redraw) - but treat this
    specifically as unconfirmed, not working, until verified further."""
    lw = _layout()
    sent = []
    try:
        if fog_type is not None:
            lw.FogType(fog_type)
            sent.append("FogType")
        if min_distance is not None:
            lw.FogMinDistance(min_distance)
            sent.append("FogMinDistance")
        if max_distance is not None:
            lw.FogMaxDistance(max_distance)
            sent.append("FogMaxDistance")
        if min_amount is not None:
            lw.FogMinAmount(min_amount)
            sent.append("FogMinAmount")
        if max_amount is not None:
            lw.FogMaxAmount(max_amount)
            sent.append("FogMaxAmount")
        if color is not None:
            lw.FogColor(*color)
            sent.append("FogColor")
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc), "sent": sent})
    time.sleep(0.3)
    state = _query("get_fog")
    return json.dumps({"sent": sent, "state": state.get("result", state)})


@mcp.tool()
def lw_set_antialiasing(camera: str = "Camera", min_samples: int = None,
                        max_samples: int = None, adaptive_sampling: bool = None,
                        adaptive_threshold: float = None,
                        filter_radius: float = None) -> str:
    """Set a camera's antialiasing (Camera Properties' sampling block):
    `min_samples`/`max_samples` (Minimum/Maximum Samples),
    `adaptive_sampling` (on/off), `adaptive_threshold` (Threshold) and
    `filter_radius` (Filter Radius). Any parameter left as None is not
    touched. Higher samples and a lower threshold mean a cleaner, slower
    render - e.g. a draft pass at 1/4 samples, a final at 8/64. With
    adaptive sampling OFF, LightWave renders every pixel at
    `min_samples` - confirmed live, the scene's effective maximum
    dropped to the minimum - so `max_samples` and `adaptive_threshold`
    only matter with it on.

    Command names are from Cmd History while the controls were changed
    by hand, NOT the obvious stub names: Minimum/Maximum Samples log as
    MinAntialiasing/MaxAntialiasing (the MinimumSamples/MaximumSamples
    stubs are something else), Filter Radius logs as Oversampling, and
    the Adaptive Sampling checkbox logs a bare AdaptiveSampling - a
    toggle. So `adaptive_sampling` reads the current state first and
    toggles only if it differs. The camera is selected by numeric ID,
    never by name (see lw_set_camera).

    The Command Port is one-way UDP, so after sending, this reads every
    value back (lw_get_antialiasing) and returns it as `state` -
    trust that, not just the "sent" list. The reconstruction filter
    (Render Properties > Buffers) is not settable here: changing it by
    hand logs no command at all."""
    camera_id, id_resp = _resolve_item_id(camera)
    if not camera_id:
        return json.dumps({"error": "could not resolve camera: %s" % camera, "detail": id_resp})
    lw = _layout()
    sent = []
    try:
        lw.SelectItem(camera_id)
        if min_samples is not None:
            lw.MinAntialiasing(int(min_samples))
            sent.append("MinAntialiasing %d" % int(min_samples))
        if max_samples is not None:
            lw.MaxAntialiasing(int(max_samples))
            sent.append("MaxAntialiasing %d" % int(max_samples))
        if adaptive_sampling is not None:
            current = _query("get_antialiasing", camera).get("result", {}).get("adaptive_sampling")
            if current is None:
                return json.dumps({"error": "couldn't read adaptive_sampling state, so "
                                            "didn't toggle it", "sent": sent})
            if bool(current) != bool(adaptive_sampling):
                lw.AdaptiveSampling()
                sent.append("AdaptiveSampling")
        if adaptive_threshold is not None:
            lw.AdaptiveThreshold(float(adaptive_threshold))
            sent.append("AdaptiveThreshold %s" % adaptive_threshold)
        if filter_radius is not None:
            lw.Oversampling(float(filter_radius))
            sent.append("Oversampling %s" % filter_radius)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc), "sent": sent})
    time.sleep(0.3)
    state = _query("get_antialiasing", camera)
    return json.dumps({"camera": camera, "id": camera_id, "sent": sent,
                       "state": state.get("result", state)})


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
                  falloff_type: int = None, cone_angle: float = None,
                  volumetric_samples: int = None, volumetric_intensity: float = None) -> str:
    """Set light properties - ROADMAP2.md item 5, the write-side
    counterpart to lw_get_light_info. Wraps LightIntensity/LightColor
    (color is [r, g, b], each 0.0-1.0)/LightFalloffType/LightConeAngle,
    following lw_set_camera's bundled-optional-params shape. Same
    numeric-ID SelectItem fix as lw_set_camera/lw_set_target. Confirmed
    live: intensity and color take effect immediately.

    `volumetric_samples`/`volumetric_intensity` (ROADMAP3.md item 4,
    Light Properties > Basic > "Volumetric Samples"/"Volumetric
    Intensity", gated by "Affect Volumetrics") confirmed live with zero
    precondition beyond that checkbox already being on:
    `volumetric_samples=8` showed "8"; `volumetric_intensity=0.5` showed
    "50.0%", both exact matches.

    `falloff_type` is the Intensity Falloff dropdown: 0 = Off, 1 = Inv
    Distance^2 - the only two options in LightWave 2019 (Cmd History logs
    LightFalloffType 0/1); anything else is refused. Confirmed live, and
    read back correctly by lw_get_light_info - but close Light Properties before changing falloff. If that panel is open
    when the command arrives, the light does change, but the open panel
    gets out of step - it stops responding and can't be closed normally
    (reopening it from the Scene Editor shows the real value) - and
    lw_get_light_info keeps reporting the old value. Confirmed live.
    It only applies to Point/Spot lights, confirmed via LightWave's own
    error dialog ("This option does not apply to the current light
    type") when tried on a Distant light. cone_angle only matters for spot/cone-type lights - not
    independently visually confirmed the way falloff_type was.

    Deliberately does NOT cover LightVisibleToCamera/LightCastsShadows.
    Both are confirmed-live, real argument-less TOGGLES (Cmd History
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
    if falloff_type is not None and falloff_type not in (0, 1):
        return json.dumps({"error": "falloff_type must be 0 (Off) or 1 (Inv Distance^2)"})
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
        if volumetric_samples is not None:
            lw.LightVolumetricSamples(volumetric_samples)
            sent.append("LightVolumetricSamples")
        if volumetric_intensity is not None:
            lw.LightVolumetricIntensity(volumetric_intensity)
            sent.append("LightVolumetricIntensity")
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

    Both are confirmed live to be real argument-less TOGGLES, same
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
def lw_toggle_object_visibility(item: str, flag: str) -> str:
    """Flip a per-object render-visibility flag (ROADMAP3.md item 5).
    flag must be one of "unseen_by_rays", "unseen_by_camera",
    "unseen_by_radiosity", "unaffected_by_fog".

    All four confirmed live to be real argument-less TOGGLES, same
    shape and same finding as lw_toggle_ik_flag's FullTimeIK/
    UnaffectedByIK: Cmd History showed each command bare, no argument
    following, after clicking every one of the four real "Object
    Properties > Render" buttons on a live object. There is no way to
    read any of these flags' current state back, so this FLIPS whatever
    it currently is - call it once, then check Object Properties (or
    call it again to flip back) if the direction matters.

    Deliberately different from ROADMAP2.md item 1's light/object
    illumination linking (lw_include_light/lw_exclude_light etc., which
    control which objects a light lights) - these four are about
    whether the object is visible to the camera, reflection/refraction
    rays, radiosity calculations, or fog at all, a distinct
    render-visibility axis found by surveying the command list, not by
    extending the light-linking work.

    Deliberately does NOT include "unseen_by_alpha_channel" - that
    command turned out NOT to be a boolean visibility flag at all (see
    lw_set_alpha_channel_mode) despite matching this exact bare-call
    shape in the stub before it was fixed."""
    item_id, id_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": id_resp})
    command = {
        "unseen_by_rays": "UnseenByRays",
        "unseen_by_camera": "UnseenByCamera",
        "unseen_by_radiosity": "UnseenByRadiosity",
        "unaffected_by_fog": "UnaffectedByFog",
    }.get(flag)
    if not command:
        return json.dumps({"error": "flag must be one of 'unseen_by_rays', 'unseen_by_camera', "
                                     "'unseen_by_radiosity', 'unaffected_by_fog', got %r" % flag})
    lw = _layout()
    try:
        lw.SelectItem(item_id)
        getattr(lw, command)()
        return json.dumps({"result": "toggled %s on %s (id %s)" % (command, item, item_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_alpha_channel_mode(item: str, mode: int) -> str:
    """Set an object's Alpha Channel mode (ROADMAP3.md item 5). Wraps
    UnseenByAlphaChannel(mode) - a real, confirmed bug found while
    investigating this: the native command takes an argument
    (confirmed live via Cmd History: "UnseenByAlphaChannel 1"), but the
    bundled lwcommandport stub had it wrapped with no way to pass one at
    all, the same class of bug as Ring()/SetRenderDisplay()/MotionBlur()
    from earlier roadmaps - fixed here.

    Despite its name suggesting a boolean "unseen by alpha channel"
    toggle (and matching the exact bare-call shape lw_toggle_object_
    visibility's four real toggles use), this is actually the Object
    Properties "Alpha Channel" dropdown's underlying command - an enum,
    not a boolean. Only two values confirmed live via that dropdown in
    this LightWave 2019.1.5 install: 0 = "Use Surface Settings" (the
    default), 1 = "Constant Value" (pairs with the separate AlphaValue
    command/field). Other LightWave versions' docs mention additional
    options (e.g. Shadow Density) that were NOT independently confirmed
    in this dropdown - pass an unconfirmed value at your own risk, this
    tool does not validate the range."""
    item_id, id_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": id_resp})
    lw = _layout()
    try:
        lw.SelectItem(item_id)
        lw.UnseenByAlphaChannel(mode)
        return json.dumps({"result": "set UnseenByAlphaChannel(%s) on %s (id %s)" % (mode, item, item_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_bone(item: str, strength: float = None, rest_length: float = None,
                 rest_position: list = None, rest_rotation: list = None,
                 weight_map_name: str = None, falloff_type: int = None,
                 min_range: float = None, max_range: float = None) -> str:
    """Set a bone's rigging properties (ROADMAP3.md item 6, Modify >
    Properties > "Bones for <object>" panel, opened while a bone is the
    current item). `item` must be a bone's numeric ID (e.g. "40000000")
    from lw_get_hierarchy's bone `id` field - `_resolve_item_id` passes
    a purely numeric string straight through (see ROADMAP2.md item 7),
    the same mechanism this whole family of bone tools relies on since
    bones have no name lw_get_item_id can resolve.

    `falloff_type` is object-wide (the "Falloff Type" dropdown at the
    TOP of the Bones panel, above "Current Bone" - it applies to every
    bone on the object, not just the selected one), everything else is
    per-bone. `rest_position`/`rest_rotation` are [x,y,z]/[h,p,b]
    triples.

    Confirmed live on a real bone (Bone1): `strength=0.5` showed
    "Strength: 50.0%"; `rest_length=2` showed "Rest Length: 2m";
    `falloff_type=2` changed the object-wide dropdown from "Inverse
    Distance ^16" to "Inverse Distance ^2" (exact enum values for other
    dropdown entries not confirmed). `min_range=0.5`/`max_range=3`
    correctly showed "Min: 500mm"/"Max: 3m" once `lw_toggle_bone_flag`'s
    "limited_range" was enabled first (these fields are grayed out
    otherwise, matching the DOF/Motion-Blur precondition shape from
    earlier roadmaps). `rest_position=[1,2,3]`/`rest_rotation=[10,20,30]`
    confirmed live via a real UI discovery: clicking the "Rest Position"/
    "Rest Rotation" buttons (they look like plain buttons, not value
    fields) opens a "Set Bone Rest Position/Rotation" requester
    pre-populated with the already-written value - X:1m/Y:2m/Z:3m and
    Heading:10/Pitch:20/Bank:30 respectively, both exact matches.
    `weight_map_name` sent cleanly (no error, logged correctly) but
    couldn't be visually confirmed - this test rig's bones live on a
    plain Null with no real mesh/vmap data, so there was no actual
    weight map for the name to match; treat this as likely-correct-by-
    signature rather than fully confirmed."""
    item_id, id_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": id_resp})
    lw = _layout()
    sent = []
    try:
        lw.SelectItem(item_id)
        if strength is not None:
            lw.BoneStrength(strength)
            sent.append("BoneStrength")
        if rest_length is not None:
            lw.BoneRestLength(rest_length)
            sent.append("BoneRestLength")
        if rest_position is not None:
            lw.BoneRestPosition(*rest_position)
            sent.append("BoneRestPosition")
        if rest_rotation is not None:
            lw.BoneRestRotation(*rest_rotation)
            sent.append("BoneRestRotation")
        if weight_map_name is not None:
            lw.BoneWeightMapName(weight_map_name)
            sent.append("BoneWeightMapName")
        if falloff_type is not None:
            lw.BoneFalloffType(falloff_type)
            sent.append("BoneFalloffType")
        if min_range is not None:
            lw.BoneMinRange(min_range)
            sent.append("BoneMinRange")
        if max_range is not None:
            lw.BoneMaxRange(max_range)
            sent.append("BoneMaxRange")
        return json.dumps({"result": "set %s on %s (id %s)" % (sent, item, item_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_toggle_bone_flag(item: str, flag: str) -> str:
    """Flip a bone's argument-less toggle flag (ROADMAP3.md item 6).
    `flag` is `"active"`, `"limited_range"`, `"weight_map_only"`,
    `"strength_multiply"`, `"joint_comp"`, `"joint_comp_parent"`,
    `"muscle_flex"`, `"muscle_flex_parent"`, `"bulge"`, `"bulge_parent"`,
    or `"twist"`. `item` must be a bone's numeric ID (see lw_set_bone's
    docstring for why).

    The first four confirmed live to be real argument-less TOGGLES (a
    definitive test, not just a UI guess: passing an explicit argument
    to any of them raises a clean Python arg-count error from the stub
    itself, e.g. "takes 1 positional argument but 2 were given" -
    proving the real command underneath takes none). No way to
    read current state back for any of them, so this flips rather than
    sets. `BoneActive` (Bone Active checkbox) defaulted to unchecked on
    a freshly-created bone in this test rig - a bone can exist and be
    parented into a chain while still "inactive". `BoneLimitedRange`
    gates the "Limited Range" Min/Max fields lw_set_bone's `min_range`/
    `max_range` write to - confirmed live those fields are grayed out
    until this is checked. `BoneWeightMapOnly` has a real precondition,
    confirmed live via LightWave's own error dialog: "This option only
    applies when using a weight map" - call after lw_set_bone's
    `weight_map_name` has assigned a real map. `BoneStrengthMultiply`
    maps to the "Multiply Strength by Rest Length" checkbox - confirmed
    live via a later full-panel screenshot showing it checked after
    this toggle was flipped, resolving what an earlier pass had left as
    an unpinned candidate.

    The remaining seven are the muscle/joint-compensation family's own
    enable checkboxes (see lw_set_bone_deform's docstring for the
    matching amount setters). All confirmed live via the Bones panel's
    "Bone Displacement"/"Parent Displacement" section: `joint_comp`
    ("Joint Compensation") and `bulge`/`bulge_parent` ("Muscle
    Bulge"/"Parental Muscle Bulge") are each independent
    checkboxes - toggling one leaves the other's checked state alone,
    confirmed by toggling only `joint_comp` and seeing only that row
    checked. `muscle_flex` (`BoneMuscleFlex`) is NOT independent of its
    parent counterpart the same way - confirmed live that toggling only
    `muscle_flex` checked BOTH "Muscle Flexing" AND "Parental Muscle
    Flexing" simultaneously, unlike the joint-comp/bulge pairs;
    `muscle_flex_parent` (`BoneMuscleFlexParent`) was not independently
    re-tested given this, and may be redundant with `muscle_flex` or
    control something else not covered by this session's screenshots.
    `twist` (`BoneTwist`) has a real precondition, confirmed live via
    LightWave's own error dialog: "This option does not apply to the
    current bone type" - consistent with its "Twist" row appearing
    grayed out for this test rig's Z-axis bones; a different Bone Type
    may be required."""
    item_id, id_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": id_resp})
    command = {
        "active": "BoneActive",
        "limited_range": "BoneLimitedRange",
        "weight_map_only": "BoneWeightMapOnly",
        "strength_multiply": "BoneStrengthMultiply",
        "joint_comp": "BoneJointComp",
        "joint_comp_parent": "BoneJointCompParent",
        "muscle_flex": "BoneMuscleFlex",
        "muscle_flex_parent": "BoneMuscleFlexParent",
        "bulge": "BoneBulge",
        "bulge_parent": "BoneBulgeParent",
        "twist": "BoneTwist",
    }.get(flag)
    if not command:
        return json.dumps({"error": "flag must be one of 'active', 'limited_range', "
                                     "'weight_map_only', 'strength_multiply', 'joint_comp', "
                                     "'joint_comp_parent', 'muscle_flex', 'muscle_flex_parent', "
                                     "'bulge', 'bulge_parent', 'twist', got %r" % flag})
    lw = _layout()
    try:
        lw.SelectItem(item_id)
        getattr(lw, command)()
        return json.dumps({"result": "toggled %s on %s (id %s)" % (command, item, item_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_bone_deform(item: str, joint_comp: float = None, joint_comp_parent: float = None,
                        muscle_flex: float = None, muscle_flex_parent: float = None,
                        bulge: float = None, bulge_parent: float = None,
                        twist: float = None) -> str:
    """Set the muscle/joint-compensation family's amount fields (Bones
    panel, "Bone Displacement"/"Parent Displacement" section) - the
    counterpart to lw_toggle_bone_flag's `joint_comp`/`joint_comp_parent`/
    `muscle_flex`/`muscle_flex_parent`/`bulge`/`bulge_parent`/`twist`
    enable checkboxes, which gate whether each of these has any visible
    effect. `item` must be a bone's numeric ID (see lw_set_bone's
    docstring for why). All amounts are 0.0-1.0 (percent/100).

    `joint_comp`/`joint_comp_parent` are sent TOGETHER via the native
    BoneJointCompAmounts(self, parent) - it takes both at once, so
    passing only one sends 0.0 for the other; call again with both
    explicit values if you don't want to reset the omitted side.
    Confirmed live: `joint_comp=0.3, joint_comp_parent=0.6` showed
    "Joint Compensation: 30.0%"/"Joint Comp for Parent: 60.0%" exactly.
    `muscle_flex`/`muscle_flex_parent` work the same way via
    BoneMuscleFlexAmounts(self, parent) - confirmed live with
    `muscle_flex=0.4, muscle_flex_parent=0.7` showing "40.0%"/"70.0%".
    `bulge`/`bulge_parent`/`twist` are each independent single-argument
    setters (BoneBulgeAmount/BoneBulgeParentAmount/BoneTwistAmount) -
    confirmed live for bulge (`0.55`/`0.8` matched exactly); `twist` has
    a real precondition, LightWave's own error dialog "This option does
    not apply to the current bone type" (this test rig's bones are
    Z-axis type - a different Bone Type may be required, not
    independently confirmed working end to end)."""
    item_id, id_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": id_resp})
    lw = _layout()
    sent = []
    try:
        lw.SelectItem(item_id)
        if joint_comp is not None or joint_comp_parent is not None:
            lw.BoneJointCompAmounts(joint_comp or 0.0, joint_comp_parent or 0.0)
            sent.append("BoneJointCompAmounts")
        if muscle_flex is not None or muscle_flex_parent is not None:
            lw.BoneMuscleFlexAmounts(muscle_flex or 0.0, muscle_flex_parent or 0.0)
            sent.append("BoneMuscleFlexAmounts")
        if bulge is not None:
            lw.BoneBulgeAmount(bulge)
            sent.append("BoneBulgeAmount")
        if bulge_parent is not None:
            lw.BoneBulgeParentAmount(bulge_parent)
            sent.append("BoneBulgeParentAmount")
        if twist is not None:
            lw.BoneTwistAmount(twist)
            sent.append("BoneTwistAmount")
        return json.dumps({"result": "set %s on %s (id %s)" % (sent, item, item_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_morph(item: str, target: str = None, amount: float = None) -> str:
    """Set an object's Morph target/amount (ROADMAP3.md item 7, the
    classic object-to-object morph - assigns a whole other item's shape
    as a blend target, distinct from vmap-based Endomorphs on a single
    object). Wraps MorphTarget(itemid)/MorphAmount(morph), both already
    correctly taking real arguments in the stub. `target` is resolved to
    a numeric ID like `lw_set_goal`/`lw_set_parent` (this command family
    shares the same "wants a numeric ID, not a name" quirk).

    Real precondition confirmed live: `MorphAmount` alone pops "This
    option only applies when the current object has a morph target" -
    LightWave's own error dialog, not a stub bug. Set `target` first (or
    in the same call - `target` is applied before `amount` here) to
    satisfy it. Confirmed live end to end: sending `MorphTarget` then
    `MorphAmount(0.5)` no longer raised the error and both logged
    cleanly. No visible geometry change was possible to confirm further
    in this test scene, since the morph target used
    (`BoneTestObject`, a Null) has no real mesh to blend toward - a
    limitation of the test rig, not the command."""
    item_id, id_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": id_resp})
    lw = _layout()
    sent = []
    try:
        lw.SelectItem(item_id)
        if target is not None:
            target_id, target_resp = _resolve_item_id(target)
            if not target_id:
                return json.dumps({"error": "could not resolve target: %s" % target, "detail": target_resp})
            lw.MorphTarget(target_id)
            sent.append("MorphTarget")
        if amount is not None:
            lw.MorphAmount(amount)
            sent.append("MorphAmount")
        return json.dumps({"result": "set %s on %s (id %s)" % (sent, item, item_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_save_endomorph(item: str, name: str) -> str:
    """Bake `item`'s current deformed point positions into a new
    Endomorph vmap named `name`. Wraps the native SaveEndomorph(name)
    command - `item` is selected via SelectItem first, matching every
    other per-item command in this file.

    Real, confirmed precondition found via LightWave's own error
    dialog: "Null objects are automatically saved with the scene" -
    SaveEndomorph refuses Null objects outright; only a real mesh
    object can have an Endomorph baked onto it. This project's current
    test rigs (e.g. BoneTestObject) are Nulls, so the actual successful
    bake - a new named Endomorph appearing with correct deformed
    positions - is NOT independently confirmed end to end, only that
    the command exists, takes a name argument, and enforces this real
    precondition. Left for a future session with a real mesh object
    (loaded via lw_load_object) that has some actual point deformation
    (bones/Morph Mixer) applied to bake."""
    item_id, id_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": id_resp})
    lw = _layout()
    try:
        lw.SelectItem(item_id)
        lw.SaveEndomorph(name)
        return json.dumps({"result": "sent SaveEndomorph %s on %s (id %s)" % (name, item, item_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_toggle_use_morphed_positions() -> str:
    """Flip "Use Morphed Positions" - per LightWave's own (much later,
    2025-version) documentation, this lets bone deformation apply AFTER
    morphs instead of before, and is documented there as not supported
    with Limited Bones. Wraps the native UseMorphedPositions() command.

    Confirmed live to be a real argument-less TOGGLE via the
    definitive arg-count test (passing an explicit argument raises a
    clean Python "takes 1 positional argument but 2 were given" error
    from the stub). Its own checkbox could not be located as a visible
    UI element in LightWave 2019.1.5 (checked the full Bones panel,
    Motion Options, General Options, and Object Properties - none show
    it), BUT calling it live DID pop a real LightWave error dialog:
    "Use Morphed Positions not supported with the current bone mode." -
    this closely matches the 2025 documentation's "not supported with
    Limited Bones" claim, confirming the feature and its precondition
    are both real in 2019.1.5 too, just gated behind a bone mode this
    test rig's bones don't have and with no separate checkbox exposed
    in this build's UI (it may only appear once that mode is active).
    Shipped as a bare toggle with no way to read state back."""
    try:
        _layout().UseMorphedPositions()
        return json.dumps({"result": "toggled UseMorphedPositions"})
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
