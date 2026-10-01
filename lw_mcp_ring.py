"""
lw_mcp_ring.py

Read-path Master plug-in for the Claude <-> LightWave MCP connector, built
on the *real* mechanism for receiving Command Port traffic: LWComRing.

Why this replaces lw_mcp_master.py (LWEVNT_COMMAND approach): that was a
confirmed, empirically-tested dead end - event() never fired for Command
Port traffic no matter what. The correct mechanism, found in NewTek's own
bundled example (support/plugins/scripts/Python/Layout/Master/
command_port_test.py, shipped with every LightWave 2019.1.5 install), is:

  1. Hold an lwsdk.LWComRing() instance.
  2. In inst_acquire(), call self._comring.ringAttach(
       lwsdk.LW_PORT_COMMAND_PORT, self, self.ring_event)
  3. Command Port traffic arrives at the ring_event(client_data, port_data,
     event_code, event_data) callback, event_code 0.
  4. Decode the raw bytes with self._comring.decodeData(('s:256',),
     event_data) -> a 1-tuple containing the string.
  5. Messages are expected in the form "{Topic} rest of message" - this
     matches the Ring(topic, command) method already present in the
     bundled lwcommandport client library's CommandPort base class, which
     formats exactly that: "{%s} %s" % (topic, command).

So the external client calls lw.Ring("MCP", "ping") (or "get_scene_info"),
which sends "{MCP} ping" over the same UDP Command Port used for AddNull
etc. This plug-in listens for the "MCP" topic specifically and writes its
answer to _mcp_response.json, which server.py polls (unchanged protocol
from the old, non-working attempt - only the delivery mechanism changes).

SETUP (must be done every fresh Layout session, same as the Command Port
itself):
  1. Utilities > Plugins > Add Plugins > lw_mcp_ring.py (registers the
     class - unlike the old single-shot enable script, this ships a
     ServerRecord so it needs a second step below).
  2. Utilities > Master Plugins > "Add Layout or Scene Master" dropdown >
     select "LW MCP Ring" > make sure its "On" checkbox is ticked.
     (Confirmed in earlier testing: LWMAST_LAYOUT-flagged masters still
     need this explicit activation step - just loading via Add Plugins is
     not enough to get inst_acquire() called.)
"""
import json
import os
import re

import lwsdk

__lwver__ = "11"

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_response.json")
DEBUG_LOG_PATH = os.path.join(_HERE, "_mcp_ring_debug.log")
RENDER_STATUS_PATH = os.path.join(_HERE, "_mcp_render_status.json")

TOPIC = "MCP"
# ROADMAP2.md item 8: this was originally r"^\{(.+)\}\s*(.*)$" - a GREEDY
# (.+) matches from the first "{" all the way to the LAST "}" in the whole
# message, not the first one. Every command before this item happened to
# have no braces in its own payload, so this bug was invisible until
# set_surface's JSON-encoded arg (e.g. '{MCP} set_surface X|{"diffuse": 0.5}')
# introduced a second pair. Confirmed via a standalone regex test: the old
# pattern parsed topic as 'MCP} set_surface X|{"diffuse": 0.5' (garbage,
# != "MCP") and rest as "" - so `if topic != TOPIC: return` silently dropped
# the message before _handle_query ever ran. This was misdiagnosed the first
# time as LWSurfaceFuncs().setFlt() hanging forever (the debug log looked
# identical either way: the incoming message logs, then nothing) - setFlt()
# was never actually reached. Fixed with a non-greedy (.+?) so topic stops
# at the FIRST "}" instead of the last one.
_TOPIC_RE = re.compile(r"^\{(.+?)\}\s*(.*)$")


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


def _find_item(name):
    """Search all item types for a name. Returns the item ID or None."""
    ii = lwsdk.LWItemInfo()
    for item_type in (lwsdk.LWI_OBJECT, lwsdk.LWI_LIGHT, lwsdk.LWI_CAMERA):
        it = ii.first(item_type, lwsdk.LWITEM_NULL)
        while it != lwsdk.LWITEM_NULL:
            if ii.name(it) == name:
                return it
            it = ii.next(it)
    return None


def _vec_to_list(v):
    """Best-effort conversion of a PCore::Vector SWIG object to a plain
    list, since it isn't JSON-serializable directly. Confirmed live that
    LWLightInfo().color() returns this type."""
    try:
        return [v.x, v.y, v.z]
    except AttributeError:
        pass
    try:
        return list(v)
    except TypeError:
        pass
    return str(v)


def _get_selection():
    """Every item's name/type and whether it's currently selected.
    Confirmed live: LWItemInfo().selected(item) is the reliable signal -
    flags() & LWITEMF_SELECTED was tested and does NOT reflect actual
    selection state (returned the same value for every item regardless)."""
    ii = lwsdk.LWItemInfo()
    items = []
    for label, item_type in (
        ("OBJECT", lwsdk.LWI_OBJECT),
        ("LIGHT", lwsdk.LWI_LIGHT),
        ("CAMERA", lwsdk.LWI_CAMERA),
    ):
        it = ii.first(item_type, lwsdk.LWITEM_NULL)
        while it != lwsdk.LWITEM_NULL:
            items.append({
                "name": ii.name(it),
                "type": label,
                "selected": bool(ii.selected(it)),
            })
            it = ii.next(it)
    return {"items": items, "selected": [i["name"] for i in items if i["selected"]]}


def _current_time():
    """ROADMAP.md's long-standing "querying LightWave's live playhead
    from Python is unsolved" limitation - solved. lwsdk.LWTimeInfo() is
    a plain-attribute class in the same style as LWSceneInfo (already
    proven safe elsewhere in this file) - found via a widened
    introspection pass (_probe_time, kept below) after the original
    _introspect() never searched for time/frame-related keywords at
    all. `.time` is the live playhead position in seconds, exactly the
    unit every animatable call in this file already expects (they used
    to hardcode 0.0 here). Confirmed live: GoToFrame(30) via the write
    path followed by this returning the corresponding non-zero seconds
    value, and an item keyframed at frame 0/30 correctly reading back
    its frame-30 value here instead of the frame-0 default."""
    return lwsdk.LWTimeInfo().time


def _get_camera_info(name):
    """Confirmed live signatures: resolution(id) takes just the item ID;
    focalLength/fStop/fovAngles/zoomFactor are animatable channels and
    need a second (time) argument - now the real live playhead time via
    _current_time(), not a hardcoded 0.0 (see _current_time's
    docstring).

    shutterOpen/shutterEfficiency/rollingShutter added for ROADMAP2.md
    item 4 (lw_set_camera, the write-side counterpart) - needed a way
    to verify those writes actually took effect. Signatures not
    independently confirmed against NewTek docs like the fields above
    were; tried with the same (id, time) shape as the rest of this
    function, each wrapped separately so a wrong guess for one doesn't
    break the others or the whole query."""
    cam_id = _find_item(name)
    if cam_id is None:
        return {"error": "camera not found: %s" % name}
    ci = lwsdk.LWCameraInfo()
    t = _current_time()
    result = {
        "name": name,
        "resolution": list(ci.resolution(cam_id)),
        "focal_length_mm": ci.focalLength(cam_id, t),
        "f_stop": ci.fStop(cam_id, t),
        "fov_angles_h_v": list(ci.fovAngles(cam_id, t)),
        "zoom_factor": ci.zoomFactor(cam_id, t),
        "evaluated_at_time": t,
    }
    for key, getter in (
        ("shutter_open", ci.shutterOpen),
        ("shutter_efficiency", ci.shutterEfficiency),
        ("rolling_shutter", ci.rollingShutter),
    ):
        try:
            result[key] = getter(cam_id, t)
        except Exception as exc:  # noqa: BLE001
            result[key + "_error"] = str(exc)
    return result


def _get_light_info(name):
    """Same live-time fix as _get_camera_info.

    ROADMAP2.md item 5: falloff(light_id) is a known-stale read - it
    always reports the scene-default value regardless of what
    lw_set_light's falloff_type just wrote. Confirmed via UI screenshot
    that the WRITE genuinely takes effect (Light Properties showed
    "Intensity Falloff: Inv Distance^2" right after setting
    falloff_type=2) while this field kept reporting the original
    default. Also tried li.falloff(light_id, t) (the (id, time) shape
    every other animatable field here uses) in case falloff is
    channel-driven like they are - confirmed live that this does NOT
    fix it either, it just returns the same stale value without even
    raising, so there's no exception to branch on. Left as the simple
    one-argument call and documented as an open, un-worked-around
    limitation of the read path rather than shipping dead code that
    only pretends to address it."""
    light_id = _find_item(name)
    if light_id is None:
        return {"error": "light not found: %s" % name}
    li = lwsdk.LWLightInfo()
    t = _current_time()
    return {
        "name": name,
        "type": li.type(light_id),
        "falloff": li.falloff(light_id),
        "color_rgb": _vec_to_list(li.color(light_id, t)),
        "intensity": li.intensity(light_id, t),
        "range": li.range(light_id, t),
        "evaluated_at_time": t,
    }


def _get_transform(name):
    """Item position/rotation/scale. FOUND THE REAL API - does NOT use
    LWChannelInfo/nextGroup (confirmed crashing, see _probe_channels
    below). NewTek's C SDK docs (etwright.org/lwsdk/docs/globals/
    iteminfo.html) show LWItemInfo already has a direct `param(item,
    param_type, time, vector)` call for exactly this - position/rotation/
    scale are LWIP_POSITION/LWIP_ROTATION/LWIP_SCALING. Real-world Python
    plugin code (a bone-rigging tool, found via web search) confirmed the
    Python binding is the 3-arg form `item_info.param(item_id, type,
    time)` returning the vector directly (no separate out-parameter,
    matching the pattern already proven for LWCameraInfo/LWLightInfo in
    this file). Same live-time fix as camera/light info."""
    target = _find_item(name)
    if target is None:
        return {"error": "item not found: %s" % name}
    ii = lwsdk.LWItemInfo()
    t = _current_time()
    return {
        "name": name,
        "position": _vec_to_list(ii.param(target, lwsdk.LWIP_POSITION, t)),
        "rotation": _vec_to_list(ii.param(target, lwsdk.LWIP_ROTATION, t)),
        "scale": _vec_to_list(ii.param(target, lwsdk.LWIP_SCALING, t)),
        "evaluated_at_time": t,
    }


def _get_surface_info(name):
    """Surface/material info via LWSurfaceFuncs(). Real-world Python
    plugin code (OD_CopyPasteExternal on GitHub, found via web search)
    confirmed live calling conventions: byName(surfname, objname) and
    byObject(objname) return plain Python-iterable lists of surface IDs
    (not the NULL-terminated C array the SDK doc describes - SWIG handles
    that), and getFlt(surf, channel) returns a plain float directly
    (compared with `> 0` in the reference code), not the C pointer the
    doc describes. objname=None should match every object per the C doc.
    Untested against a real textured object as of this writing (the live
    scene only had a Null and default Light/Camera) - test with a real
    object before trusting this fully; wrap in the same try/except
    _handle_query already has so a bad channel name degrades to an error
    response rather than an unhandled exception."""
    surf_ids = lwsdk.LWSurfaceFuncs().byName(name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % name}
    surf = surf_ids[0]
    sf = lwsdk.LWSurfaceFuncs()
    return {
        "name": sf.name(surf),
        "color_rgb": _vec_to_list(sf.getFlt(surf, lwsdk.SURF_COLR)),
        "diffuse": sf.getFlt(surf, lwsdk.SURF_DIFF),
        "luminosity": sf.getFlt(surf, lwsdk.SURF_LUMI),
        "specularity": sf.getFlt(surf, lwsdk.SURF_SPEC),
        "glossiness": sf.getFlt(surf, lwsdk.SURF_GLOS),
        "reflection": sf.getFlt(surf, lwsdk.SURF_REFL),
        "transparency": sf.getFlt(surf, lwsdk.SURF_TRAN),
        "smoothing": sf.getFlt(surf, lwsdk.SURF_SMAN),
    }


_SURF_SCALAR_CHANNELS = {
    "diffuse": "SURF_DIFF",
    "luminosity": "SURF_LUMI",
    "specularity": "SURF_SPEC",
    "glossiness": "SURF_GLOS",
    "reflection": "SURF_REFL",
    "transparency": "SURF_TRAN",
    "smoothing": "SURF_SMAN",
}


def _set_surface(arg):
    """ROADMAP2.md item 8 - the first WRITE in this connector to go
    through the read-path's Master plugin/LWComRing instead of the
    one-way Command Port, since lwsdk.LWSurfaceFuncs() (already used to
    read surfaces) is where the setter methods actually live - there is
    no native SurfaceEditor-style Command Port command for this, it
    just opens the UI panel. A temporary lw_introspect diagnostic tool
    (since removed) confirmed LWSurfaceFuncs really does expose
    setFlt/setColorVMap/setImg/setMaterial/setInt/setShadingModel/setTex
    as real bound methods, not just a C-docs claim.

    Wire format: `arg` is "<surface_name>|<json object>" - the surface
    name is kept outside the JSON so it can contain spaces without
    escaping, using "|" as a separator on the (safe) assumption a real
    surface name won't contain one.

    IMPORTANT, found the hard way: this function was briefly shipped as
    a permanently-disabled stub after set_surface calls appeared to hang
    the ring_event callback forever (confirmed "twice" via the debug log
    going silent right after logging the incoming request). That
    diagnosis was WRONG. The real bug was in _TOPIC_RE (see its
    definition above): the original pattern's GREEDY (.+) matched from
    the first "{" to the LAST "}" in the whole raw message, not the
    first one - fine for every prior command, whose payloads never
    contained braces, but this command's JSON-encoded arg does. A
    standalone regex test confirmed the old pattern parsed topic as
    garbage (e.g. 'MCP} set_surface CONNECTOR|{"diffuse": 0.5', not
    "MCP") for a real set_surface message, so `if topic != TOPIC: return`
    silently dropped it before _handle_query - let alone setFlt() - ever
    ran. setFlt() was never actually reached the first time this was
    tested. Fixed by making _TOPIC_RE's first group non-greedy. Real
    lesson for this project's methodology: an "it looks exactly like our
    one documented crash" debug-log signature (message logged, then
    silence) does NOT by itself prove the same failure mode - the
    silence here had a completely different, mundane cause. Re-verify
    with the simplest possible reproduction (a standalone script, not
    just re-reading the same live symptom) before concluding a new SDK
    call is unsafe.

    After the _TOPIC_RE fix, re-verified live from scratch rather than
    trusting the fix on paper: setFlt(surf, SURF_DIFF, 0.5) alone first
    (Surface Editor showed 50.0%, lw_get_surface_info read back 0.5),
    then setFlt(surf, SURF_COLR, (1,0,0)) + setFlt(surf, SURF_GLOS, 0.8)
    together in one call (screenshot showed a genuinely red color
    swatch and "Glossiness 80.0%", both matching the read-back exactly).
    setFlt(surf, SURF_COLR, (r,g,b)) accepting a plain 3-tuple, the same
    as getFlt returns, is now confirmed symmetric, not just assumed."""
    surf_name, sep, props_json = arg.partition("|")
    if not sep:
        return {"error": "malformed set_surface arg, expected 'name|{json}': %r" % arg}
    props = json.loads(props_json)
    surf_ids = lwsdk.LWSurfaceFuncs().byName(surf_name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % surf_name}
    surf = surf_ids[0]
    sf = lwsdk.LWSurfaceFuncs()
    sent = []
    if "color" in props:
        sf.setFlt(surf, lwsdk.SURF_COLR, tuple(props["color"]))
        sent.append("color")
    for key, const_name in _SURF_SCALAR_CHANNELS.items():
        if key in props:
            sf.setFlt(surf, getattr(lwsdk, const_name), float(props[key]))
            sent.append(key)
    return {"result": "set %s on %s" % (sent, surf_name)}


def _probe_channels(name):
    """DISABLED as of this edit: lwsdk.LWChannelInfo().nextGroup(target,
    None) - called with an item ID (from LWItemInfo) as the first
    argument, satisfying the "takes exactly 3 arguments" signature error
    seen with nextGroup(None) alone - reproducibly took down the entire
    Layout process (no Python exception, no crash-report-worthy Python
    traceback, just silence in the debug log after "about to call" and
    then total unresponsiveness / an actual LightWave crash-reporter
    dialog on next Quit). Confirmed twice. There is no LWChannelInfo C
    header shipped with this install to check the real expected argument
    types, and guessing further risks more crashes/restarts. Leaving
    this stubbed out - ROADMAP item 1b (item transform query) is
    blocked on this until NewTek's actual SDK docs/header for
    LWChannelInfo can be consulted (see PLAN.md for the full writeup)."""
    target = _find_item(name)
    if target is None:
        return {"error": "item not found: %s" % name}
    return {
        "target_id": repr(target),
        "error": "probe disabled - nextGroup(item, prev) crashed Layout twice, "
                 "see PLAN.md 'LWChannelInfo crash' section",
    }


_MAX_CHANNELS_PER_ITEM = 20
_MAX_KEYS_PER_CHANNEL = 500


def _get_channels(name):
    """ROADMAP2.md item 9 - the real, shipped feature this whole
    investigation was building toward: an item's channel/keyframe
    structure (which frames have keys, what value, what interpolation
    shape), closing the gap lw_get_transform's single-point-in-time
    evaluation always had.

    Built entirely on mechanisms confirmed safe by explicit,
    user-approved live testing first (see PLAN.md 'Keyframe/envelope
    reading' for the full staged investigation, matching this project's
    standing rule for this exact SDK area - the one place with a
    confirmed real crash, LWChannelInfo/nextGroup, see 'LWChannelInfo
    crash'):
      - LWItemInfo().chanGroup(item) is the item's OWN channel group -
        confirmed live that LWChannelInfo().nextChannel(chanGroup(item),
        None) directly enumerates the item's own channels (Position.X,
        Position.Y, ...), no LWChannelInfo().nextGroup() hop needed at
        all for this purpose (nextGroup instead walks to OTHER, related
        groups - e.g. a child bone's own group - confirmed by name via
        groupName(), not needed here).
      - nextChannel(group, prev)/nextKey(envelope, prev): prev=None for
        the first result, the previous real result to continue: a
        second real call in both cases returned a genuine next
        result (channel: "Position.Y"; a fresh confirmation the pattern
        continues correctly, not just works once) and confirmed live
        that Python None (not a crash, not an exception, not
        LWITEM_NULL) is the reliable "no more" sentinel, obtained on a
        channel with a single implicit key.
      - keyGet(envelope, key, LWKEY_TIME/VALUE/SHAPE) returns a 2-element
        [status, value] list, not a bare value - confirmed live
        (originally miscalled as keyGet(key, param), a 3-arg call that
        raised a clean, catchable "takes exactly 4 arguments" error, not
        a crash - fixed to keyGet(envelope, key, param)).

    Bounded the same way _get_bones is (a fixed cap far above any
    realistic real count, as a safety margin against a hypothetical
    malformed/circular list hanging the loop, not because normal data
    should ever approach it) rather than trusting an unbounded while
    True. key "time" is converted from raw seconds to a frame number via
    LWSceneInfo().framesPerSecond, the same convention _get_current_time
    already established, alongside the raw seconds value for anyone who
    needs it. "shape" is the raw LWKEY_SHAPE integer (matching the Graph
    Editor's interpolation curve types) - not translated to a name here,
    since no confirmed mapping of those integers to LightWave's own
    labels (TCB/Linear/Stepped/etc.) was established this session; do
    not guess at that mapping without live verification against a key
    with a known, UI-set interpolation type."""
    item = _find_item(name)
    if item is None:
        return {"error": "item not found: %s" % name}
    ii = lwsdk.LWItemInfo()
    ci = lwsdk.LWChannelInfo()
    ef = lwsdk.LWEnvelopeFuncs()
    fps = lwsdk.LWSceneInfo().framesPerSecond

    group = ii.chanGroup(item)
    channels = []
    chan = None
    chan_count = 0
    while chan_count < _MAX_CHANNELS_PER_ITEM:
        chan = ci.nextChannel(group, chan)
        if chan is None:
            break
        chan_count += 1
        env = ci.channelEnvelope(chan)
        keys = []
        key = None
        key_count = 0
        while key_count < _MAX_KEYS_PER_CHANNEL:
            key = ef.nextKey(env, key)
            if key is None:
                break
            key_count += 1
            _, t = ef.keyGet(env, key, lwsdk.LWKEY_TIME)
            _, v = ef.keyGet(env, key, lwsdk.LWKEY_VALUE)
            _, shape = ef.keyGet(env, key, lwsdk.LWKEY_SHAPE)
            keys.append({
                "time_seconds": t,
                "frame": t * fps if fps else None,
                "value": v,
                "shape": shape,
            })
        channels.append({
            "name": ci.channelName(chan),
            "type": ci.channelType(chan),
            "keys": keys,
        })
    return {"name": name, "channels": channels}


_MAX_NODES_PER_EDITOR = 50
_MAX_INPUTS_PER_NODE = 60
_MAX_SURFACE_GROUPS = 30
_MAX_SURFACE_CHANNELS = 60


def _get_surface_nodes(surf_name):
    """ROADMAP3.md item 2 - list every node in a surface's node graph
    (e.g. "Surface", "Input", "Standard (1)", "Principled BSDF (1)" for
    a surface with a Principled BSDF added). Uses LWSurfaceFuncs()
    .getNodeEditor(surf) + LWNodeEditorFuncs numberOfNodes/nodeByIndex
    (a bounded-count-then-index shape, not an open-ended
    first()/next() traversal) plus LWNodeFuncs nodeName/serverUserName
    to identify each one. Confirmed live: even a "Standard"-material
    surface that was never manually node-edited already has an implicit
    3-node graph ("Surface"/"Input"/"Standard (1)") - LightWave's nodal
    architecture underlies every surface, not just ones built by hand in
    the Node Editor. node_name includes a "(N)" instance suffix when
    more than one of the same node type exists; server_user_name is the
    plain type name (e.g. "Principled BSDF") without that suffix - use
    server_user_name to find a node type regardless of how many
    instances exist, node_name to address one specific instance."""
    surf_ids = lwsdk.LWSurfaceFuncs().byName(surf_name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % surf_name}
    surf = surf_ids[0]
    sf = lwsdk.LWSurfaceFuncs()
    editor = sf.getNodeEditor(surf)

    nef = lwsdk.LWNodeEditorFuncs()
    nf = lwsdk.LWNodeFuncs()
    count = nef.numberOfNodes(editor)
    nodes = []
    for i in range(min(count, _MAX_NODES_PER_EDITOR)):
        node = nef.nodeByIndex(editor, i)
        nodes.append({
            "node_name": nf.nodeName(node),
            "server_user_name": nf.serverUserName(node),
        })
    return {"surface": surf_name, "nodes": nodes}


def _get_node_inputs(surf_name, target_node_name):
    """ROADMAP3.md item 2 - list a specific node's input parameter names
    and raw type codes (e.g. Principled BSDF's "Color"/"Roughness"/
    "Metallic"/etc. - confirmed live to correctly enumerate all 27 real
    parameters, exactly matching the Surface Editor panel). Uses
    LWNodeInputFuncs numInputs/byIndex (bounded-count shape, not the
    untested first()/next() pair this class also exposes).

    Does NOT report each input's current value: LWNodeInputFuncs
    evaluate_scalar/evaluate_vector both failed live needing "4
    arguments (2 given)" - these appear to be render-time calls needing
    extra shading context (a per-shading-point structure) this
    connector has no way to supply outside an active render, not simple
    property getters. To read a specific input's actual value, add an
    envelope to it in the UI (Graph Editor, or the node's own envelope
    button) and use lw_get_node_channel instead - confirmed live to
    correctly read back an enveloped Roughness value (0.1, matching the
    UI's "10.0%") end to end via the same LWChannelInfo/LWEnvelopeFuncs
    machinery ROADMAP2.md item 9 already proved safe. This is a real,
    confirmed limitation, not a placeholder: a parameter with no
    envelope has no value reachable through this connector today."""
    surf_ids = lwsdk.LWSurfaceFuncs().byName(surf_name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % surf_name}
    surf = surf_ids[0]
    sf = lwsdk.LWSurfaceFuncs()
    editor = sf.getNodeEditor(surf)
    nef = lwsdk.LWNodeEditorFuncs()
    nf = lwsdk.LWNodeFuncs()

    count = nef.numberOfNodes(editor)
    target_node = None
    for i in range(min(count, _MAX_NODES_PER_EDITOR)):
        node = nef.nodeByIndex(editor, i)
        if nf.nodeName(node) == target_node_name:
            target_node = node
            break
    if target_node is None:
        return {"error": "node not found: %s" % target_node_name}

    nif = lwsdk.LWNodeInputFuncs()
    input_count = nif.numInputs(target_node)
    inputs = []
    for i in range(min(input_count, _MAX_INPUTS_PER_NODE)):
        inp = nif.byIndex(target_node, i)
        inputs.append({"name": nif.name(inp), "type": nif.type(inp)})
    return {"surface": surf_name, "node": target_node_name, "inputs": inputs}


def _get_node_channel(surf_name, node_name, channel_name):
    """ROADMAP3.md item 2 - the real payoff of this whole investigation:
    read a node parameter's actual keyframe data (frame/time, value,
    interpolation shape), the same shape lw_get_channels already reports
    for item transform channels.

    Root-caused live, in stages, why a node parameter isn't reachable
    through LWNodeInputFuncs.evaluate_scalar/vector (see
    lw_get_node_inputs): the real path turned out to mirror ROADMAP2.md
    item 9's item-channel discovery almost exactly.
    LWSurfaceFuncs().chanGrp(surf) is a surface's own top-level channel
    group; ONE nextGroup() hop reaches a "Nodes" container group
    (confirmed live: chanGrp(surf) alone has zero direct channels - not
    a crash, just legitimately empty); a SECOND nextGroup() hop within
    "Nodes", matched by groupName(), reaches the specific node's own
    group (e.g. "Principled BSDF (1)"); nextChannel() within THAT group
    finds the parameter, but ONLY if a human (or a future write tool)
    has explicitly added an envelope to it first - confirmed live that
    an un-enveloped parameter's group has zero channels (not a crash,
    still just empty), and the exact same parameter appears the instant
    an envelope is added via the UI. Once found, channelEnvelope()/
    nextKey()/keyGet() are the identical, already-proven-safe calls
    lw_get_channels already uses for item transforms.

    Confirmed live end to end: after enveloping Principled BSDF's
    "Roughness" via the Graph Editor, this correctly read back
    {"value": 0.1, "frame": 0.0, ...}, matching the UI's "10.0%" exactly.
    Real, confirmed limitation: reports "channel not found" for any
    parameter that hasn't been enveloped - this is the honest boundary
    of what's readable today, not a bug to work around."""
    surf_ids = lwsdk.LWSurfaceFuncs().byName(surf_name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % surf_name}
    surf = surf_ids[0]
    sf = lwsdk.LWSurfaceFuncs()
    top_group = sf.chanGrp(surf)

    ci = lwsdk.LWChannelInfo()
    ef = lwsdk.LWEnvelopeFuncs()
    fps = lwsdk.LWSceneInfo().framesPerSecond

    nodes_group = ci.nextGroup(top_group, None)
    if nodes_group is None:
        return {"error": "no 'Nodes' sub-group found on %s" % surf_name}

    target_group = None
    group = None
    for _ in range(_MAX_SURFACE_GROUPS):
        group = ci.nextGroup(nodes_group, group)
        if group is None:
            break
        if ci.groupName(group) == node_name:
            target_group = group
            break
    if target_group is None:
        return {"error": "node group not found: %s" % node_name}

    target_chan = None
    chan = None
    for _ in range(_MAX_SURFACE_CHANNELS):
        chan = ci.nextChannel(target_group, chan)
        if chan is None:
            break
        if ci.channelName(chan) == channel_name:
            target_chan = chan
            break
    if target_chan is None:
        return {"error": "channel not found (not enveloped?): %s" % channel_name}

    env = ci.channelEnvelope(target_chan)
    keys = []
    key = None
    for _ in range(_MAX_KEYS_PER_CHANNEL):
        key = ef.nextKey(env, key)
        if key is None:
            break
        _, t = ef.keyGet(env, key, lwsdk.LWKEY_TIME)
        _, v = ef.keyGet(env, key, lwsdk.LWKEY_VALUE)
        _, shape = ef.keyGet(env, key, lwsdk.LWKEY_SHAPE)
        keys.append({"time_seconds": t, "frame": t * fps if fps else None, "value": v, "shape": shape})
    return {"surface": surf_name, "node": node_name, "channel": channel_name, "keys": keys}


def _add_node(surf_name, node_type, x=0, y=0):
    """Node Editor writing, step 1 - create a new node in a surface's
    node graph, via the same save/rewrite/load route as _rewire_nodes
    (PLAN.md "Node Editor writing").

    Deliberately does NOT use LWNodeEditorFuncs.addNode, which this tool
    originally wrapped. A node made by addNode looks normal (visible in
    the Node Editor, listed by lw_get_surface_nodes) but poisons the
    graph: a later LWNodeEditorFuncs.load of it never returns, wedging
    the ring listener until Layout restarts - confirmed live twice,
    while the identical load over a HAND-added node of the same type
    and name worked. addNode nodes plausibly also caused all three
    connect freezes.

    Instead: save the graph as ASCII, append a minimal node block to
    its "{ Nodes }" section - Server/RealName = node_type, Name =
    "<node_type> (N)" with N one past the highest existing instance,
    Coordinates x y (default 0 0, the graph's origin - see _move_node),
    and an empty "{ Data }" (as the Surface and Input nodes are saved),
    so the node starts from its own defaults - then load it back. It
    then saves again and confirms the node really exists.

    CRITICAL, inherited from the addNode version: an unknown node_type
    pops a modal "Plug-in Missing" dialog that freezes Layout. Only pass
    exact server_user_name values already seen via lw_get_surface_nodes
    (e.g. "Principled BSDF", "Standard"), never a Node Editor category
    name or a guess."""
    if '"' in node_type or "\n" in node_type or not node_type.strip():
        return {"error": "invalid node_type: %r" % node_type}
    surf_ids = lwsdk.LWSurfaceFuncs().byName(surf_name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % surf_name}
    editor = lwsdk.LWSurfaceFuncs().getNodeEditor(surf_ids[0])
    nef = lwsdk.LWNodeEditorFuncs()
    nf = lwsdk.LWNodeFuncs()

    existing = _node_names(nef, nf, editor)
    pattern = re.compile(r"^%s \((\d+)\)$" % re.escape(node_type))
    taken = [int(m.group(1)) for m in (pattern.match(n) for n in existing) if m]
    node_name = "%s (%d)" % (node_type, max(taken) + 1 if taken else 1)

    path = os.path.join(_HERE, _REWIRE_SCRATCH)
    try:
        lines = _save_graph_text(editor, path).splitlines()
        try:
            nodes_start = lines.index("{ Nodes")
            nodes_end = lines.index("}", nodes_start)
        except ValueError:
            return {"error": "saved graph has no { Nodes } block"}
        block = [
            '  Server "%s"' % node_type,
            "  { Tag",
            '    RealName "%s"' % node_type,
            '    Name "%s"' % node_name,
            "    Coordinates %d %d" % (x, y),
            "    Mode 1",
            "    Selected 0",
            "    { Data",
            "    }",
            "  }",
        ]
        with open(path, "w") as f:
            f.write("\n".join(lines[:nodes_end] + block + lines[nodes_end:]) + "\n")
        _load_graph_file(editor, path)
        _save_graph_text(editor, path)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    after = _node_names(nef, nf, editor)
    if node_name not in after:
        return {"error": "node not present after load: %s" % node_name, "nodes": after}
    node = _find_node(nef, nf, editor, node_name)
    return {
        "surface": surf_name,
        "node_name": node_name,
        "server_user_name": nf.serverUserName(node),
    }


_CONNECTION_KEYS = ("NodeName", "InputName", "InputNodeName", "InputOutputName")
_REWIRE_SCRATCH = "_mcp_nodes__rewire.txt"


def _find_node(nef, nf, editor, node_name):
    """Resolve a node_name to its NodeID; "Surface" is the root node."""
    if node_name == "Surface":
        return nef.getRootNodeID(editor)
    for i in range(min(nef.numberOfNodes(editor), _MAX_NODES_PER_EDITOR)):
        node = nef.nodeByIndex(editor, i)
        if nf.nodeName(node) == node_name:
            return node
    return None


def _node_names(nef, nf, editor):
    return [nf.nodeName(nef.nodeByIndex(editor, i))
            for i in range(min(nef.numberOfNodes(editor), _MAX_NODES_PER_EDITOR))]


def _input_names(nif, node):
    """Input names via numInputs/byIndex, skipping the unnamed entry the
    root Surface node reports at index 0. Note that on the root node this
    misses its last input (OpenGL) - see PLAN.md "Node Editor writing"."""
    names = []
    for i in range(min(nif.numInputs(node), _MAX_INPUTS_PER_NODE)):
        name = nif.name(nif.byIndex(node, i))
        if name:
            names.append(name)
    return names


def _output_names(nof, node):
    """Output names via first/next - byIndex(node, 0) returns nothing."""
    names = []
    out = nof.first(node)
    while out is not None and len(names) < _MAX_INPUTS_PER_NODE:
        names.append(nof.name(out))
        out = nof.next(out)
    return names


def _save_graph_text(editor, path):
    fio = lwsdk.LWFileIOFuncs()
    state = fio.openSave(path, lwsdk.LWIO_ASCII)
    if state is None:
        raise RuntimeError("openSave returned no state for %s" % path)
    try:
        lwsdk.LWNodeEditorFuncs().save(editor, state)
    finally:
        fio.closeSave(state)
    with open(path) as f:
        return f.read()


def _load_graph_file(editor, path):
    fio = lwsdk.LWFileIOFuncs()
    state = fio.openLoad(path, lwsdk.LWIO_ASCII)
    if state is None:
        raise RuntimeError("openLoad returned no state for %s" % path)
    try:
        lwsdk.LWNodeEditorFuncs().load(editor, state)
    finally:
        fio.closeLoad(state)


def _split_connections(text):
    """Split a saved ASCII node graph into (text before the
    "{ Connections" block, list of connection dicts). Parses strictly -
    the block must be nothing but repeated NodeName/InputName/
    InputNodeName/InputOutputName lines in that order - and raises on
    anything else rather than risk loading a mangled graph. A graph
    with no block at all has no connections."""
    lines = text.splitlines()
    try:
        start = lines.index("{ Connections")
    except ValueError:
        return text.rstrip("\n") + "\n", []
    try:
        end = lines.index("}", start)
    except ValueError:
        raise RuntimeError("unterminated { Connections } block")
    if any(line.strip() for line in lines[end + 1:]):
        raise RuntimeError("unexpected content after { Connections } block")
    body = [line.strip() for line in lines[start + 1:end] if line.strip()]
    if len(body) % len(_CONNECTION_KEYS):
        raise RuntimeError("unexpected { Connections } layout: %r" % body)
    connections = []
    for i in range(0, len(body), len(_CONNECTION_KEYS)):
        conn = {}
        for key, line in zip(_CONNECTION_KEYS, body[i:i + len(_CONNECTION_KEYS)]):
            m = re.match(r'^%s "([^"]*)"$' % key, line)
            if not m:
                raise RuntimeError("unexpected { Connections } line: %r" % line)
            conn[key] = m.group(1)
        connections.append(conn)
    return "\n".join(lines[:start]) + "\n", connections


def _join_connections(head, connections):
    if not connections:
        return head
    out = [head.rstrip("\n"), "{ Connections"]
    for conn in connections:
        for key in _CONNECTION_KEYS:
            out.append('  %s "%s"' % (key, conn[key]))
    out.append("}")
    return "\n".join(out) + "\n"


def _describe(connections):
    return ["%s.%s -> %s.%s" % (c["InputNodeName"], c["InputOutputName"],
                                c["NodeName"], c["InputName"]) for c in connections]


def _rewire_nodes(surf_name, to_node_name, input_name, from_node_name, output_name):
    """Node Editor wiring via save/load (PLAN.md "Node Editor writing",
    step 3). Wires from_node's output into to_node's input, replacing
    whatever fed that input before; with from_node_name None, only
    disconnects that input.

    LWNodeEditorFuncs.connect is NOT used: it made the connection but
    froze Layout's UI in all three live runs. Instead this saves the
    surface's whole graph as ASCII (LWFileIOFuncs.openSave +
    LWNodeEditorFuncs.save), rewrites its "{ Connections }" block -
    which names every wire by node/socket name - and loads it back
    (openLoad + load), which was confirmed live to replace the graph
    exactly and leave Layout responsive. It then saves once more and
    returns the connections LightWave actually reports, so the result
    is verified rather than assumed.

    Every name is checked against the live graph first (nodes via
    numberOfNodes/nodeByIndex, inputs via LWNodeInputFuncs, outputs via
    LWNodeOutputFuncs first/next), and an unknown one returns an error
    listing the valid choices - nothing is loaded. An open Surface
    Editor does not refresh after the load; close and reopen it."""
    names = [surf_name, to_node_name, input_name, from_node_name or "", output_name or ""]
    if any('"' in n or "\n" in n for n in names):
        return {"error": "names may not contain quotes or newlines"}
    surf_ids = lwsdk.LWSurfaceFuncs().byName(surf_name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % surf_name}
    editor = lwsdk.LWSurfaceFuncs().getNodeEditor(surf_ids[0])
    nef = lwsdk.LWNodeEditorFuncs()
    nf = lwsdk.LWNodeFuncs()

    to_node = _find_node(nef, nf, editor, to_node_name)
    if to_node is None:
        return {"error": "node not found: %s (available: %s)"
                         % (to_node_name, _node_names(nef, nf, editor))}
    inputs = _input_names(lwsdk.LWNodeInputFuncs(), to_node)
    if input_name not in inputs:
        return {"error": "input not found on %s: %s (available: %s)"
                         % (to_node_name, input_name, inputs)}

    new_conn = None
    if from_node_name is not None:
        from_node = _find_node(nef, nf, editor, from_node_name)
        if from_node is None:
            return {"error": "node not found: %s (available: %s)"
                             % (from_node_name, _node_names(nef, nf, editor))}
        outputs = _output_names(lwsdk.LWNodeOutputFuncs(), from_node)
        if not outputs:
            return {"error": "node has no outputs: %s" % from_node_name}
        output_name = output_name or outputs[0]
        if output_name not in outputs:
            return {"error": "output not found on %s: %s (available: %s)"
                             % (from_node_name, output_name, outputs)}
        new_conn = {"NodeName": to_node_name, "InputName": input_name,
                    "InputNodeName": from_node_name, "InputOutputName": output_name}

    path = os.path.join(_HERE, _REWIRE_SCRATCH)
    try:
        head, connections = _split_connections(_save_graph_text(editor, path))
        kept = [c for c in connections
                if not (c["NodeName"] == to_node_name and c["InputName"] == input_name)]
        if new_conn is None and len(kept) == len(connections):
            return {"error": "nothing connected to %s.%s" % (to_node_name, input_name),
                    "connections": _describe(connections)}
        if new_conn is not None:
            kept.append(new_conn)
        with open(path, "w") as f:
            f.write(_join_connections(head, kept))
        _load_graph_file(editor, path)
        _, after = _split_connections(_save_graph_text(editor, path))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    result = {"surface": surf_name, "before": _describe(connections),
              "connections": _describe(after)}
    if new_conn is not None:
        result["connected"] = new_conn in after
    else:
        result["disconnected"] = not any(
            c["NodeName"] == to_node_name and c["InputName"] == input_name for c in after)
    return result


_UNREMOVABLE_NODES = ("Surface", "Input")


def _node_block_span(lines, node_name):
    """(first, last) line indexes of one node's block in a saved ASCII
    graph's "{ Nodes }" section. A block runs from its '  Server
    "<type>"' line to the first line that is exactly '  }' (the Tag
    close - everything inside it, attribute data included, is indented
    deeper); the node is identified by its '    Name "<node_name>"' line
    at Tag level. Raises if the node isn't found exactly once."""
    nodes_start = lines.index("{ Nodes")
    nodes_end = lines.index("}", nodes_start)
    blocks = []
    i = nodes_start + 1
    while i < nodes_end:
        if lines[i].startswith('  Server "'):
            close = lines.index("  }", i)
            blocks.append((i, close))
            i = close + 1
        else:
            i += 1
    target = '    Name "%s"' % node_name
    matches = [(a, b) for a, b in blocks if target in lines[a:b + 1]]
    if len(matches) != 1:
        raise RuntimeError("expected one block for %s, found %d" % (node_name, len(matches)))
    return matches[0]


def _drop_node_block(text, node_name):
    """Remove one node's block from a saved ASCII graph."""
    lines = text.splitlines()
    a, b = _node_block_span(lines, node_name)
    return "\n".join(lines[:a] + lines[b + 1:]) + "\n"


def _coordinates_index(lines, node_name):
    """Index of a node's Tag-level '    Coordinates x y' line."""
    a, b = _node_block_span(lines, node_name)
    hits = [i for i in range(a, b + 1) if lines[i].startswith("    Coordinates ")]
    if len(hits) != 1:
        raise RuntimeError("expected one Coordinates line for %s, found %d"
                           % (node_name, len(hits)))
    return hits[0]


def _node_coordinates(text, node_name):
    lines = text.splitlines()
    return [int(v) for v in lines[_coordinates_index(lines, node_name)].split()[1:3]]


def _move_node(surf_name, node_name, x, y):
    """Node Editor writing - reposition a node in the Node Editor's
    graph view by rewriting its block's Coordinates line in the saved
    graph and loading it back (the same save/rewrite/load route as the
    other node tools; LWNodeEditorFuncs.setXY is not used). Purely
    cosmetic: placement has no effect on shading. Works on any node,
    including Surface and Input. Saves again afterwards and reports the
    coordinates LightWave actually has."""
    if '"' in node_name or "\n" in node_name or not node_name:
        return {"error": "invalid node name: %r" % node_name}
    surf_ids = lwsdk.LWSurfaceFuncs().byName(surf_name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % surf_name}
    editor = lwsdk.LWSurfaceFuncs().getNodeEditor(surf_ids[0])
    nef = lwsdk.LWNodeEditorFuncs()
    nf = lwsdk.LWNodeFuncs()
    if _find_node(nef, nf, editor, node_name) is None:
        return {"error": "node not found: %s (available: %s)"
                         % (node_name, _node_names(nef, nf, editor))}

    path = os.path.join(_HERE, _REWIRE_SCRATCH)
    try:
        lines = _save_graph_text(editor, path).splitlines()
        i = _coordinates_index(lines, node_name)
        before = [int(v) for v in lines[i].split()[1:3]]
        lines[i] = "    Coordinates %d %d" % (x, y)
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        _load_graph_file(editor, path)
        after = _node_coordinates(_save_graph_text(editor, path), node_name)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return {"surface": surf_name, "node": node_name, "before": before,
            "coordinates": after, "moved": after == [x, y]}


def _remove_node(surf_name, node_name):
    """Node Editor writing - delete a node from a surface's node graph,
    along with every wire to or from it, via the same save/rewrite/load
    route as _add_node/_rewire_nodes (PLAN.md "Node Editor writing").
    LWNodeEditorFuncs.destroyNode is not used, in keeping with avoiding
    the node SDK's direct mutators (addNode poisoned graphs; connect
    froze Layout).

    Refuses "Surface" (the root output node) and "Input", which every
    surface has built in. Saves the graph again afterwards and confirms
    the node is gone."""
    if '"' in node_name or "\n" in node_name or not node_name:
        return {"error": "invalid node name: %r" % node_name}
    if node_name in _UNREMOVABLE_NODES:
        return {"error": "%s is built into every surface and can't be removed" % node_name}
    surf_ids = lwsdk.LWSurfaceFuncs().byName(surf_name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % surf_name}
    editor = lwsdk.LWSurfaceFuncs().getNodeEditor(surf_ids[0])
    nef = lwsdk.LWNodeEditorFuncs()
    nf = lwsdk.LWNodeFuncs()
    if _find_node(nef, nf, editor, node_name) is None:
        return {"error": "node not found: %s (available: %s)"
                         % (node_name, _node_names(nef, nf, editor))}

    path = os.path.join(_HERE, _REWIRE_SCRATCH)
    try:
        head, connections = _split_connections(_save_graph_text(editor, path))
        kept = [c for c in connections
                if node_name not in (c["NodeName"], c["InputNodeName"])]
        with open(path, "w") as f:
            f.write(_join_connections(_drop_node_block(head, node_name), kept))
        _load_graph_file(editor, path)
        _, after = _split_connections(_save_graph_text(editor, path))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    nodes_after = _node_names(nef, nf, editor)
    return {
        "surface": surf_name,
        "removed": node_name not in nodes_after,
        "wires_removed": _describe([c for c in connections if c not in kept]),
        "nodes": nodes_after,
        "connections": _describe(after),
    }


_VALUE_SHAPES = {"vparam": 1, "vparam3": 3, "int": 1}


def _node_attrs(lines, node_name):
    """Parse every stored input value in one node's block of a saved
    ASCII graph. Each input is an '{ Attr' block: 'Name "<input>"',
    some 'Tag' lines (FORMAT gives the units: Percent is stored as a
    fraction, Color as 0-1 per channel, Distance in metres), then
    '{ Value' + a type line and the value itself in one of three shapes:

        "vparam"  / { Value / 1 / <x> / }        - one number
        "vparam3" / { Value / 3 / <x y z> / }    - three numbers
        "int"     / <n>                          - one whole number

    Returns one dict per input with the line index of its value, so
    _set_node_input can rewrite exactly that line. An input whose value
    doesn't match those shapes (an enveloped one, say) is reported with
    type "unsupported" and no value rather than guessed at."""
    a, b = _node_block_span(lines, node_name)
    attrs = []
    i = a
    while i <= b:
        if lines[i].strip() != "{ Attr":
            i += 1
            continue
        indent = len(lines[i]) - len(lines[i].lstrip())
        end = i + 1
        while not (lines[end].strip() == "}"
                   and len(lines[end]) - len(lines[end].lstrip()) == indent):
            end += 1
        body = [line.strip() for line in lines[i + 1:end]]
        m = re.match(r'^Name "([^"]*)"$', body[0]) if body else None
        attr = {"name": m.group(1) if m else None, "format": None,
                "type": "unsupported", "value": None, "line": None}
        for line in body:
            fm = re.match(r'^Tag "FORMAT" "([^"]*)"$', line)
            if fm:
                attr["format"] = fm.group(1)
        if "{ Value" in body:
            v = body.index("{ Value")
            kind = body[v + 1:v + 2]
            try:
                if kind == ['"int"']:
                    attr.update(type="int", value=[int(body[v + 2])], line=i + 1 + v + 2)
                elif kind in (['"vparam"'], ['"vparam3"']):
                    shape = kind[0].strip('"')
                    count = _VALUE_SHAPES[shape]
                    if (body[v + 2] == "{ Value" and body[v + 3] == str(count)
                            and body[v + 5] == "}"):
                        values = [float(x) for x in body[v + 4].split()]
                        if len(values) == count:
                            attr.update(type=shape, value=values, line=i + 1 + v + 4)
            except (IndexError, ValueError):
                pass
        if attr["name"] is not None:
            attrs.append(attr)
        i = end + 1
    return attrs


def _public_attr(attr):
    return {k: attr[k] for k in ("name", "format", "type", "value")}


def _get_node_values(surf_name, node_name):
    """Read every stored input value of one node - the values
    LWNodeInputFuncs.evaluate_* can't give outside a render - by saving
    the graph as ASCII and parsing the node's block (see _node_attrs).
    Read-only: nothing is loaded back."""
    surf_ids = lwsdk.LWSurfaceFuncs().byName(surf_name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % surf_name}
    editor = lwsdk.LWSurfaceFuncs().getNodeEditor(surf_ids[0])
    nef = lwsdk.LWNodeEditorFuncs()
    nf = lwsdk.LWNodeFuncs()
    if _find_node(nef, nf, editor, node_name) is None:
        return {"error": "node not found: %s (available: %s)"
                         % (node_name, _node_names(nef, nf, editor))}
    path = os.path.join(_HERE, _REWIRE_SCRATCH)
    try:
        lines = _save_graph_text(editor, path).splitlines()
        attrs = _node_attrs(lines, node_name)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return {"surface": surf_name, "node": node_name,
            "inputs": [_public_attr(a) for a in attrs]}


def _format_value(shape, values):
    if shape == "int":
        return str(int(values[0]))
    return " ".join("%.17g" % float(v) for v in values)


def _set_node_input(surf_name, node_name, input_name, values):
    """Set one stored input value on a node by rewriting that input's
    value line in the saved ASCII graph and loading it back - the same
    save/rewrite/load route as the other node tools. values is a list
    whose length must match the input's shape (1 for "vparam"/"int",
    3 for "vparam3"), in LightWave's internal units (see _node_attrs).
    Re-saves afterwards and reports the value LightWave actually holds,
    plus a warning when a wire feeds the input (the wire then decides
    the input, not this value)."""
    surf_ids = lwsdk.LWSurfaceFuncs().byName(surf_name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % surf_name}
    editor = lwsdk.LWSurfaceFuncs().getNodeEditor(surf_ids[0])
    nef = lwsdk.LWNodeEditorFuncs()
    nf = lwsdk.LWNodeFuncs()
    if _find_node(nef, nf, editor, node_name) is None:
        return {"error": "node not found: %s (available: %s)"
                         % (node_name, _node_names(nef, nf, editor))}

    path = os.path.join(_HERE, _REWIRE_SCRATCH)
    try:
        text = _save_graph_text(editor, path)
        lines = text.splitlines()
        attrs = _node_attrs(lines, node_name)
        matches = [a for a in attrs if a["name"] == input_name]
        if len(matches) != 1:
            return {"error": "no stored value for input %s on %s (inputs with values: %s)"
                             % (input_name, node_name, [a["name"] for a in attrs])}
        attr = matches[0]
        if attr["line"] is None:
            return {"error": "input %s has a value shape this tool doesn't handle "
                             "(enveloped?) - not changed" % input_name}
        if len(values) != _VALUE_SHAPES[attr["type"]]:
            return {"error": "%s takes %d number(s) (%s, format %s), got %d"
                             % (input_name, _VALUE_SHAPES[attr["type"]], attr["type"],
                                attr["format"], len(values))}
        if attr["type"] == "int" and float(values[0]) != int(values[0]):
            return {"error": "%s takes a whole number" % input_name}
        before = attr["value"]
        old_line = lines[attr["line"]]
        indent = old_line[:len(old_line) - len(old_line.lstrip())]
        lines[attr["line"]] = indent + _format_value(attr["type"], values)
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        _load_graph_file(editor, path)
        after_text = _save_graph_text(editor, path)
        after = [a for a in _node_attrs(after_text.splitlines(), node_name)
                 if a["name"] == input_name][0]
        _, connections = _split_connections(after_text)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    result = {"surface": surf_name, "node": node_name, "input": input_name,
              "format": attr["format"], "before": before, "value": after["value"],
              "set": after["value"] is not None and all(
                  abs(x - float(y)) < 1e-9 for x, y in zip(after["value"], values))}
    wired = [c for c in connections
             if c["NodeName"] == node_name and c["InputName"] == input_name]
    if wired:
        result["warning"] = ("a wire feeds this input (%s), so it overrides this value"
                             % _describe(wired)[0])
    return result


def _resolve_name(ii, item_id):
    """None for LWITEM_NULL (no relationship set), otherwise the item's
    name. Isolated so a bad/unexpected ID degrades to None instead of
    raising and killing the whole hierarchy query."""
    try:
        if item_id is None or item_id == lwsdk.LWITEM_NULL:
            return None
        return ii.name(item_id)
    except Exception:
        return None


_MAX_BONES_PER_OBJECT = 200


def _get_bones(ii, object_id):
    """Walk the bone chain within one object via LWItemInfo.first(
    LWI_BONE, object)/next() - confirmed live via a temporary probe
    tool (removed once this shipped) before this loop was written:
    LWI_BONE exists, and a single first()/next() call pair completed
    safely against a real 2-bone chain with no crash, unlike the
    LWChannelInfo/nextGroup path (see PLAN.md) this project has
    previously confirmed crashes Layout outright with no Python
    exception. Capped at
    _MAX_BONES_PER_OBJECT as a safety margin against a hypothetical
    malformed/circular chain hanging the loop - far more than any real
    scene should ever have, so it should never actually bind in
    practice. Each bone reports the same parent/target/goal/pole shape
    as every other item here, plus which bone (if any, within the same
    object) it's parented to - a bone's own parent() can point outside
    the chain (e.g. to the host object) so that's resolved by name
    like everything else, not assumed to be another bone.

    ROADMAP2.md item 7: also reports each bone's own numeric "id" (via
    lwsdk.itemid_to_str(), the same conversion _get_item_id uses) -
    added because bones have no other way to get a numeric ID from this
    connector. Confirmed live via Cmd History that manually clicking a
    bone in the Scene Editor logs "SelectItem 40000000" - bones live in
    their own ID range, distinct from Object/Light/Camera's
    10000000/20000000/30000000. server.py's _resolve_item_id passes a
    purely numeric `item` string straight through so this ID can be fed
    directly into lw_set_ik_options/lw_toggle_ik_flag/lw_set_goal/etc."""
    bones = []
    bone_id = ii.first(lwsdk.LWI_BONE, object_id)
    count = 0
    while bone_id != lwsdk.LWITEM_NULL and count < _MAX_BONES_PER_OBJECT:
        entry = {
            "name": ii.name(bone_id),
            "type": "BONE",
            "id": lwsdk.itemid_to_str(bone_id),
            "parent": _resolve_name(ii, ii.parent(bone_id)),
        }
        for key, getter in (("target", ii.target), ("goal", ii.goal), ("pole", ii.pole)):
            try:
                entry[key] = _resolve_name(ii, getter(bone_id))
            except Exception:
                pass
        bones.append(entry)
        bone_id = ii.next(bone_id)
        count += 1
    return bones


def _get_hierarchy():
    """Parent/child and IK (target/goal/pole) relationships for every
    object/light/camera, plus bone chains within each object. Uses
    LWItemInfo.parent()/target()/goal()/pole() - confirmed via NewTek's
    official Python SDK docs (fetched live from static.lightwave3d.com/
    sdk/2015/python/globaliteminfo.html, since none ship with this
    install; this is the same LWItemInfo class already proven safe here
    for _get_transform's param() calls, NOT the LWChannelInfo path that
    crashed Layout - see PLAN.md). parent() returns an item ID or
    LWITEM_NULL, so each relationship is resolved to a name via a
    second LWItemInfo call rather than returned as a raw ID, matching
    how every other query in this file reports items.

    Bone chain traversal (see _get_bones) confirmed live against a real
    2-bone chain on a Null (BoneTestObject/Bone1/Bone2) - bones can be
    added directly to a Null via AddBone/AddChildBone, no real mesh
    geometry required, which made this far cheaper to verify than
    expected."""
    ii = lwsdk.LWItemInfo()
    items = []
    for label, item_type in (
        ("OBJECT", lwsdk.LWI_OBJECT),
        ("LIGHT", lwsdk.LWI_LIGHT),
        ("CAMERA", lwsdk.LWI_CAMERA),
    ):
        it = ii.first(item_type, lwsdk.LWITEM_NULL)
        while it != lwsdk.LWITEM_NULL:
            entry = {
                "name": ii.name(it),
                "type": label,
                "parent": _resolve_name(ii, ii.parent(it)),
            }
            for key, getter in (("target", ii.target), ("goal", ii.goal), ("pole", ii.pole)):
                try:
                    entry[key] = _resolve_name(ii, getter(it))
                except Exception:
                    pass
            if label == "OBJECT":
                bones = _get_bones(ii, it)
                if bones:
                    entry["bones"] = bones
            items.append(entry)
            it = ii.next(it)
    return {"items": items}


def _get_item_id(name):
    """Resolve an item's name to the plain numeric ID string LightWave's
    native item-reference commands (ParentItem, TargetItem, GoalItem,
    PoleItem) actually expect on the Command Port - confirmed via Cmd
    History showing real UI-driven actions log as e.g. "ParentItem
    10000000", never a name. SelectItem is the odd one out: its command
    handler resolves names internally (confirmed working via lw_name
    string args throughout this project), but ParentItem/TargetItem do
    not - passing a name silently coerces to argument 0 (a no-op), with
    no error and no dialog. lwsdk.itemid_to_str() (a module-level
    helper, found by grepping an old _introspect() diagnostic dump for
    "itemid" - sitting unused in lwsdk.dir() since long before this was
    identified as the actual root cause) converts the opaque NodeID
    handle _find_item() already returns into exactly that numeric string
    form. See PLAN.md 'ParentItem argument format' for the Cmd History
    evidence."""
    item = _find_item(name)
    if item is None:
        return {"error": "item not found: %s" % name}
    return {"name": name, "id": lwsdk.itemid_to_str(item)}


def _get_render_status():
    """Reads the status file written by lw_mcp_render_monitor.py's
    IFrameBuffer.open()/close() callbacks (ROADMAP.md item 6). Separate
    plug-in/file from this one because Frame Buffer is a different
    LightWave plug-in architecture (Render Display server) than Master
    (LWComRing) - this query just surfaces its output over the read
    path already proven here, rather than requiring a second polling
    mechanism on the client side."""
    if not os.path.exists(RENDER_STATUS_PATH):
        return {
            "rendering": None,
            "note": "no render has been triggered yet this session, or "
                    "lw_mcp_render_monitor.py isn't set as the active Render "
                    "Display (Render Globals > Render Display tab) - see "
                    "lw_mcp_render_monitor.py's docstring",
        }
    try:
        with open(RENDER_STATUS_PATH) as f:
            return json.load(f)
    except (ValueError, OSError) as exc:
        return {"error": str(exc)}


def _probe_surf_constants():
    names = [n for n in dir(lwsdk) if n.startswith("SURF_")]
    return sorted(names)


def _probe_node_write_sigs():
    """DIAGNOSTIC, temporary: step 2 of the Node Editor writing
    investigation. Calls each write-candidate method found by
    _probe_node_write with zero arguments and captures the resulting
    Python TypeError message - the same safe signature-discovery
    technique already used for LWNodeInputFuncs.evaluate_scalar/
    evaluate_vector in the read-side investigation (a bad argument
    count fails in Python before any native LightWave call happens, so
    this cannot touch scene state)."""
    candidates = {
        "LWNodeEditorFuncs": ["addNode", "connect", "destroyNode", "setXY", "reset"],
        "LWNodeFuncs": ["setNodeColor", "setNodeColor3", "setNodePreviewType"],
        "LWNodeInputFuncs": ["create", "createCustom", "destroy", "disconnect", "connectedOutput"],
        "LWNodeOutputFuncs": ["create", "createCustom", "destroy", "setValue"],
    }
    result = {}
    for cls_name, method_names in candidates.items():
        cls = getattr(lwsdk, cls_name)
        instance = cls()
        cls_result = {}
        for method_name in method_names:
            method = getattr(instance, method_name)
            try:
                method()
                cls_result[method_name] = {"called_with_zero_args": "no error raised"}
            except TypeError as exc:
                cls_result[method_name] = {"type_error": str(exc)}
            except Exception as exc:  # noqa: BLE001
                cls_result[method_name] = {"other_error": str(exc)}
        result[cls_name] = cls_result
    return result













def _probe_node_write():
    """DIAGNOSTIC, temporary: safe dir() scan (zero risk - Python
    introspection on freshly-constructed objects, nothing live touched)
    of the node-related SDK classes already found during ROADMAP3.md
    item 2's read-side investigation, filtered for write-suggestive
    method names. Step 1 of a future Node Editor writing investigation -
    following the exact same staged, dir()-first discipline that
    investigation already used."""
    write_keywords = (
        "add", "create", "new", "insert", "remove", "delete", "destroy",
        "connect", "disconnect", "link", "unlink", "wire", "clone",
        "set", "assign", "attach", "detach",
    )
    classes = [
        "LWNodeFuncs", "LWNodeEditorFuncs", "LWNodeInputFuncs",
        "LWNodeOutputFuncs", "LWNodeUtilityFuncs", "LWNodeDrawFuncs",
        "LWNodeMenuFuncs",
    ]
    result = {}
    for cls_name in classes:
        cls = getattr(lwsdk, cls_name, None)
        if cls is None:
            result[cls_name] = {"error": "class not found"}
            continue
        try:
            instance = cls()
            names = dir(instance)
        except Exception as exc:  # noqa: BLE001
            result[cls_name] = {"error": str(exc)}
            continue
        matches = sorted(
            n for n in names
            if not n.startswith("_")
            and any(kw in n.lower() for kw in write_keywords)
        )
        result[cls_name] = matches
    return result


def _get_scene_info():
    scene = lwsdk.LWSceneInfo()
    iteminfo = lwsdk.LWItemInfo()

    items = []
    for item_type in (lwsdk.LWI_OBJECT, lwsdk.LWI_LIGHT, lwsdk.LWI_CAMERA):
        item = iteminfo.first(item_type, lwsdk.LWITEM_NULL)
        while item != lwsdk.LWITEM_NULL:
            items.append(iteminfo.name(item))
            item = iteminfo.next(item)

    return {
        "scene_name": scene.name,
        "filename": scene.filename,
        "items": items,
    }


def _introspect():
    """Diagnostic: find real lwsdk class/method names for extending the
    read path (item transform, selection, surface, camera/light info).
    Temporary - not part of the permanent tool surface."""
    interesting_substrings = [
        "Channel", "Surface", "Camera", "Light", "Item", "Select",
        "State", "Transform", "Scene", "Bound",
    ]
    names = dir(lwsdk)
    matches = sorted(set(
        n for n in names
        if any(s.lower() in n.lower() for s in interesting_substrings)
    ))

    probes = {}
    for expr in [
        "lwsdk.LWItemInfo()",
        "lwsdk.LWSceneInfo()",
        "lwsdk.LWChannelInfo()",
        "lwsdk.LWStateQueryFuncs()",
        "lwsdk.LWSurfaceFuncs()",
        "lwsdk.LWCameraInfo()",
        "lwsdk.LWLightInfo()",
        "lwsdk.LWObjectInfo()",
        "lwsdk.LWObjectFuncs()",
    ]:
        try:
            obj = eval(expr)
            probes[expr] = [m for m in dir(obj) if not m.startswith("_")]
        except Exception as exc:  # noqa: BLE001
            probes[expr] = "FAILED: %s" % exc

    return {"matches": matches, "probes": probes}


def _get_current_time():
    """Exposes _current_time()'s fix directly - useful on its own to
    confirm what time an lw_get_camera_info/lw_get_light_info/
    lw_get_transform call will evaluate at, without needing an
    animated item to notice a difference. frame is derived from
    time/framesPerSecond via LWSceneInfo (already proven safe
    elsewhere in this file) since LWTimeInfo only exposes seconds."""
    t = _current_time()
    fps = lwsdk.LWSceneInfo().framesPerSecond
    return {"time": t, "frame": t * fps if fps else None}


def _handle_query(text):
    parts = text.split(None, 1)
    command = parts[0] if parts else "ping"
    arg = parts[1].strip() if len(parts) > 1 else ""

    try:
        if command == "ping":
            payload = {"result": "pong"}
        elif command == "get_scene_info":
            payload = {"result": _get_scene_info()}
        elif command == "introspect":
            payload = {"result": _introspect()}
        elif command == "get_selection":
            payload = {"result": _get_selection()}
        elif command == "get_camera_info":
            payload = {"result": _get_camera_info(arg or "Camera")}
        elif command == "get_light_info":
            payload = {"result": _get_light_info(arg or "Light")}
        elif command == "get_transform":
            payload = {"result": _get_transform(arg or "TransformTest")}
        elif command == "get_surface_info":
            payload = {"result": _get_surface_info(arg)}
        elif command == "set_surface":
            payload = {"result": _set_surface(arg)}
        elif command == "probe_channels":
            payload = {"result": _probe_channels(arg or "TransformTest")}
        elif command == "get_channels":
            payload = {"result": _get_channels(arg or "TransformTest")}
        elif command == "get_surface_nodes":
            payload = {"result": _get_surface_nodes(arg or "CONNECTOR")}
        elif command == "get_node_inputs":
            surf_arg, _, node_arg = arg.partition("|")
            payload = {"result": _get_node_inputs(surf_arg or "CONNECTOR", node_arg or "Principled BSDF (1)")}
        elif command == "get_node_channel":
            parts_gnc = arg.split("|")
            surf_a = parts_gnc[0] if len(parts_gnc) > 0 and parts_gnc[0] else "CONNECTOR"
            node_a = parts_gnc[1] if len(parts_gnc) > 1 and parts_gnc[1] else "Principled BSDF (1)"
            chan_a = parts_gnc[2] if len(parts_gnc) > 2 and parts_gnc[2] else "Roughness"
            payload = {"result": _get_node_channel(surf_a, node_a, chan_a)}
        elif command == "add_node":
            parts_an = (arg.split("|") + [""] * 4)[:4]
            payload = {"result": _add_node(parts_an[0] or "CONNECTOR",
                                           parts_an[1] or "Principled BSDF",
                                           int(parts_an[2] or 0), int(parts_an[3] or 0))}
        elif command == "get_node_values":
            surf_gv, _, node_gv = arg.partition("|")
            payload = {"result": _get_node_values(surf_gv or "CONNECTOR", node_gv)}
        elif command == "set_node_input":
            parts_si = arg.split("|", 3)
            if len(parts_si) != 4:
                payload = {"error": "set_node_input needs surface|node|input|values"}
            else:
                values_si = json.loads(parts_si[3])
                if not isinstance(values_si, list):
                    values_si = [values_si]
                payload = {"result": _set_node_input(parts_si[0] or "CONNECTOR", parts_si[1],
                                                     parts_si[2], values_si)}
        elif command == "move_node":
            parts_mn = (arg.split("|") + [""] * 4)[:4]
            payload = {"result": _move_node(parts_mn[0] or "CONNECTOR", parts_mn[1],
                                            int(parts_mn[2] or 0), int(parts_mn[3] or 0))}
        elif command == "connect_nodes":
            parts_cn = (arg.split("|") + [""] * 5)[:5]
            payload = {"result": _rewire_nodes(parts_cn[0] or "CONNECTOR",
                                               parts_cn[2] or "Surface",
                                               parts_cn[3] or "Material",
                                               parts_cn[1] or "Principled BSDF (1)",
                                               parts_cn[4])}
        elif command == "disconnect_nodes":
            parts_dn = (arg.split("|") + [""] * 3)[:3]
            payload = {"result": _rewire_nodes(parts_dn[0] or "CONNECTOR",
                                               parts_dn[1] or "Surface",
                                               parts_dn[2] or "Material",
                                               None, None)}
        elif command == "remove_node":
            surf_rn, _, node_rn = arg.partition("|")
            payload = {"result": _remove_node(surf_rn or "CONNECTOR", node_rn)}
        elif command == "probe_surf":
            payload = {"result": _probe_surf_constants()}
        elif command == "probe_node_write":
            payload = {"result": _probe_node_write()}
        elif command == "probe_node_write_sigs":
            payload = {"result": _probe_node_write_sigs()}
        elif command == "get_render_status":
            payload = {"result": _get_render_status()}
        elif command == "get_hierarchy":
            payload = {"result": _get_hierarchy()}
        elif command == "get_item_id":
            payload = {"result": _get_item_id(arg)}
        elif command == "get_current_time":
            payload = {"result": _get_current_time()}
        else:
            payload = {"error": "unknown command: %s" % command}
    except Exception as exc:  # noqa: BLE001
        payload = {"error": str(exc)}

    _write_response(payload)


class mcp_ring_master_v4(lwsdk.IMaster):
    def __init__(self, context):
        super(mcp_ring_master_v4, self).__init__()
        self._comring = lwsdk.LWComRing()
        _log("mcp_ring_master_v4 instantiated")

    # LWInstanceFuncs ---------------------------------------------------
    def inst_copy(self, source):
        return None

    def inst_descln(self):
        return "Claude MCP Command Port Ring listener"

    def inst_acquire(self):
        self._comring.ringAttach(lwsdk.LW_PORT_COMMAND_PORT, self, self.ring_event)
        _log("ringAttach called")

    def inst_release(self):
        self._comring.ringDetach(lwsdk.LW_PORT_COMMAND_PORT, self)
        _log("ringDetach called")

    # ComRing -------------------------------------------------------------
    def ring_event(self, client_data, port_data, event_code, event_data):
        if event_code != 0:
            return
        data = self._comring.decodeData(('s:256',), event_data)
        if not data:
            _log("ring_event: decodeData failed")
            return
        raw = data[0]
        _log("ring_event: raw=%r" % (raw,))
        m = _TOPIC_RE.match(raw)
        if not m:
            return
        topic, rest = m.group(1), m.group(2)
        if topic != TOPIC:
            return
        _handle_query(rest.strip())

    # LWMaster ------------------------------------------------------------
    def flags(self):
        return lwsdk.LWMAST_LAYOUT

    def event(self, ma):
        return 0.0


ServerTagInfo = [
    ("LW MCP Ring4", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.MasterFactory("LW_MCP_Ring4", mcp_ring_master_v4): ServerTagInfo,
}
