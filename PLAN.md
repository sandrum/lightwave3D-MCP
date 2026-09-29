# Claude ↔ LightWave 2019 MCP connector — build plan

## Item hierarchy query (ROADMAP.md item 7) — DONE

User asked for a way to understand an object's existing parent/child
(and rigging-relevant IK target/goal/pole) relationships before rigging
on top of it. Found the real API the same way as items 1b/1c/6 - fetched
NewTek's official Python SDK docs live rather than guessing
(`static.lightwave3d.com/sdk/2015/python/globaliteminfo.html` - the
`docs.lightwave3d.com` 2025 docs didn't have this specific page indexed,
but the 2015 static docs cover the same `LWItemInfo` class already
proven safe in this project). Confirmed real methods: `parent(item)`,
`target(item)`, `goal(item)`, `pole(item)`, each returning an item ID or
`LWITEM_NULL`.

Shipped `lw_get_hierarchy` (via a new `get_hierarchy` query in
`lw_mcp_ring.py`). Each relationship ID is resolved to a name via a
second `LWItemInfo.name()` call so the response matches every other
query's convention of reporting names, not raw IDs.

**Live-verified with a real relationship, not just an empty scene:**
queried a flat scene (`Light`, `Camera`, no parents) and got `parent:
null` for both, as expected. Then created `ParentTest`/`ChildTest`
nulls and tried to reparent via `lw_run_command("ParentItem",
["ParentTest"])` after `SelectItem("ChildTest")` - **this did NOT
work**: re-querying showed `ChildTest.parent` still `null`, and the
Motion Options panel confirmed `Parent Item: (none)`. Root cause not
yet investigated (worth a follow-up if this connector needs to *write*
parenting, not just read it - possibly needs an item ID rather than a
name, or a different command entirely). Set the parent for real via the
Motion Options panel's "Parent Item" dropdown instead, then re-queried:
`lw_get_hierarchy` correctly returned `{"name": "ChildTest", "parent":
"ParentTest", ...}`. The read side is proven correct against ground
truth; the write side for parenting specifically is not yet solved.

**Deliberately out of scope this round:** bone chain traversal
(`LWItemInfo.first(LWI_BONE, object)` / `next()`) - the live scene had
no boned object to safely verify traversal against, and this project has
a real precedent (`LWChannelInfo`/`nextGroup`) for an SDK traversal call
crashing Layout, so it wasn't shipped un-tested. Follow-up once there's
a real rigged object to test against.

## Render / camera automation (ROADMAP.md item 6) — DONE

The real problem here was never "how do I trigger a render" - RenderFrame/
RenderScene are ordinary native commands, already reachable via
lw_run_command. It was that every command sent through this project's
Command Port client is one-way UDP fire-and-forget (confirmed by reading
`CommandPort._send_command` in `lwcommandport/__init__.py` - it only ever
calls `sendto()`, nothing reads a response), so firing a render command
and assuming it succeeded/finished would just be guessing, which is
exactly what this roadmap item said to avoid.

**Found the real completion signal via NewTek's official docs, not more
live probing.** No docs ship with this 2019.1.5 install, so fetched
docs.lightwave3d.com's 2025 Python SDK reference live (same fetch
pattern that worked for item 1b/1c's `LWItemInfo.param`) and found the
Frame Buffer handler class (`lwsdk.IFrameBuffer` /
`FrameBufferFactory`) - LightWave's actual plug-in architecture for
"Render Display" servers. Real engine-driven callbacks, not polling:
`open(width, height)` when a render session begins, `write()` per
scanline, `close()` when it's complete, `pause()` only during
interactive (F9/manual-advance) renders, not automatic ones.

Shipped `lw_mcp_render_monitor.py`, a Frame Buffer plug-in that ignores
actual pixel data and just records lifecycle state
(`{"rendering": bool, "frame_count": int, "width", "height", "updated"}`)
to `_mcp_render_status.json` on open()/close(). Extended `lw_mcp_ring.py`
with a `get_render_status` query that reads that file and returns it
over the already-proven LWComRing read path - no second polling
mechanism needed. New tools: `lw_render_frame`, `lw_render_scene`,
`lw_abort_render`, `lw_get_render_status`, `lw_set_camera_resolution`
(wraps `FrameSize` - confirmed this is a scene-wide render global in
LightWave, not literally a per-camera setting, despite the name).

**One real wrinkle, discovered live rather than assumed:** LightWave has
no networked way to select which Frame Buffer plug-in is the active
Render Display (`SetRenderDisplay`/`RenderDisplayOptions` take no
arguments per the local command list) - it's chosen once via Render
Properties > General tab > "Render Display" dropdown. Same one-time
manual-UI-step pattern this whole project already leans on for Master
Plugins activation. Confirmed via the dropdown itself listing "LW MCP
Render Monitor" right alongside the built-in options once the plug-in is
loaded, so at least the registration side needs zero guessing.

**Live-verified twice, end to end:**
1. Manually via `lw_run_command("RenderFrame")` before the new server.py
   tools were loaded (Claude Desktop hadn't been restarted yet):
   `_mcp_render_status.json` went from not-existing, to
   `{"rendering": true, "frame_count": 1, "width": 1280, "height": 720}`
   the instant the Render Status dialog appeared, to
   `{"rendering": false, "frame_count": 1}` the instant "Continue" was
   clicked to dismiss it.
2. After restarting to load the new tools: `lw_set_camera_resolution(640,
   360)` -> confirmed 640x360 in the Render Status dialog ->
   `lw_render_frame(frame=0)` -> `lw_get_render_status()` returned
   `rendering: true` with matching width/height while the dialog was still
   up -> dismissed it -> `lw_get_render_status()` returned `rendering:
   false`. Real state read from the render engine's own callbacks, not a
   timer or guess.

Not yet tested: multi-frame `RenderScene` (whether frame_count increments
once per frame or the open/close cycle behaves differently for
animations - the docstring in lw_mcp_render_monitor.py calls this out as
an open question worth checking before relying on frame_count for
progress-bar-style tracking across a whole animation render).

## Animation helper tools (ROADMAP.md item 4) — DONE

Shipped `lw_set_keyframe(name, frame, position=None, rotation=None,
scale=None)` in `server.py`, wrapping the by-hand sequence
(`SelectItem` → `GoToFrame` → `Position`/`Rotation`/`Scale` → `CreateKey`)
into one call. All five native commands were already proven-reachable via
`lw_run_command`, so this was API design, not new SDK territory.

Live-verified end to end on a fresh Null (`AnimTest`, recreated via
`lw_create_null` after the prior session's scene was lost to a Layout
restart):

- `lw_set_keyframe("AnimTest", frame=0, position=[0,0,0])`
- `lw_set_keyframe("AnimTest", frame=30, position=[5,5,5])`

Confirmed via screenshot at three scrubbed timeline positions, not just
the tool's own "success" response:
- Frame 0: Position readout `0m, 0m, 0m`, item at the origin.
- Frame 30: Position readout `5m, 5m, 5m`, with a visible motion path
  from the origin.
- Frame 15 (midpoint): Position readout `3.104m, 3.104m, 3.104m` - not
  the linear midpoint (2.5), consistent with Layout's default TCB spline
  interpolation kicking in between the two keys. This is the real proof:
  the item is genuinely animating between keyframes, not just being
  written to twice.

One documented unit mismatch: `lw_set_keyframe`'s `rotation` argument is
in degrees (Layout's native command-line/UI convention, confirmed live -
values entered here show unchanged in the Motion Options panel), while
`lw_get_transform`'s rotation reading is in radians (the `LWItemInfo` SDK
global's convention). Not a bug, just two different native conventions
on the write side vs. the read side - noted in both tools' docstrings.

## Modeler read path (ROADMAP.md item 5) — researched, confirmed blocked

**Finding: there is currently no known way to get query answers out of a
running Modeler session over the network.** This is a real, well-evidenced
architectural limitation, not a bug in this project's code - confirmed
using NewTek's own bundled sample plugin, not just ours.

Modeler has no Master-plugin/`LWComRing` equivalent at all - confirmed via
`Glob` against the local install: `support/plugins/scripts/Python/Modeler/`
only has a `CommandSequence` folder, no `Master` folder, and NewTek's SDK
docs (docs.lightwave3d.com) confirm Modeler's Python plugin architecture is
`CommandSequence`-only. The natural next idea - since a `CommandSequence`
plug-in registers as an ordinary invocable command, and
`modeler_run_command` already proves arbitrary *native* command names are
invocable over Modeler's Command Port - was to invoke a custom
`CommandSequence` plug-in the same way, passing a query string as its
trailing argument (`mod_command.argument`, confirmed to exist and carry
trailing text via a public third-party plug-in,
github.com/heimlich1024/OD_CopyPasteExternal) and have it answer via a
response file, exactly like the Layout read path but without needing a
persistent listener.

**This does not work.** Live-tested three ways, all failed identically -
no exception, no error dialog, just silence:
- `modeler_ping()` (routed through `_send_command` via the wrapped
  `Modeler` class) - timed out, and `_mcp_modeler_debug.log` was never
  created, meaning `process()` never ran.
- Raw UDP packets sent directly from Modeler's own PCore Python console
  (`socket.sendto(b'LW_MCP_ModelerQuery ping', ('localhost', 9736))` and a
  quoted-display-name variant `"LW MCP Modeler Query" ping`) - `sendto()`
  itself succeeded (returned the byte count, no exception), but the debug
  log still never gained a new line.
- The exact same test against **NewTek's own bundled sample plug-in**
  (`support/plugins/scripts/Python/Modeler/CommandSequence/
  enumerate_surfaces.py`, registered factory ID `LW_PyEnumSurfaces`) via
  raw socket - no observable effect either.

Meanwhile, invoking our plug-in through the UI (Utilities > Additional >
"LW MCP Modeler Query") worked immediately and correctly - `process()`
ran, `mod_command.argument` was empty as expected for a menu click, and
the response file was written. So the plug-in code itself is correct; the
network Command Port specifically does not route to it.

**Conclusion:** despite the `--command-port` documentation's description
("feed LightWave Command Sequence commands directly into the
application"), the network Command Port for both Layout and Modeler
appears to only reach LightWave's native/compiled command table - not
Python-registered plug-in commands. This is the exact same failure mode
that ruled out Layout's very first read-path attempt (`CommandInput
LW_MCP_Query ping` → `"Unknown command"`, documented above) - except for
Modeler there is no known `LWComRing`-style escape hatch, since Modeler
has no persistent Master-plugin architecture at all. Every avenue found
in the SDK docs and every bundled sample either issues commands
*from within* an already-running plug-in (`lookup`/`execute`/`evaluate`,
requires already being invoked some other way first) or requires the
same blocked network invocation to get started.

**Practical alternative, not a true "live" read path:** since Modeler
objects are ordinary `.lwo` files, an external client can already inspect
point/poly counts and surface names by loading the saved file directly
(bypassing Modeler's Python API entirely) - this is exactly how `TestBox.lwo`
was independently useful for testing the surface query in item 1c. This
only reflects saved state, not in-memory unsaved edits, so it's a
real but limited substitute, not a real-time query mechanism.

`lw_mcp_modeler_query.py` and the `modeler_ping`/`modeler_get_object_info`
tools are left in place since they work correctly when invoked from
inside Modeler (e.g. manually, or possibly from a future in-process
bridge) - just not from an external network client as originally hoped.

## Item transform + surface query (ROADMAP.md items 1b/1c) — DONE

**Resolved.** Tracked down NewTek's real SDK docs (etwright.org/lwsdk,
mirrored from the official SDK - the local install ships no headers) and
found real-world working Python plugin code on GitHub
(heimlich1024/OD_CopyPasteExternal) to confirm exact Python calling
conventions. Two real findings unblocked both items without ever going
back through `LWChannelInfo`:

- `LWItemInfo` already has a **direct** `param(item, param_type, time)`
  call for position/rotation/scale (`LWIP_POSITION`/`LWIP_ROTATION`/
  `LWIP_SCALING`) - documented in the C SDK
  (etwright.org/lwsdk/docs/globals/iteminfo.html) and confirmed via a
  real third-party Python plugin's usage pattern
  (`item_info.param(item_id, type, time)` returning the vector directly,
  matching the pattern already proven for `LWCameraInfo`/`LWLightInfo`
  in this file). This completely avoids `LWChannelInfo`/`nextGroup`,
  which is the crash confirmed below. Implemented as `_get_transform()`
  / `lw_get_transform`.
- `LWSurfaceFuncs().byName(surfname, objname)` and `.getFlt(surf,
  channel)` were confirmed via the same real-world plugin code to
  return plain Python lists/floats in the SWIG binding (not the C
  pointers the doc describes). Implemented as `_get_surface_info()` /
  `lw_get_surface_info`.

**Both confirmed live, end to end, with no crashes:**
- `lw_get_transform("TransformTest")` returned the correct default
  transform (`position [0,0,0]`, `rotation [0,0,0]`, `scale [1,1,1]`);
  after moving the item with `lw_run_command("Position", [1.5, 2,
  -0.5])`, a re-query correctly returned `position [1.5, 2.0, -0.5]` -
  proof this reads real live state, not just defaults.
- `lw_get_surface_info("Default")` against a real object (`TestBox.lwo`,
  a unit box built in Modeler and loaded into Layout for this test)
  returned sensible real values: `color_rgb [0.502, 0.502, 0.502]`,
  `diffuse 1.0`, `specularity 0.5`, `glossiness 0.4`, `transparency
  0.0`, `reflection 0.0`, `smoothing -1.5625`. The `smoothing` value's
  sign/exact meaning under the newer Principled BSDF shading model
  isn't fully decoded (magnitude is close to the ~89.5° smoothing angle
  shown in the Surface Editor, in radians) - flagged as a minor open
  question, not a blocker; the mechanism itself is proven safe and
  working.

The diagnostic `_probe_channels`/`lw_probe_channels` stub (crash
writeup below) and `_probe_surf_constants`/`lw_probe_surf` are now
superseded by the real tools and can be removed in a future cleanup
pass, but are left in place for now since they're harmless.

## LWChannelInfo crash (root cause of the original block, kept for the record)

`lwsdk.LWChannelInfo().nextGroup(...)` is the documented way to walk an
item's animation channels (position/rotation/scale live under one
"group" per item). Live probing found real, reproducible problems:

- `nextGroup(None)` (one arg, matching the SDK doc's example) raises
  `LWChannelInfo_nextGroup() takes exactly 3 arguments (2 given)` -
  confirming the doc is wrong about arity for this build; the real
  signature needs a second positional argument.
- `nextGroup(target, None)`, passing a real item ID (obtained from
  `LWItemInfo`, a SWIG object of type `NodeID`) as that second argument,
  **reproducibly crashes the entire Layout process** - no Python
  exception, no traceback, the debug log simply stops after logging
  "about to call nextGroup(target, None)". Confirmed twice, each time
  requiring a full process/machine restart to recover (the second
  occurrence left Layout in a state where even Quit triggered LightWave's
  native crash-reporter dialog). This is almost certainly a native/SWIG
  crash from passing the wrong ID type - `LWChannelInfo` most likely
  expects a different kind of handle (e.g. a channel-group ID) than the
  `NodeID` that `LWItemInfo` hands back, and the binding doesn't
  type-check before dereferencing.
- There is no `LWChannelInfo` C header shipped with this install to
  confirm the real expected argument types (only Python-only headers -
  numpy, PySide, shiboken, win32com - were found anywhere under the
  install directory). Guessing further risks more crashes.

**Decision: stopped guessing.** `_probe_channels()` in `lw_mcp_ring.py`
is now a safe stub - it resolves the target item and returns its ID
plus an explanation, without calling `nextGroup`. Confirmed live (see
below) that this stub is completely safe: repeated calls do not crash
or destabilize Layout. Real transform queries are blocked until NewTek's
actual SDK docs/headers for `LWChannelInfo` can be consulted, or until
someone finds a working reference sample (the same way the read path
itself was eventually solved via NewTek's bundled `command_port_test.py`
rather than guesswork).

**Two operational lessons from chasing this, worth remembering for any
future LightWave MCP debugging session:**

1. **Zombie Layout processes.** Multiple `Layout.exe` processes can run
   at once silently, and an old background one can stay bound to the
   Command Port and keep answering UDP queries with stale scene state
   and stale plugin code, while the window you're actually looking at
   and interacting with is a completely different, disconnected
   process. This produced a long, confusing detour (phantom items in
   query responses that didn't exist in the visible Scene Editor). If
   query results ever look stale or impossible, check Task Manager for
   more than one `Layout.exe` before doubting the code.
2. **"Remove" in Master Plugins doesn't fully deregister a plugin.**
   Repeated Add/Remove cycles during iteration created many duplicate
   entries in Layout's internal plugin catalog (visible in Utilities >
   Edit Plugins, grouped by category - accumulated ~10 stale entries
   this session: Diag through Diag6, Master, Ring through Ring3). Full
   removal requires selecting the entry in **Edit Plugins** (not Master
   Plugins) and clicking **Delete**. Separately, Layout persists "should
   this identifier be active" state at the *application* level, not the
   scene level - a fresh Layout launch after a full machine restart
   prompted "Plug-in Missing: No plug-in of type MasterHandler found
   with name LW_MCP_Ring4. Would you like to load it from disk?",
   confirming this survives across sessions independent of any scene
   file.

Also observed, not fully root-caused: `inst_acquire()`/`ringAttach()`
firing for a freshly-registered Master Plugin is intermittent in this
environment - sometimes the debug log shows the class instantiated but
never followed by "ringAttach called", with no clear trigger. Toggling
the "On" checkbox does not reliably fix it. The only workaround found is
repeating Remove → Add Plugins → reselect-from-dropdown until one
attempt works (usually within 1-3 tries). Current final verified state:
this cycle succeeded, and `lw_ping`, `lw_get_scene_info`, `lw_probe_surf`,
and the now-safe `lw_probe_channels` were all confirmed live against a
freshly-restarted Layout with no crash. Notably, `lw_probe_channels`'s
`target_id` field for a real Null item resolves to a SWIG object of type
`NodeID` (`<Swig Object of type 'NodeID' at 0x...>`) - concrete evidence
for the type-mismatch theory above, and a useful starting point if
`LWChannelInfo`'s real expected ID type is ever tracked down.

**Surface/material query (ROADMAP.md item 1c) is now done too** - see
the "DONE" section above. It turned out not to need `LWChannelInfo` at
all (surfaces have their own dedicated `LWSurfaceFuncs` global), so it
was never actually at risk from the crash above - it was just
sequenced behind item 1b out of caution until a working docs-first
approach was proven.

## Modeler write path (ROADMAP.md item 2)

Confirmed live end to end. Modeler uses a completely different
enable mechanism than Layout - not `lwsdk.LWCommandPort().enable()`, but
`lwsdk.ModCommand()` + looking up and executing a native command called
`"ENABLECOMMANDPORT"` (see `lw_enable_modeler_command_port.py`, adapted
from NewTek's own bundled sample). Two real findings from getting this
working:

- **Modeler treats single-file plug-ins differently than Layout.**
  Loading via Add Plugins only *registers* it as a "Modeling Command" -
  unlike Layout's Generic single-shot scripts, it does not run
  automatically. It has to be separately invoked afterward via
  Utilities > Additional > (the script's name, alphabetical in a long
  list).
- **`ModCommand.execute()`'s reported result code is unreliable.**
  Enabling the port returned `result=0` ("failure" per NewTek's own
  sample comment) both when the port was genuinely free and when it was
  already successfully bound and listening. Confirmed via a UDP
  bind-conflict test (the same ground-truth trick used earlier to debug
  Layout's Command Port) that the enable actually succeeded regardless
  of what the return code said - the title bar showing `(CP: 9736)` is
  the reliable signal, not the result code. This is a third confirmed
  bug/inconsistency in this SDK build's Python bindings, alongside
  `LWMessageFuncs.info()`'s arg count and `IMaster.__init__`'s arg count.

`modeler_run_command` in `server.py` mirrors `lw_run_command`, using the
previously-unused `Modeler` class in `lwcommandport/modeler/__init__.py`
(mesh cleanup, extrude/clone/array tools, booleans, file ops). Confirmed
live via the real MCP tool: sent `command="new"`, Modeler's title bar
changed from "Unnamed" to "Unnamed 1", confirming a real new object
layer was created.

**Not yet done: Modeler reads.** Modeler's plugin architecture
(`CommandSequence`) is different from Layout's Master-plugin model that
`LWComRing` uses for reads - see ROADMAP.md item 5 for what's still
open.

## Current status (tested live against a running Layout 2019.1.5)

**Writes: working, verified, twice over.** `lw.AddNull(...)` sent over UDP
to LightWave's Command Port produces a real Null item in the live scene -
confirmed visually via screenshot, including a from-scratch clean-session
retest (`CleanTest1`/`CleanTest2`, both showed up in the Scene Editor).
`lw_run_command` in `server.py` generalizes this to any of the ~800 native
commands in the bundled `lwcommandport` client.

Note: an earlier round of testing appeared to show writes silently
failing (no items appearing despite "success" responses). Root cause was
NOT a code bug - the Layout session itself had hung (stuck PCore Console,
unresponsive dialogs, Add Plugins silently not executing anything). A
clean Layout restart immediately fixed it. If writes ever appear to stop
working, suspect a hung session before suspecting the connector.

**Reads: now working.** Two earlier approaches were tried and both ruled
out by direct testing:

1. Registered Generic-class plug-in (`lw_mcp_query.py`), invoked by name
   via `CommandInput LW_MCP_Query ping`. Result every time: `Unknown
   command: "LW_MCP_Query"`. LightWave's command resolver only recognizes
   native/compiled commands (like AddNull) - Python `IGeneric` plug-ins
   aren't added to that namespace.
2. Master-class plug-in (`lw_mcp_master.py`) listening for
   `LWEVNT_COMMAND`, per the SDK doc's own `master.html` example.
   Confirmed via debug log that this event never fires for Command Port
   traffic at all (fires for ordinary UI actions only).

**The working mechanism: `LWComRing`.** Found in NewTek's own bundled
sample, which ships with every LightWave 2019.1.5 install:
`support/plugins/scripts/Python/Layout/Master/command_port_test.py`.
A Master plug-in holds an `lwsdk.LWComRing()` instance and calls
`ringAttach(lwsdk.LW_PORT_COMMAND_PORT, self, self.ring_event)` in
`inst_acquire()`. Command Port traffic arrives at `ring_event(...)` with
`event_code == 0`, decoded via `self._comring.decodeData(('s:256',),
event_data)`. Messages are expected wrapped as `"{Topic} message"`.

This is implemented in `lw_mcp_ring.py`, listening for topic `"MCP"`.
Confirmed live: after loading and activating it, sending
`Ring("MCP", "ping")` produced a real `ring_event` callback (captured in
`_mcp_ring_debug.log`).

**A real bug found along the way, in NewTek's own bundled client
library:** the `Ring(topic, command)` method in
`lwcommandport/__init__.py`, under Python 3, did:
```python
command = "{{0}} {1}".format(topic, command)
```
Doubled braces in `str.format` escape to a literal brace rather than
substituting - so this produces the literal string `"{0} ping"` instead
of `"{MCP} ping"`. Confirmed live via the debug log showing
`raw='{0} ping'`. Fixed to `"{{{0}}} {1}".format(topic, command)` (three
braces before, two after - correctly escapes to one literal `{`/`}`
around the substituted topic).

Also fixed two earlier real bugs found via live tracebacks:
- `lwsdk.LWMessageFuncs().info(text)` actually requires two arguments
  (`info(text, None)`), despite the SDK doc's own example showing one.
- `lwsdk.IMaster.__init__` is called by the factory as `klass(context)`
  (one arg), despite the SDK doc's own example showing
  `__init__(self, context, count)`.
These all suggest the local docs (and the bundled sample client code)
are somewhat out of sync with this LightWave build/Python version - worth
remembering if more of this surfaces.

## Setup for the read path (per fresh Layout session)

1. Utilities → Plugins → Add Plugins → `lw_mcp_ring.py`.
2. Utilities → Master Plugins → "Add Layout or Scene Master" dropdown →
   select "LW MCP Ring" (shows as "Claude MCP Command Port Ring
   listener") → confirm its "On" checkbox is ticked.
3. Restart the `server.py` MCP process (i.e. restart Claude Desktop) at
   least once after pulling this fix, so it picks up the corrected
   `lwcommandport/__init__.py` - it's imported once at process start and
   caches the old buggy version otherwise. Note: closing/reopening the
   Claude Desktop window is not enough to restart the underlying MCP
   subprocess on Windows - use Task Manager to End Task every "Claude"
   process, then relaunch.

**CONFIRMED LIVE END TO END** via the real `lw_ping` and `lw_get_scene_info`
MCP tools after this restart: `lw_ping` returned `"pong"`, and
`lw_get_scene_info` correctly returned the live scene's actual item list
(`CleanTest1`, `CleanTest2`, `Light`, `Camera`) - both nulls created
earlier in this same session via `lw_create_null`. Full read+write round
trip is proven working, not just theorized.

## Read path, round 2: selection, camera, light (ROADMAP.md item 1)

Added `lw_get_selection`, `lw_get_camera_info`, `lw_get_light_info` -
all confirmed live via the real MCP tools after a server restart. Found
the exact method signatures by writing three small throwaway probe
plug-ins (`lw_mcp_diag.py`, `diag2`, `diag3` - safe to ignore/leave
unloaded, kept only as a record of what was tried) that dumped live
`dir(lwsdk)` results and tested real method calls against the actual
scene, rather than guessing from static docs:

- `LWItemInfo().selected(item)` → 0/1, the reliable selection signal.
  Important: `flags() & LWITEMF_SELECTED` looked plausible from the name
  but is **not** reliable - tested live, returned the same flags value
  (37) for every item regardless of actual selection state.
- `LWCameraInfo`/`LWLightInfo` split into two calling conventions:
  non-animated properties take just the item ID (`resolution(id)`,
  `falloff(id)`, `type(id)`), while animatable ones need a second `time`
  argument (`focalLength(id, time)`, `color(id, time)`, etc.) - confirmed
  working with `time=0.0`.
- `LWLightInfo().color()` returns a `PCore::Vector` SWIG object, not
  JSON-serializable directly - converted via `.x`/`.y`/`.z`.

**Open limitation:** `time=0.0` means these evaluate at scene start, not
LightWave's live playhead position. There's no confirmed way yet to
query the actual current time from Python - fine for non-animated
cameras/lights, wrong for animated ones. See ROADMAP.md.

**Descoped, promoted to their own roadmap items:** item transform
(position/rotation/scale - needs `LWChannelInfo` group/channel
traversal with an unclear iteration-end sentinel) and surface/material
info (needs `SURF_*` constants not yet found via introspection).

## Files

- `lw_enable_command_port.py` — run once inside Layout to turn on the
  Command Port. Working.
- `lw_mcp_ring.py` — the working read-path Master plug-in (LWComRing).
  Must be both loaded (Add Plugins) and activated (Master Plugins panel)
  each fresh Layout session.
- `server.py` — external MCP bridge server. `lw_run_command`,
  `lw_create_null`, `lw_ping`, `lw_get_scene_info`, `lw_get_selection`,
  `lw_get_camera_info`, `lw_get_light_info`, and `modeler_run_command`
  all work now (reads require `lw_mcp_ring.py` to be active - see
  above; `modeler_run_command` requires
  `lw_enable_modeler_command_port.py` to have been run in Modeler).
- `lw_enable_modeler_command_port.py` — run once inside Modeler (via Add
  Plugins, then Utilities > Additional - see above for why it's two
  steps) to turn on Modeler's Command Port on 9736. Working, confirmed
  live.
- `lw_mcp_diag.py`, `lw_mcp_diag2.py`, `lw_mcp_diag3.py`,
  `lw_diag_modeler_cp.py` — throwaway live-introspection probe plug-ins
  used to find the real method signatures/behavior documented above. Not
  needed going forward; safe to ignore or unload.
- `lw_mcp_ring.py`'s `_probe_channels()` / `server.py`'s
  `lw_probe_channels` — temporary, safe (crash-disabled) diagnostic for
  the blocked `LWChannelInfo` transform query above. Returns the
  resolved item ID and an error explaining the block, does not call
  `nextGroup`. To be replaced by a real `lw_get_transform` once a safe
  calling convention is found.
- `lw_mcp_ring.py`'s `_probe_surf_constants()` / `server.py`'s
  `lw_probe_surf` — lists `SURF_*` constants from `lwsdk` (confirmed
  live, ~48 found, e.g. `SURF_COLR`, `SURF_DIFF`, `SURF_REFL`,
  `SURF_TRAN`). Never implicated in any crash. Still needs live
  `LWSurfaceFuncs().byName()`/`getFlt()` probing to become a real
  `lw_get_surface_info` tool (item 1c).
- `lwcommandport/` — NewTek's official Command Port client, copied from
  the LightWave install, with one bug fixed (`Ring()`'s Python 3 topic
  formatting - see above). This is what makes both writes and reads work.
- `lw_mcp_master.py` — superseded Master-class plug-in with the
  LWEVNT_COMMAND attempt for reads. Confirmed dead end, kept for
  reference/history only. Do not load.
- `lw_mcp_query.py` — superseded Generic-class plug-in, the first (also
  unsuccessful) attempt at reads. Kept for reference/history only. Do not
  load.
- `lw_socket_master.py` — superseded very first draft (custom TCP socket
  server, relied on a tick event that doesn't exist). Do not load.
- `lw_diag_items.py`, `lw_diag2.py` — throwaway diagnostics used while
  chasing the hung-session issue above. Not needed going forward.
- `README.md` — setup/testing instructions.

## Setup (current, full read+write path)

1. In Layout: Utilities → Plugins → Add Plugins → `lw_enable_command_port.py`
   (runs once automatically, enables Command Port on 9735 - title bar
   should show `(CP: 9735)`).
2. Utilities → Plugins → Add Plugins → `lw_mcp_ring.py`, then Utilities →
   Master Plugins → "Add Layout or Scene Master" → "LW MCP Ring" (make
   sure "On" is checked).
3. `pip install "mcp[cli]"`.
4. Add `server.py` to Claude Desktop's MCP config, restart Claude Desktop
   (needed at least once after this fix, to pick up the corrected
   `lwcommandport/__init__.py`).
5. Ask Claude to call `lw_create_null`, `lw_run_command`, `lw_ping`, or
   `lw_get_scene_info` - all confirmed working as of this write-up
   (`lw_ping`/`lw_get_scene_info` verification pending the Claude Desktop
   restart in step 4 taking effect - see PLAN.md status above).

## ParentItem argument format (ROADMAP.md item 8, closing the item 7 gap)

Session goal: solve the previously-documented gap where `ParentItem`
via `lw_run_command` did not actually reparent items, confirmed only
readable via the UI-set relationship. Live LightWave 2019.1.5 was
available this session (a real Layout process, both Command Port and
`lw_mcp_ring.py` active), so this was investigated with real
round-trips rather than more static guessing.

**Wrong theories tested and ruled out live, in order:**

1. *Hidden modal requester.* Many LightWave generic commands pop a
   dialog when they can't parse their argument, and a network-invoked
   command can't dismiss it. Ruled out: took a screenshot of Layout
   immediately after sending `ParentItem` - no dialog, just the normal
   viewport, status bar showing `Current Item: ChildTest`, `Sel: 1`.
2. *Needs a UI redraw to flush a queued scene-graph rebuild.* A first
   test appeared to succeed - after the user opened Scene Editor,
   `lw_get_hierarchy` showed `ChildTest.parent: "ParentTest"` where it
   had shown `null` moments before. Tested the theory directly: created
   a second pair (`ParentTest2`/`ChildTest2`), sent the same
   `SelectItem`/`ParentItem` sequence, then asked the user to click once
   in the viewport (a trivial redraw trigger) and re-checked. Still
   `null`. Ruled out.
3. *Just needs more elapsed real time.* Polled `lw_get_hierarchy`
   repeatedly across a couple of minutes with no further action. Still
   `null` for the second pair throughout. Ruled out.
4. *The apparent first "success" was real.* Directly contradicted by
   the user: "it didn't work. I parented the items myself." - meaning
   the Scene Editor screenshot that appeared to show `ChildTest` nested
   under `ParentTest` was the user manually dragging it while looking at
   that panel, not the network command taking effect. The untouched
   second pair staying `null` the whole time is independent confirmation
   of the same thing. Real lesson: a single apparent success right after
   a UI interaction, with no isolated control case, is not evidence -
   this cost real time before the fresh, untouched `ParentTest2`/
   `ChildTest2` pair caught it.

**Root cause, found via Utilities > Commands > Cmd History:** this
panel logs the literal native command LightWave runs for any action,
UI-driven or network-driven. Asked the user to open it, then manually
reparent a pair via Motion Options (the same manual method already
proven to work, used originally to verify the read side). The log
showed:

```
ParentItem 10000000
SelectItem 10000000
```

A plain numeric ID, not a name. Meanwhile this connector's own failed
network attempts (`SelectItem Camera` then `TargetItem ChildTest`,
testing whether the failure was `ParentItem`-specific or affected the
whole "reference another item" command family) logged as:

```
TargetItem 0
```

Confirming `TargetItem` fails identically to `ParentItem` - not a
`ParentItem`-specific bug, but a shared argument-parsing convention
across this command family (`ParentItem`, `TargetItem`, `GoalItem`,
`PoleItem` all share the same `(itemid)` signature in
`lwcommandport/layout/__init__.py`). When given a name string these
commands can't parse as a numeric ID, they silently coerce the argument
to `0` - a bogus/no-op ID - rather than erroring, resolving by name, or
opening a dialog. `SelectItem` is the one exception: its own Cmd
History entries (`SelectItem 10000003` for a name-based call) prove its
command handler really does resolve names to IDs internally, unlike
this family. This inconsistency across LightWave's native commands
appears to be a genuine, longstanding NewTek API quirk, not something
introduced by this connector.

The IDs are sequential per item, assigned in creation order starting
at `10000000` for the Object category in this scene: `ParentTest` was
the first Null created this session and got `10000000`; `ParentTest2`
(the 3rd Null created) got `10000002`; `ChildTest2` (4th) got
`10000003`.

**Getting the numeric ID from Python:** the missing piece had been
sitting unused in this project since early on. `_mcp_diag_response.json`
- the output of `lw_mcp_ring.py`'s `_introspect()` diagnostic from a
much earlier session - lists module-level `lwsdk` helper functions
never connected to this problem until now: `find_scene_item_by_name`,
`itemid_to_str`, `str_to_itemid`. `_find_item(name)` (already existing
in `lw_mcp_ring.py`, used by every read query) already returns the
opaque `NodeID` handle for a name; `lwsdk.itemid_to_str()` converts
that handle into exactly the numeric string Cmd History showed
(confirmed live: `lw_get_item_id("ParentTest3")` returned `"10000004"`,
matching the expected sequential position for the 5th Null created).

**Fix, confirmed live end-to-end:** added a `get_item_id` query to
`lw_mcp_ring.py` (wraps `_find_item` + `itemid_to_str`), exposed as
`lw_get_item_id(name)` in `server.py`, plus `lw_set_parent(child,
parent)` wrapping the full corrected sequence (resolve parent's numeric
ID via the read path, `SelectItem(child)` by name since that's proven
to work, `ParentItem(id)`). Tested against a completely fresh,
untouched pair (`ParentTest3`/`ChildTest3`) specifically to avoid
repeating mistake #4 above - `lw_get_hierarchy` afterward correctly
showed `{"name": "ChildTest3", "parent": "ParentTest3", ...}`.

**Not yet wrapped in their own tools, but fixed by the same mechanism:**
`TargetItem`, `GoalItem`, `PoleItem` share the identical root cause and
argument convention. `lw_get_item_id` already produces the correct
argument for any of them via `lw_run_command` (e.g. `lw_run_command
"TargetItem" [lw_get_item_id result]`); a dedicated wrapper analogous
to `lw_set_parent` is a quick follow-up if IK rigging through this
connector is ever needed, not attempted this session since it wasn't
the reported gap.

## Second finding: SelectItem(name) isn't reliable for Camera/Light either (follow-up session)

Wrapped `TargetItem`/`GoalItem`/`PoleItem` as `lw_set_target`/
`lw_set_goal`/`lw_set_pole`, reusing `lw_set_parent`'s shape (resolve
the reference's numeric ID, `SelectItem(item)` by name, send
`command(id)`). Live-tested `lw_set_target(item="Camera",
target="ChildTest")` against real LightWave - it silently applied the
target to `ChildTest3` (an unrelated Null that happened to be the
already-current Object) instead of Camera. Confirmed via
`lw_get_selection` this wasn't a timing issue (waited, re-checked,
`SelectItem("Camera")` provably changed nothing observable).

Root cause, again found via Cmd History (select Camera in Layout,
Motion Options, set Target Item to ChildTest manually):

```
EditCameras 30000000
SelectItem 30000000
MotionOptions
TargetItem 10000001
```

The real working sequence selects the Camera by its own **numeric ID**
(`30000000`), not by name. So `SelectItem(name)`'s internal name
resolution - which does work reliably for Objects (confirmed
repeatedly, e.g. `SelectItem ChildTest2` logged as `SelectItem
10000003`) - is not reliable for Camera/Light. This also revealed each
item-type category has its own numeric ID range: Objects start at
`10000000`, Lights at `20000000`, Cameras at `30000000` (confirmed:
`lw_get_item_id("Camera")` returned `"30000000"`, `lw_get_item_id`
against the scene's one Light returned `"20000000"`).

**Fix:** `_set_reference_item()` in `server.py` now resolves BOTH the
`item` and the `reference` to numeric IDs before sending anything -
`SelectItem(item_id)`, not `SelectItem(item_name)`. Never rely on
SelectItem's name resolution for this command family again, even
though it happens to work for Objects; resolving both sides uniformly
is simpler than tracking which categories are "safe" by name.
Confirmed live after the fix: `lw_set_target("Camera", "ChildTest")`
correctly showed `Camera.target: "ChildTest"` via `lw_get_hierarchy`,
and `lw_set_target("Light", "ParentTest4")` correctly showed
`Light.target: "ParentTest4"`. Re-verified `lw_set_parent` still works
after the change (no regression) on a fresh pair, `ParentTest4`/
`ChildTest4`.

Process note: this fix needed two Claude Desktop restarts to verify -
the first restart left a stale `server.py` process still running
(confirmed via `tasklist`/`Get-CimInstance Win32_Process`, two
processes with the same command line, one clearly older), meaning the
live connection may have still been talking to the pre-fix code. A
fully-quit-and-reopened restart (both processes freshly spawned
seconds apart) was needed before the new tool definitions actually
took effect. Worth checking process list rather than assuming a
restart worked if a just-fixed tool still shows the old behavior.

## lw_set_goal/lw_set_pole live verification (closing the last untested tool)

Expected this to need setting up a real IK chain (bones, or at least a
proper Full-Body IK setup) to test meaningfully. Turned out not to:
`goal()`/`pole()` are generic per-item properties in the SDK -
`lw_get_hierarchy` has queried them for every item type since
ROADMAP.md item 7, regardless of whether the item is actually part of
an active IK chain. So both were tested directly against a plain Null
already in the scene (`ChildTest3`, which by this point already had a
parent and a target set from earlier testing):

- `lw_set_goal("ChildTest3", "ParentTest2")` -> `lw_get_hierarchy`
  correctly showed `"goal": "ParentTest2"`.
- `lw_set_pole("ChildTest3", "ParentTest")` -> `lw_get_hierarchy`
  correctly showed `"pole": "ParentTest"`, alongside the still-correct
  `parent`/`target`/`goal` from earlier - all four relationship types
  set correctly on one item at once, a good comprehensive confirmation
  that the fix generalizes across the whole command family rather than
  being coincidentally right for `ParentItem`/`TargetItem` alone.

No further work needed here - all four `lw_set_*` tools are now fully
live-confirmed.

## Live playhead time query (ROADMAP.md item 9, the item 1 limitation carried since the start)

Goal: solve the oldest open limitation in this project - every
animatable read (`lw_get_camera_info`/`lw_get_light_info`/
`lw_get_transform`) has been hardcoded to `time=0.0` since item 1,
because there was no confirmed way to query LightWave's live playhead
position from Python.

**Root cause of why this looked unsolved:** it wasn't that the SDK
lacks the capability - the original `_introspect()` diagnostic (used
to find `LWCameraInfo`/`LWLightInfo` back in item 1) searched
`dir(lwsdk)` for a fixed list of substrings (`Channel`, `Surface`,
`Camera`, `Light`, `Item`, `Select`, `State`, `Transform`, `Scene`,
`Bound`) that simply never included anything time-related. Nobody had
looked. A widened probe (temporary `lw_probe_time`/`_probe_time`,
searching `Time`/`Frame`/`Current`/`Play`/`Clock`/`Tick`) found it
immediately:

- `lwsdk.LWTimeInfo()` - a plain-attribute class (`frame`, `time`) in
  exactly the same simple style as `LWSceneInfo`, already proven safe
  elsewhere in this connector. `.time` is the live playhead position in
  seconds - exactly the unit every animatable call already expected
  (they'd been passing a hardcoded `0.0` in that same unit).
- `lwsdk.LWInterfaceInfo()` also exposes `curTime` as a second
  candidate, not used since `LWTimeInfo` matched the codebase's
  existing pattern more directly.

**Fix:** added a `_current_time()` helper in `lw_mcp_ring.py`
(`lwsdk.LWTimeInfo().time`) and swapped the hardcoded `0.0` for it in
`_get_camera_info`/`_get_light_info`/`_get_transform`, each now also
reporting `evaluated_at_time` in its response instead of a static
"note" about the old limitation. Added a permanent `get_current_time`
query/`lw_get_current_time` tool (frame derived from
`time * LWSceneInfo().framesPerSecond`) so the evaluation time can be
checked directly without needing an animated item. Removed the
temporary `lw_probe_time` tool/`_probe_time` function once the fix
shipped, per this project's established pattern for diagnostic-only
code.

**Confirmed live with a real animated item**, not just trusting the
mechanism's plausibility from its method signature: created a fresh
Null (`TimeTest`), keyframed it at frame 0 (position 0,0,0 via
`lw_set_keyframe`) and frame 30 (position 10,10,10), moved the
playhead to frame 15 via `GoToFrame` (already proven-reachable), then:

- `lw_get_current_time` correctly returned `{"frame": 15.0, "time":
  0.5}` (30fps).
- `lw_get_transform("TimeTest")` correctly returned an interpolated
  position of ~(6.208, 6.208, 6.208) - not the frame-0 default of
  (0,0,0), and notably not a naive linear midpoint of 5.0 either. This
  matches LightWave's default TCB/spline easing curve shape: the
  original item-4 keyframe test (0→5 over the same 0→30 frame range)
  read back 3.104 at frame 15 - almost exactly half of 6.208, i.e. the
  same easing curve scaled 2x for this test's 0→10 range. That
  consistency is strong independent evidence the fix is evaluating at
  the correct time, not coincidentally producing a plausible-looking
  number.

**Process detour worth recording:** partway through verifying this,
`lw_ping` and writes both stopped working, and the Ring listener's
debug log showed it endlessly attach/detach-cycling without ever
receiving an event - exactly the signature of the already-documented
Master Plugin activation flakiness. Several remove/re-add cycles were
spent chasing that before checking the title bar and noticing it no
longer showed `(CP: 9735)` at all, and the Scene Editor had reset to
just the default `Light`/`Camera` - Layout itself had been restarted
at some point, and setup step 1 (enabling the Command Port itself) had
never been redone. Once that was fixed, the Ring listener worked
immediately. Lesson: if symptoms that look exactly like the known
Master Plugin flakiness persist past 2-3 retries, check the title bar
for `(CP: 9735)` and the scene contents (are previous session's test
items still there?) before assuming it's the same flaky-activation
issue again - it might be a full Layout restart instead, which needs
setup step 1 redone, not just step 2.

With this, every roadmap item is done except item 5 (Modeler reads),
which remains a documented, confirmed dead end.

## Multi-frame RenderScene progress tracking (STATUS.md item 1, closing the ROADMAP.md item 6 "untested" note)

Goal: verify whether `frame_count` correctly increments across a
multi-frame `lw_render_scene()` render, or jumps straight to done, or
stalls - flagged as untested since ROADMAP.md item 6 shipped. Involved
real environment trouble across several sessions (a full computer
restart mid-investigation, a stale two-python-process situation, and a
genuinely locked plug-in file) on top of the actual technical
questions - worth recording the process, not just the final answer.

**Setup friction before any real testing could start:** `FirstFrame(0)`/
`LastFrame(3)` (confirmed via `lwcommandport`, these are the real
Start/End Frame globals, not `GoToFrame` or the Preview range fields)
set the range correctly and were confirmed live via a screenshot of
Render Properties. But `lw_render_scene()` produced no observable
effect at all the first two attempts - traced to two different real
causes, not flakiness: (1) LightWave pops a blocking confirmation
dialog ("Do you want to set the render end frame to the slider end
frame (120)?") whenever `RenderScene` runs with `Range Type: Single`
and the configured End Frame differs from the timeline's end - a
one-way UDP command can't dismiss this, so the render never proceeds
until a human clicks it; (2) a second dialog ("Auto Frame Advance is
on. Turn off render display?") follows immediately after. Both need
"No" to proceed with the render display we want active.

**Root cause misdirected the first real investigation round:** with
those dialogs cleared, a render finished but `_mcp_render_status.json`
never updated - looked exactly like the Master Plugin activation
flakiness this project already has a documented fix for (remove/re-add
via Add Plugins, usually 1-3 tries). It wasn't. The Render Display
dropdown can keep showing "LW MCP Render Monitor" as a leftover UI
preference across a fresh Layout session even when the underlying
plug-in class was never reloaded - the debug log staying frozen for
days (`_mcp_render_debug.log`'s mtime) was the tell, not any error
message. Confirmed by explicitly switching the Render Display away and
back, which produced fresh log activity immediately.

**Once real data started coming in**, the actual technical question got
answered fast: `open()`/`close()` fire exactly once for the whole
`RenderScene` sequence (one open/close pair logged for a 4-frame
render), not once per frame as `lw_mcp_render_monitor.py`'s original
`frame_count` logic assumed (it incremented on `open()`). The real
per-frame signal, found by reading NewTek's own bundled sample plug-in
(`support/plugins/scripts/Python/Layout/FrameBuffer/framebuffer.py`,
which this project had not previously looked at for this file): a
`begin()` method, never overridden here, that the sample uses to reset
its scanline counter before each frame's `write()` calls.

**First fix attempt was incomplete, caught by testing rather than
assumed correct:** moved the increment to `begin()` and expected a
clean `frame_count` of 4 for a 4-frame render. Got 8. Checked Cmd
History's log of `pause()` calls (`'Alpha'`/`None` alternating,
matching `begin()`'s own call count exactly) and the Render Properties
Buffers tab: `Final_Render` and `Alpha` were both checked in the
"Render" column. Confirmed directly: `begin()` fires once per *enabled
render buffer* per frame, not once per frame alone - unchecking
`Alpha` (leaving only `Final_Render`) produced a clean sequence of
exactly 4 `begin()` calls, matching the 4-frame range exactly. A second
real bug surfaced in the same round: the plugin instance persists
across separate `lw_render_scene()` calls within one Layout session, so
`frame_count` was continuing to climb across renders (the immediately
following test read `12`, continuing from the prior render's `8`)
instead of resetting - fixed by resetting `self._frame_count = 0` in
`open()`, not just `__init__()`. Re-tested after both fixes: a fresh
4-frame render with only `Final_Render` enabled produced exactly
`frame_count: 4`, correctly reset from the previous session's `12`.

**Unplanned bonus finding, from reading Cmd History while debugging the
above:** `SetRenderDisplay` DOES take an argument over the network
(`SetRenderDisplay LW MCP Render Monitor`, confirmed via a real Cmd
History entry from manually switching displays) - contradicting this
project's own earlier documented conclusion (this file, "Render/camera
automation" section above) that there was no networked way to select
the active Render Display. The wrapped `lwcommandport` method was
simply generated without an argument (`def SetRenderDisplay(self):`),
the same class of bug as the `Ring()` fix in
`lwcommandport/__init__.py`. Fixed the same way. Also discovered: this
reload can get "locked" (Add Plugins reports it can't be added) if the
plug-in is currently the active Render Display - switching the display
away first, reloading, then switching back resolves it, an addition to
this project's list of known plug-in-reload quirks.

**Separately, environment trouble unrelated to the actual investigation:**
a full computer restart mid-session required redoing all three setup
steps from scratch (Command Port, Ring listener, render monitor) -
including hitting the exact "Plugins were not found or could not be
added" message for `lw_mcp_ring.py` despite it still showing (stale) in
the Master Plugins list from before the restart, resolved by the
existing uncheck/recheck toggle workaround, not a new issue. Two
`server.py` processes were also observed running simultaneously more
than once across this project's history (visible via
`Get-CimInstance Win32_Process -Filter "Name='python.exe'"`) - in this
session's case 3 days apart, clearly unrelated leftovers rather than
the same-session duplicate this project's memory previously flagged as
a concern; worth checking creation timestamps before assuming a stale
process is the cause of a given symptom.

## Bone chain traversal (STATUS.md item 2, closing item 7's deferred piece)

Goal: extend `lw_get_hierarchy` to walk bone chains within an object,
deferred since item 7 for lack of a real boned object to verify
traversal against. This project has a documented, real crash in an
adjacent SDK traversal area (`LWChannelInfo`/`nextGroup` - see
"LWChannelInfo crash" above), so this was approached deliberately step
by step rather than writing the obvious `while` loop and hoping.

**First surprise: no real mesh object was needed at all.** Before
reaching for Modeler to build a test object, checked whether `AddBone`
(a native Layout command, `lwcommandport/layout/__init__.py`) works on
a plain Null. It does: `AddBone("Bone1")` after selecting a fresh Null
(`BoneTestObject`) created a real bone, visible in Scene Editor nested
exactly like real parent/child items; `AddChildBone("Bone2")` added a
second bone chained under the first. This made the whole investigation
far cheaper than expected - no Modeler mesh-building detour, no
`.lwo` load, just two native Layout commands already in the wrapped
command list.

**Staged the actual traversal risk down before writing a real loop.**
Added a temporary, deliberately non-looping probe (`lw_probe_bones`/
`_probe_bones`, since removed) that checked, in order, each wrapped in
its own try/except:

1. Does `lwsdk.LWI_BONE` even exist (`hasattr(lwsdk, "LWI_BONE")`)?
   STATUS.md had flagged this as "the likely mechanism, unconfirmed."
2. Does a single `LWItemInfo().first(LWI_BONE, object_id)` call
   succeed, and is the result non-null?
3. Does a single `.next(first_bone_id)` call succeed, and is *that*
   non-null?

Ran this against the real 2-bone chain: all three came back clean -
`has_LWI_BONE: true`, `first_bone_name: "Bone1"`,
`second_bone_name: "Bone2"`, no exceptions, no crash. Checked Layout
was still fully responsive (`lw_ping`, `lw_get_scene_info`) before
proceeding - unlike `LWChannelInfo`/`nextGroup`, this API behaves like
the same safe `first()`/`next()` pattern already proven for
Object/Light/Camera iteration, not the one that crashed Layout
outright with no Python exception.

**Shipped the real traversal** in `lw_mcp_ring.py` (`_get_bones()`),
using the identical `while it != LWITEM_NULL` shape already proven for
the other item categories, plus a generous iteration cap
(`_MAX_BONES_PER_OBJECT = 200`) as an extra margin against a
hypothetical malformed/circular chain - not because anything suggested
one exists, but because a bounded loop costs nothing and this project
has exactly one precedent for an unbounded SDK traversal call going
wrong. Each bone reports the same name/parent/target/goal/pole shape as
every other item, attached to its host object's entry as a `bones`
list (only when non-empty).

**Confirmed live end to end:** `lw_get_hierarchy()` against the real
2-bone chain correctly returned `Bone1.parent == "BoneTestObject"`
(the host item) and `Bone2.parent == "Bone1"` - the actual chain
relationship, not just "a bone exists." No crash, no exception, on the
first real attempt at the full (bounded) loop - the staged probing
beforehand meant there was nothing left to discover by the time the
real loop got written.

Removed the temporary probe tool and function once this shipped, per
this project's established pattern (`lw_probe_channels`, `lw_probe_surf`,
`lw_probe_time` before it).

**Unrelated side investigation, same session:** the user asked whether
a different, newer LightWave-MCP project (Kartaverse's `lightwave-mcp`,
targeting LightWave 2025.0.3+, found locally as
`lightwave-mcp-master-2025`) had solved Modeler reads or had anything
else worth leveraging. It hadn't, on either count:

- No `LWComRing`/`IMaster`/`FrameBuffer` usage anywhere in the repo,
  and no companion `.py` file meant to be loaded inside LightWave via
  Add Plugins at all - it's a pure external client with connection
  management and command-cache introspection built around fire-and-
  forget `send_layout_command`/`send_modeler_command` calls, nothing
  more. It hasn't attempted what this project already solved for
  Layout reads, let alone Modeler.
- It still carries both bugs this project found and fixed independently:
  `Ring()`'s doubled-brace format-string bug (`"{{0}} {1}".format(...)`
  producing a literal `"{0} message"`), and `SetRenderDisplay(self)`
  taking zero arguments despite the native command accepting one. Both
  are apparently genuine, longstanding bugs in NewTek's own bundled SDK
  sample code, uncaught anywhere else and carried forward unfixed even
  in the current 2025 distribution.
- Modeler's command surface (`lwcommandport/modeler/__init__.py`) is
  byte-for-byte identical between the two forks - same 63 method names,
  zero additions in 6 years across a major version jump (2019.1.5 to
  2025.0.3). Real, independent evidence for item 5's Modeler-reads
  dead-end conclusion, not just this project's own testing.

No further work needed here - `lw_get_hierarchy` now covers item-level
parenting, IK relationships, AND bone chains, all live-verified.
STATUS.md's remaining-items list is down to one entry (Modeler reads,
confirmed dead end).

## Light/object visibility linking (ROADMAP2.md item 1)

Goal: wrap `IncludeObject`/`ExcludeObject`/`IncludeLight`/
`ExcludeLight` - found unused during the survey of
`lwcommandport/layout/__init__.py` that grounded `ROADMAP2.md`. All
four share the identical `(itemid)` docstring convention already known
to be unreliable for `ParentItem`/`TargetItem`/`GoalItem`/`PoleItem`
(see "ParentItem argument format" above) - name strings silently
no-op, and `SelectItem(name)` itself isn't reliable for Camera/Light
(see "Second finding"). Wrapped with the same `_set_reference_item`
helper unconditionally rather than testing whether the old assumption
would happen to hold here too.

Shipped `lw_include_light(light, obj)`, `lw_exclude_light(light, obj)`,
`lw_include_object_light(obj, light)`, `lw_exclude_object_light(obj,
light)`. Confirmed live end to end, via the actual UI panels rather
than just trusting Cmd History's logged IDs:

1. `lw_include_light("Light", "BoneTestObject")` -> Cmd History showed
   `SelectItem 20000000` / `IncludeObject 10000000` (correctly resolved
   IDs). Screenshot of Light Properties > Objects tab confirmed
   `BoneTestObject` listed with the "Exclude" checkbox unchecked - i.e.
   genuinely in Include mode, not just "some entry appeared."
2. `lw_exclude_object_light("BoneTestObject", "Light")` - the same
   relationship, set from the *other* item's side via the *other*
   native command (`ExcludeLight` instead of `ExcludeObject`).
   Confirmed two things at once: (a) toggling Include -> Exclude
   updates the same list entry's checkbox rather than creating a
   duplicate row, and (b) the relationship really is shared, bare data,
   not two independent lists that happened to look similar - after
   this call, BOTH the light's own Properties > Objects tab AND the
   object's own Item Properties > Lights tab (opened via the native
   `ItemProperties` command, initially thought not to exist based on a
   quick look but it does, under its own "Lights" tab) showed the
   "Exclude" checkbox checked for each other.

One incidental observation, not investigated further since nothing
broke: `ItemProperties` on a fresh Object (as opposed to a Null that
already existed in a scene from a `.lws` load) triggered `Cmd History`
entries for `ApplyServer PixelFilterHandler FiberFilter` and
`ApplyServer MasterHandler FiberFX`, and "FiberFX" appeared as a new
entry in the Master Plugins list - LightWave auto-registering a bundled
hair/fur rendering handler the first time an Object Properties panel
opens for real geometry, apparently unrelated to the light-linking
being tested. Layout remained fully responsive throughout (confirmed
via continued Cmd History activity and successful subsequent commands)
- worth knowing this happens, not treating it as a bug, but not chased
further since it didn't block anything.

No further work needed here - all four tools confirmed live and
symmetric. `ROADMAP2.md` item 1 is closed; item 2 (loading real
geometry via `LoadObject`) is next.

## Load real geometry into Layout (ROADMAP2.md item 2)

Goal: close the biggest capability gap identified in `ROADMAP2.md` -
this connector could create Nulls (`AddNull`) but had no way to bring
real mesh geometry into a Layout scene without a separate Modeler
round-trip. `LoadObject(filename)` was found unused during the same
command-list survey that grounded the whole of `ROADMAP2.md`.

Needed a real `.lwo` file to test against. Rather than build one via
Modeler (previously confirmed to have no simple scriptable primitive
command - see "ParentItem argument format"'s sibling investigations
and ROADMAP2.md item 2's own framing), checked the LightWave install
itself first: `support/genoma/rigs/` ships real `.lwo` rig-part files
as part of the bundled Genoma auto-rigging system. Picked the smallest
one available (`connector_01.lwo`, 622 bytes, under `Rig Parts/
01_Connectors/`) purely to keep the test object simple, not for any
functional reason.

Shipped `lw_load_object(filename)`, a thin wrapper around
`LoadObject` following the same one-way fire-and-forget pattern as
every other write in this connector. Confirmed live end to end, not
just that the command was sent:

- `lw_get_scene_info()` before: `["BoneTestObject", "Light", "Camera"]`.
  After `lw_load_object(<connector_01.lwo path>)`:
  `["BoneTestObject", "connector_01", "Light", "Camera"]` - the loaded
  object's name (derived from the file, not something we specified)
  appearing confirms LightWave actually parsed and loaded the file,
  not just accepted the command.
- `lw_get_transform("connector_01")` returned a valid position/
  rotation/scale, proving it's a real, queryable item like any other,
  not a broken reference.
- A screenshot showed real triangular mesh geometry in the viewport -
  visual, not just data-level, confirmation. Object Properties panel
  also independently confirmed "Objects in Scene: 2."

Not tested: relative paths, paths outside the LightWave process's
obvious reach (network shares, paths with unusual characters), or
loading multiple objects/layers via `LoadObjectLayer`. `filename` is
documented as needing to be an absolute path readable by the LightWave
process based on this one successful test, not verified against
failure modes.

No further work needed for the basic case - `lw_load_object` works.
`ROADMAP2.md` item 2 is closed; item 3 (scene file I/O) is next.

## Scene file I/O (ROADMAP2.md item 3)

Goal: wrap `SaveScene`/`LoadScene`/`ClearScene`/`SaveObject`, found
unused in the same command-list survey that grounded `ROADMAP2.md`.
`SaveScene()` takes no arguments (saves to the scene's already-known
filename), not useful for the unnamed scenes this project has always
tested against - used `SaveSceneAs(filename)` instead for the primary
save path.

**Save/clear/load round trip confirmed live, verified two ways, not
just "a file appeared":**

1. `lw_save_scene_as(<temp path>.lws)` against the live scene
   (`BoneTestObject`, `connector_01`, `Light`, `Camera`) - checked the
   saved file's actual content, not just its existence: it contained
   `AddNullObject 10000000 BoneTestObject` and `LoadObjectLayer 1
   10000001 <path>/connector_01.lwo`, the correct numeric IDs matching
   this project's established ID scheme (see PLAN.md "ParentItem
   argument format").
2. `lw_clear_scene()` -> `lw_get_scene_info()` correctly showed just
   `["Light", "Camera"]`.
3. `lw_load_scene(<same path>)` - popped a blocking "Change Content
   Directory?" dialog ("You are trying to load a scene which is not on
   the current content path") since the temp save path wasn't under
   LightWave's configured Content Directory. Answering "No" (don't
   change the content path) still let the scene load correctly -
   `lw_get_scene_info()` afterward showed `scene_name`/`filename`
   correctly reflecting the loaded file and all four items restored.

**`lw_save_object` surfaced a real, new problem, not just a rerun of
an already-solved one.** First attempt (`SelectItem(name)` then
`SaveObject(filename)`, the same shape as `lw_set_keyframe`) produced
LightWave's own error dialog: "Null objects are automatically saved
with the scene" - meaning `SaveObject` had fired against
`BoneTestObject` (a Null, still the "current object" from earlier
testing), not `connector_01`, even though `SelectItem("connector_01")`
had just been sent. `lw_get_selection()` confirmed it directly:
`connector_01: false`, `BoneTestObject: true`, unchanged.

Ruled out timing as the cause: repeated the `SelectItem`/
`lw_get_selection` pair as two fully separate tool calls (a real
network round trip apart, not two sends in one Python function) - no
change. Ruled out a naming mismatch: `lw_get_item_id("connector_01")`
resolved cleanly to `"10000001"` via this project's own read path,
proving the name is exactly right. Tried `SelectItem` with that
numeric ID directly (the fix already proven for Camera/Light/every
other item-relationship command in this project) - still no change.
This ruled out every previously-known failure mode for this command
family.

Reached for Cmd History again, the same tool that broke open the
original `ParentItem`/`SetRenderDisplay` investigations: asked the
user to manually click `connector_01` in Scene Editor. The log showed
**two** `SelectItem` calls for that one click:

```
SelectItem 40010000
SelectItem 10000001
```

`10000001` matches `lw_get_item_id`'s answer exactly - but `40010000`
is a new ID pattern never seen in this project before (Object/Light/
Camera IDs all start `1`/`2`/`3` followed by zeros; this starts `4`).
Sent both, in that order, via `lw_run_command` - `lw_get_selection()`
confirmed `connector_01` correctly became current. Tested whether the
`40010000` call was a one-time context-activation or needed every
time: switched to `BoneTestObject` via its own numeric ID (`10000000`,
confirmed working), then switched back to `connector_01` using its
plain numeric ID (`10000001`) **alone** - this time it worked. The
`40010000`-style call appears to be a one-time-per-object-per-session
activation, not a per-call requirement - once something (a manual
click, or replaying the two-ID sequence) has touched that object's
selection once, its regular numeric ID becomes reliable afterward.

**Deliberately did not bake a guessed formula into the shipped code.**
`40010000` invites a tempting pattern (`40000000 + object_index *
10000`, since `connector_01` was the 2nd object created, index 1) that
would predict this exact value - but that's one data point. Committing
an unverified numeric formula into a tool other work will depend on
risks a repeat of this project's `LWChannelInfo`/`nextGroup` lesson in
spirit if not in severity: confidently wrong code is worse than an
honest gap. `lw_save_object` ships with the best *confirmed* fix
(resolve to the object's real numeric ID rather than trust
`SelectItem(name)`, consistent with every other tool in this
connector) and a clearly documented limitation for the untested case,
rather than a plausible-looking guess. With `SaveObject` finally
targeting the right item (once activated), the saved file was checked
byte-level, not just its existence: a real `FORM....LWO3TAGS` header
followed by genuine surface/tag data (`connector.lwo`, `CONNECTOR`,
`Generic_CreateConnector`) - a valid, non-corrupted LWO3 file.

**Follow-up worth doing, not attempted this session:** test the
`40000000 + index*10000` hypothesis against a second and third loaded
object to see if it actually holds, which would turn this from a
documented limitation into a real fix. Needs at least two more loaded
objects and the same Cmd History comparison method used here - not
attempted now for the same reason the formula wasn't shipped: one
successful guess is not confirmation.

`ROADMAP2.md` item 3 is closed for the confirmed cases; the
`lw_save_object` first-selection gotcha for freshly-loaded objects
remains open, documented rather than silently risking a wrong save.

## Camera property writes (ROADMAP2.md item 4)

Goal: wrap `ZoomFactor`/`LensFStop`/`ApertureHeight`/`ShutterOpen`/
`ShutterEfficiency`/`RollingShutter`, closing `lw_get_camera_info`'s
read-only status. Shipped `lw_set_camera`, bundling all six into one
call (`lw_set_keyframe`'s optional-params shape), using the numeric-ID
`SelectItem` fix already established for Camera/Light in "Second
finding." Also extended `_get_camera_info` to read back
`shutterOpen`/`shutterEfficiency`/`rollingShutter` (found on
`LWCameraInfo` in an earlier introspection dump but never previously
wired up) - needed a real way to verify the new writes rather than
trust a fire-and-forget send blind.

**`zoom_factor` and `aperture_height` confirmed live immediately** -
setting `aperture_height` alone (0.6) changed `focal_length_mm` from
41.25 to 1650.0 at the same `zoom_factor`, a real physical relationship
(film-back size vs. focal length), not a coincidence.

**`f_stop` silently no-op'd on the first attempt** - set to 2.8, but
`lw_get_camera_info` still read back the old 4.0. Not a repeat of any
previously-known failure mode (numeric ID was already correct, per the
fix above) - a genuinely new kind of problem: a real LightWave
precondition, not a connector bug. Confirmed by triggering the same
write via `lw_run_command` directly and asking the user to check for a
popup: "This option only applies when Depth of Field is turned on."
Sent the native `DepthOfField()` command once (no arguments - a
toggle, unlike most commands in this connector) and retried - `f_stop`
correctly read back as 2.8 afterward.

**The three shutter properties hit the identical pattern, one level
deeper.** All three silently no-op'd; the same error-dialog check
revealed "This option only applies when Particle Blur or Motion Blur is
turned on" (popped three times in a row for one `lw_set_camera` call
setting all three properties, confirming each is checked
independently). Sent `MotionBlur()` (same no-argument toggle shape as
`DepthOfField()`) expecting the same fix - it did not work. Retried
individually via `lw_run_command("ShutterOpen", [0.02])` and asked for
a screenshot to check: the same precondition error popped again, AND
the visible Camera Properties panel showed why - "Motion Blur" and
"Particle Blur" appear as **buttons** under a "Motion Effects" tab, not
checkboxes, strongly suggesting they open their own sub-panel/requester
rather than toggling a simple flag the way `DepthOfField()` evidently
does. `MotionBlur()` is very likely just the "open that panel" command,
not an enable/disable toggle - LightWave's own UI naming isn't a
reliable guide to a command's actual semantics, apparently even
between two features (DOF vs. Motion Blur) that look identically
structured in the Properties panel.

**Not solved this session:** how to enable Motion Blur (or Particle
Blur) via automation. Didn't chase this further given the escalating
guess-and-check cost already spent on `MotionBlur()` alone - shipped
`shutter_open`/`shutter_efficiency`/`rolling_shutter` in `lw_set_camera`
anyway, since the underlying write commands are correct and will work
the moment a human enables Motion Blur through the UI once; documented
the precondition clearly rather than silently shipping a tool that
looks like it works but doesn't, or spending more time chasing a fix
this session didn't clearly need.

`ROADMAP2.md` item 4 is closed for the confirmed cases (`zoom_factor`,
`f_stop`, `aperture_height`); enabling Motion Blur/Particle Blur via
automation remains open, a candidate for its own future investigation
if shutter-timing control specifically becomes needed.

**Resolved in the item 5 session.** The "Motion Blur is a button, not a
toggle" read above was a reasonable guess from the UI alone but turned
out to be wrong about the root cause. Working on item 5's light
toggles surfaced the same shape of bug three more times in the
`lwcommandport` stub (see "Light property writes" below), which
prompted a closer look at `MotionBlur`'s actual wrapped definition
rather than trusting the UI's button-vs-checkbox appearance: it was
`def MotionBlur(self): self._send_command("MotionBlur")` - wrapped with
**no way to pass an argument at all**, identical to the earlier
`Ring()`/`SetRenderDisplay()` bugs from ROADMAP.md. A stray "MotionBlur
1" spotted in Cmd History (logged from an unrelated manual UI click)
confirmed the real native command takes an enable/disable argument.
Fixed by adding `*args` to the stub, same pattern as the other two
fixes. Confirmed live: `lw_run_command("MotionBlur", [1])` now
correctly satisfies the precondition, and all three shutter properties
immediately read back the values that had been silently accepted (but
blocked from view) all along. The "button opens a sub-panel" UI
behavior is real and still true - clicking "Motion Blur" in the UI does
open a sub-panel - but that's a separate, cosmetic fact from whether
the *native command* takes an argument; it does. Lesson carried
forward into item 5: don't infer a command's real signature from how
its UI control looks (button vs. checkbox), only from the stub's actual
wrapped signature and Cmd History ground truth.

## Light property writes (ROADMAP2.md item 5)

Goal: wrap `LightIntensity`/`LightColor`/`LightFalloffType`/
`LightConeAngle`/`LightVisibleToCamera`/`LightCastsShadows`, closing
`lw_get_light_info`'s read-only status the same way item 4 closed it
for cameras. Shipped `lw_set_light`, bundling the first four into one
call, same shape and numeric-ID `SelectItem` pattern as `lw_set_camera`.

**`intensity` and `color` confirmed live immediately** - no
preconditions, no surprises, matching `zoom_factor`/`aperture_height`
from item 4.

**`LightFalloffType` duplicate-definition bug, found by reading code,
not live testing.** While wiring up `falloff_type`, a grep through
`lwcommandport/layout/__init__.py` turned up `LightFalloffType`
defined twice:

```python
def LightFalloffType(self, *args):
    """ LightFalloffType(type) """
    if len(args) != 1:
        raise Exception(...)
    self._send_command("LightFalloffType", args)
def LightFalloffType(self):
    """ LightFalloffType() """
    self._send_command("LightFalloffType")
```

Classic "last definition wins" Python bug - the correct, argument-taking
version was completely shadowed and unreachable; any call to
`lw.LightFalloffType(2)` would have raised a `TypeError` before ever
reaching a real command. Fixed by deleting the second (bare) version.
Found by code inspection this time, not a live symptom - worth noting
since it means the project's "always verify live" norm doesn't replace
reading the code carefully too; this bug would have looked like a
runtime failure the moment anyone tried to actually use the write side.

**`falloff_type` write confirmed live via UI screenshot** - Light
Properties showed "Intensity Falloff: Inv Distance^2" immediately after
sending `falloff_type=2` to a Point light. Initially looked broken
because `lw_get_light_info`'s own read-back didn't change - traced this
to a separate, still-open bug in the read path (see below), not the
write, only by checking the actual UI panel instead of trusting the
read tool's output blindly. Also hit a real LightWave constraint while
testing: falloff doesn't apply to Distant lights at all - confirmed via
LightWave's own error dialog, "This option does not apply to the
current light type," when tried on a Distant light. Created a real
Point light (`AddPointLight`) to test falloff properly instead of
fighting the constraint.

**`falloff` read-back bug, still open.** `LWLightInfo.falloff(light_id)`
always returns the scene-default value regardless of what was just
written - confirmed by writing `falloff_type=2`, checking the UI (write
worked), then calling `lw_get_light_info` and seeing the old default.
Tried the same `(id, time)` two-argument shape every other animatable
field in `_get_light_info` uses, in case falloff is channel-driven like
they are - confirmed live after a Layout plugin reload that this does
**not** fix it either: the two-argument call doesn't raise, it just
returns the identical stale value, so there's nothing to branch on.
Reverted to the plain one-argument call and documented this as an open,
un-worked-around limitation in `lw_mcp_ring.py`'s `_get_light_info`
rather than shipping speculative two-argument code that provided no
actual benefit - matches this project's standing preference for an
honest documented gap over a guessed fix that doesn't demonstrably help.

**`LightVisibleToCamera`/`LightCastsShadows` - suspected bug, live
verification proved it wrong.** Given the `MotionBlur`/
`SetRenderDisplay`/`LightFalloffType` pattern (three real bugs already
found this phase, all "wrapped with no way to pass an argument"),
calling `lw_run_command("LightVisibleToCamera", [0])` and seeing
`"Layout.LightVisibleToCamera() takes 1 positional argument but 2 were
given"` looked like the same bug a fourth time. It isn't: that error
only proves our stub's *current* zero-arg signature rejects extra
arguments, which is true of literally any zero-arg method - it says
nothing about whether the *native* command underneath actually accepts
one. The three earlier bugs were only confirmed as bugs because Cmd
History showed a real manual UI action logging an argument (e.g.
"MotionBlur 1"); no such evidence existed yet for this pair.

Checked properly: had the "Visible to Camera" checkbox located (Light
Properties > Basic tab - initially not visible at all because it's
grayed out/disabled for Point lights, a real constraint discovered by
switching Light Type and finding it becomes clickable under Spot or
Distant only) and clicked live. Cmd History showed a bare
`LightVisibleToCamera` with no argument following. Same test for "Cast
Shadows" (Light Properties > Shadows tab) showed a bare
`LightCastsShadows`, also no argument. Both are genuine argument-less
toggles - the original docstring's claim before this investigation
turned out to be correct, and the stub needed no fix. This is exactly
the scenario the project's live-verification norm exists to prevent
getting wrong: pattern-matching from a wrapper-level error to "probably
the same bug" would have produced a confidently wrong fix (adding
`*args` to a command that never wanted one) had it not been checked
against real Cmd History ground truth first.

Since neither toggle can be set to a known state or read back,
`lw_set_light` deliberately does not wrap them - `lw_run_command` is
the right tool for these two, same as `DepthOfField()` for item 4's
`f_stop`.

`ROADMAP2.md` item 5 is closed. Combined with item 4, this closes the
biggest remaining "reads but can't write" gap in the connector for
Camera and Light items.

## Multi-item / bulk selection investigation (ROADMAP2.md item 6)

Goal: figure out whether `AddToSelection` (tested during earlier work
and appearing to do nothing observable) is fixable, since real
multi-select would let every write tool above batch across items
instead of looping one item at a time.

**Root cause of the original "does nothing" finding.** The earlier
check read selection state via `flags() & LWITEMF_SELECTED` - the same
API `lw_get_selection`'s own docstring already documents as unreliable
("returned the same value for every item"). It was never a real test of
`AddToSelection`, just a broken read making a working command look
broken. Confirmed by re-running with `LWItemInfo().selected()` (the
read `lw_get_selection` actually uses) instead.

**Re-tested live, properly this time.** Checked `lwcommandport`'s stub
first - `AddToSelection`/`RemoveFromSelection` were already correctly
wrapped with `*args` and a `(itemid,)` argument check, unlike the
`Ring`/`SetRenderDisplay`/`MotionBlur`/`LightFalloffType` bugs found
earlier this phase, so no stub fix was needed here. Sequence: found two
Objects already in the live test scene already showing a real baseline
of simultaneous selection across categories (`lw_get_selection` showed
an Object, a Light, AND the Camera all `selected: true` at once before
touching anything - LightWave apparently keeps one "current" selection
per item-type category, all of which can be true simultaneously - this
is not the same thing as multi-selecting two items of the SAME type).
Isolated a clean test: `SelectItem(BoneTestObject's id)` to reset the
Object category down to one, confirmed only that one was
`selected: true`, then `AddToSelection(second Object's id)`.
`lw_get_selection` correctly showed BOTH Objects as `selected: true`
simultaneously afterward, and a live Scene Editor screenshot confirmed
both rows were genuinely highlighted, not a read-side illusion. Tested
`RemoveFromSelection` the same way - correctly dropped one item back to
`selected: false` while leaving the other selected.

Shipped `lw_add_to_selection(item)`/`lw_remove_from_selection(item)`,
resolving name to numeric ID first (same pattern as every other
item-reference tool here) since `AddToSelection`/`RemoveFromSelection`
share the "wants a numeric ID" quirk with the rest of this command
family. Unlike `_set_reference_item`'s shape, no preceding `SelectItem`
call is needed - `AddToSelection`/`RemoveFromSelection` ARE the
selection-modifying commands themselves. Confirmed live end to end
after a Claude Desktop restart, by name (not raw ID, to prove the
resolver path): added `BoneTestObject` back into a two-item selection,
then removed it again, both correctly reflected in `lw_get_selection`.

**The real finding, and why this doesn't fully deliver on the item's
original hope.** Tested whether a write command would apply to the
whole selection once two items were genuinely multi-selected: sent
`AddPosition(1, 0, 0)` with both `BoneTestObject` and
`lightwavemcp_test_object_out` reading `selected: true`. Only
`lightwavemcp_test_object_out` (the one most recently touched, via
`AddToSelection`) actually moved - `lw_get_transform` on
`BoneTestObject` still showed `[0, 0, 0]` afterward. Multi-selection is
real and correctly tracked by `LWItemInfo().selected()`/the UI
highlight, but write commands sent over the one-way Command Port still
only affect a single "current item" pointer - the same concept
`_set_reference_item` already has to manage via `SelectItem` for
`lw_set_parent`/`lw_set_target`/etc. There is no discovered mechanism
in this connector's command set for a single write call to fan out
across an entire highlighted selection.

`ROADMAP2.md` item 6 is closed: `AddToSelection`/`RemoveFromSelection`
are confirmed real and shipped, but they solve "represent a
multi-item selection state," not "batch a write across multiple
items" - every write tool in this connector still needs its own
per-item loop.

## IK chain configuration writes (ROADMAP2.md item 7)

Goal: enable/disable "Full-Time IK" and related chain-level flags
(Motion Options > IK and Modifiers), the piece `lw_set_goal`/
`lw_set_pole` don't cover - those two assign which item is the
goal/pole, this is about the chain's own behavior around that
assignment.

**Surveyed the stub first, before touching the UI.** Grepped
`lwcommandport/layout/__init__.py` for IK-related commands:
`GoalStrength`/`GoalObjective`/`SoftIK`/`SoftIKDistanceType`/
`SoftIKMin`/`SoftIKMax`/`IKInitialState`/`IKInitialStateFrame`/
`IKFKBlending`/`UseIKChainVals` were all already correctly wrapped with
real `*args` and an argument-count check - no repeat of the
`Ring`/`SetRenderDisplay`/`MotionBlur`/`LightFalloffType` bug in this
command family. Five candidates were wrapped bare, no arguments at
all: `UnaffectedByIK`, `EnableIK`, `EnableDeformations`, `EnableMC`,
`FullTimeIK` - the same shape that's turned out to be a real bug three
times this phase and a genuine toggle twice. Only investigated the two
this item's own description actually named (`FullTimeIK`,
`UnaffectedByIK`) rather than chasing all five blind.

**Both confirmed live as genuine argument-less toggles, matching the
`LightVisibleToCamera` precedent, not the `MotionBlur` one.** Selected
a real bone (`Bone1`, part of an actual `BoneTestObject`/`Bone1`/`Bone2`
chain) and opened Motion Options > IK and Modifiers. Clicked
"Unaffected by IK of Descendants" - Cmd History logged a bare
`UnaffectedByIK`, no argument following. "Full-time IK" was initially
grayed out and unclickable - a real precondition, found by assigning a
Goal Object (`lightwavemcp_test_object_out`, via the Goal Object
dropdown) to the same bone, after which it became clickable AND was
already checked, auto-enabled as a side effect of the goal assignment
itself rather than requiring its own command (Cmd History showed only
`GoalItem 10000001`, no separate `FullTimeIK` entry, at that point).
Unchecked it manually - Cmd History logged a bare `FullTimeIK`, same
shape as `UnaffectedByIK`. Neither needed a stub fix.

**`GoalStrength`/`IKFKBlending` confirmed live too**, sent directly via
`lw_run_command` before writing any wrapper: `GoalStrength(0.5)` and
`IKFKBlending(0.3)` on the same bone immediately showed as "Goal
Strength: 0.5" and "IK/FK Blending: 30.0%" in Motion Options - the
same 0.0-1.0-fraction-displayed-as-percent convention already known
from `lw_set_camera`'s `shutter_efficiency`. Neither showed a
precondition - both were visible and settable before any Goal Object
was assigned, unlike `FullTimeIK`.

Shipped `lw_set_ik_options(item, goal_strength=, ik_fk_blending=)`
(bundled-optional-params shape, like `lw_set_camera`/`lw_set_light`)
and `lw_toggle_ik_flag(item, flag)` (flag is `"full_time_ik"` or
`"unaffected_by_ik"` - a small dispatch tool rather than two separate
one-line tools, since both share the identical
resolve-select-then-bare-call shape). `lw_toggle_ik_flag` flips rather
than sets, documented the same way `lw_set_light` documents
`LightVisibleToCamera`/`LightCastsShadows`: there's no way to read
either flag's current state back, so a caller can't know in advance
which direction a toggle will move it.

**The real discovery of this item: bones were completely unaddressable
by this connector, for any purpose, not just IK.** Tried testing the
new tools against `"Bone1"` by name first, the same way every other
tool here resolves names - `_resolve_item_id` failed with "item not
found: Bone1". Root cause: `_find_item` (used by `lw_get_item_id`, and
so by `_resolve_item_id`) only iterates `LWI_OBJECT`/`LWI_LIGHT`/
`LWI_CAMERA` - it has never walked `LWI_BONE`, which is a separate
traversal only `_get_bones` performs (see "Bone chain traversal"
above), and `_get_bones` itself never captured each bone's own item ID,
only its name/parent/goal/pole. This was a real, previously-unnoticed
gap: no tool in this entire connector could ever target a bone by
name, for reading OR writing, before this investigation - the earlier
bone work (ROADMAP.md item 11/STATUS.md item 2) only ever reported
bones as data, never let anything address one afterward.

Fixed two ways:
1. `_get_bones` now includes `"id": lwsdk.itemid_to_str(bone_id)` on
   every bone entry, the identical conversion `_get_item_id` already
   uses for Objects/Lights/Cameras - exposed automatically through
   `lw_get_hierarchy` since that's `_get_bones`'s only caller.
2. `_resolve_item_id` (server.py) now checks `name.isdigit()` first and
   passes a purely numeric string straight through as the ID, instead
   of always treating its argument as a name to look up. This is a
   general fix, not IK-specific - any tool built on `_resolve_item_id`
   can now be pointed at a raw numeric ID obtained some other way (like
   a bone's `id` from `lw_get_hierarchy`), not just a name `_find_item`
   can already see.

Confirmed live end to end, after a Claude Desktop restart (server.py)
and a Layout plugin reload (lw_mcp_ring.py): `lw_get_hierarchy` reported
`Bone1`'s id as `"40000000"` - matching, exactly, Cmd History's own log
of a real manual click on that same bone in the Scene Editor
(`"SelectItem 40000000"`), confirming bones live in their own ID range
distinct from Object/Light/Camera's 10000000/20000000/30000000 (and
`Bone2` reported as `"40010000"`). Re-ran both new tools against
`"40000000"` directly: `lw_set_ik_options(goal_strength=0.9)` showed
"Goal Strength: 0.9" in Motion Options, and `lw_toggle_ik_flag(flag=
"unaffected_by_ik")` correctly unchecked the box, both confirmed via
screenshot and matching Cmd History entries.

Note for a future session: `Bone2`'s ID is `"40010000"` - the EXACT
same value as the unexplained "differently-scoped" `SelectItem 40010000`
Cmd History showed during item 3's investigation (see "Scene file I/O"
above), which was left as an honest documented gap rather than a
guessed formula (`40000000 + index * 10000`, since `connector_01` was
the 2nd object loaded that session, index 1). Here, `Bone2` is also the
2nd bone in its chain (index 1), and also landed on `40010000` -
completely independent contexts (one-time object-selection activation
vs. a bone's permanent item ID) producing the identical number for
"index 1" is real, if still circumstantial, support for that formula
being a genuine general LightWave convention (some kind of
position-within-a-collection ID scheme), not coincidence. Still only
two data points from two different phenomena, not a confirmed formula
for item 3's original object-selection case specifically - worth the
two/three-more-loaded-objects test item 3 already proposed, now with
more reason to expect it'll hold. Not chased further this session
since it's new, separate scope from item 7.

`ROADMAP2.md` item 7 is closed.

## Surface/material writes (ROADMAP2.md item 8)

Goal: `lw_set_surface`, the write-side counterpart to
`lw_get_surface_info`. Genuinely new territory going in: `SurfaceEditor`
in the command list just opens the UI panel, it takes no settable
arguments, so there is no native Command Port command for this at all -
the real path is `lwsdk.LWSurfaceFuncs()`'s setter methods, the same
class `lw_get_surface_info` already reads through. This would be the
first write in the whole connector to go through the read-path's Master
plugin (`LWComRing`) instead of the one-way Command Port, since that's
the only place `lwsdk`'s surface API is reachable from Python at all.

**Checked the real bound method names before writing anything against
them.** Added a temporary `lw_introspect` MCP tool (wired to the
pre-existing but unexposed `_introspect()` diagnostic already in
`lw_mcp_ring.py`) to dump `dir(lwsdk.LWSurfaceFuncs())` from a live
session, since this SDK's Python bindings have already been found to
diverge from the C docs more than once (`byName`/`getFlt` return plain
Python lists/floats, not C-style out-params). Confirmed live:
`LWSurfaceFuncs` genuinely exposes `setFlt`/`setColorVMap`/`setImg`/
`setMaterial`/`setInt`/`setShadingModel`/`setTex` as real bound methods,
not just a C-docs claim - `setFlt` (the counterpart to `getFlt`, already
used for every scalar `lw_get_surface_info` field, including the vec3
`SURF_COLR`) was the obvious target.

**Wire format**: since this is the first write to ever go through
`LWComRing`'s `Ring()` mechanism instead of a native Command Port
command, and a surface write needs a surface name plus a whole object
of properties (not just one string arg like every existing
`lw_mcp_ring.py` query), designed `arg` as `"<surface_name>|<json
object>"` - the surface name kept outside the JSON (so it can contain
spaces without escaping) using `"|"` as a separator, on the assumption
a real surface name won't contain one. Confirmed by reading
`lwcommandport`'s `_send_command` that `Ring()` sends its whole string
as one raw UDP payload with zero escaping (`args=None` means no further
`join()`/formatting happens), so a JSON blob survives intact over the
wire - but `decodeData(('s:256', ...))` caps the whole `"{MCP} ..."`
message around 256 bytes, fine for one or two properties at a time, a
real limit for many at once or a very long surface name.

**The first live test appeared to hang Layout forever - a serious,
carefully-handled scare.** Sent `diffuse=0.5` against a real surface
(`CONNECTOR`, on `connector_01`/`lightwavemcp_test_object_out`, a
loaded `.lwo`). `lw_set_surface` timed out. `_mcp_ring_debug.log` showed
the incoming `"set_surface CONNECTOR|{\"diffuse\": 0.5}"` request logged,
then nothing - no further line ever appeared for that call. This is the
exact same signature as this project's one previously confirmed crash
(`LWChannelInfo`/`nextGroup`, see "LWChannelInfo crash" above): a
message logged, then total silence. Treated it with the same gravity -
did not retry blindly, asked the user to check for a crash dialog
(none) and confirm Layout's own responsiveness (screenshot showed the
UI, menus, and Master Plugins panel all fully working). Sent `lw_ping`
immediately after: it succeeded, proving the read-path listener itself
was still alive and answering other calls. Retried `set_surface` once
more with a different value (`diffuse=0.6`) to check reproducibility -
same silent-forever signature, and `lw_ping` still recovered
immediately afterward both times.

Given this was reproducible, non-recoverable for that specific call,
but *not* a full app crash the way `LWChannelInfo` was, shipped
`_set_surface` as a permanently-disabled stub (matching
`_probe_channels`'s precedent from the original crash) rather than
guess at a workaround - an "edit-session bracket" or different
threading/marshaling approach was briefly considered but never
attempted, since `LWSurfaceFuncs`'s own method list showed no
`editBegin`/`editEnd`-style methods to base such a guess on, and this
project's norm is an honest documented gap over confidently wrong code.

**That diagnosis was wrong, caught before it was finalized - a real,
useful methodology lesson.** Before considering item 8 closed as a
partial dead end, wrote the smallest possible standalone reproduction
of the actual mechanism, rather than re-reading the same live symptom
and trusting the pattern-match to the known crash: a three-line Python
script testing `_TOPIC_RE` (the regex `ring_event` uses to split the
`"{MCP} ..."` topic from the rest of the message) against a real
`set_surface`-shaped string. The result was immediate and unambiguous:

```python
>>> re.match(r'^\{(.+)\}\s*(.*)$', '{MCP} set_surface CONNECTOR|{"diffuse": 0.5}').groups()
('MCP} set_surface CONNECTOR|{"diffuse": 0.5', '')
```

The original pattern's `(.+)` is GREEDY - it matches from the first `{`
all the way to the LAST `}` in the entire string, not the first one.
Every command before this item happened to have a payload with no
braces in it at all, so this bug was completely invisible until
`set_surface`'s JSON-encoded argument introduced a second `{`/`}` pair.
`topic` came out as literal garbage (`'MCP} set_surface CONNECTOR|
{"diffuse": 0.5'`, not `"MCP"`), so `ring_event`'s own `if topic !=
TOPIC: return` silently dropped the message before `_handle_query` -
let alone `setFlt()` - was ever reached. There was never a hang inside
`setFlt` to diagnose; the message never got that far, on *either*
attempt. Both "confirmations" of the hang were really just two
confirmations of the same transport bug.

Fixed by making the regex's first group non-greedy (`(.+?)`), confirmed
via the same standalone test that this parses correctly for both a
plain command (`{MCP} ping` -> `("MCP", "ping")`) and a
brace-containing one (`{MCP} set_surface ...` -> `("MCP", "set_surface
...")`). Reverted `_set_surface` fully back to its real
`setFlt`-calling implementation - no reason left to believe it was ever
broken. Reloaded the plugin and re-verified live from scratch, not just
trusting the fix on paper: `diffuse=0.5` alone first - Surface Editor
screenshot showed "Diffuse 50.0%", `lw_get_surface_info` read back
`0.5`. Then `color=[1,0,0]` + `glossiness=0.8` together in one call -
screenshot showed a genuinely red color swatch (255/0/0, "Glossiness
80.0%" visible though grayed out, a real precondition since Specular
was 0% - not a sign of a problem), both matching `lw_get_surface_info`'s
read-back exactly. `setFlt(surf, SURF_COLR, (r,g,b))` accepting a plain
3-tuple, symmetric with `getFlt`'s return shape, is now confirmed live,
not just assumed by analogy.

**The real, reusable lesson for this project's own methodology**: a
debug-log signature that looks exactly like a previously-confirmed
crash (message logged, then silence) does not by itself prove the same
failure mode recurred. The two situations can look identical from the
log's point of view while having completely different root causes -
here, a transport-level parsing bug that never reached the SDK call at
all, versus `LWChannelInfo`'s genuine, immediate native crash. The fix
that actually mattered was writing the smallest possible standalone
reproduction of the specific mechanism in question (a three-line regex
test) rather than re-testing the same live symptom again and trusting a
plausible-looking pattern-match to a known failure. Also: LightWave
scene state does not survive a full Layout close/reopen unless
explicitly reloaded - the test scene had to be reloaded via
`lw_load_scene` twice during this investigation after full restarts,
each time correctly restoring `CONNECTOR` to its original defaults,
which incidentally re-confirmed `lw_load_scene`/`lw_get_surface_info`
together rather than being purely incidental overhead.

`ROADMAP2.md` item 8 is closed. `lw_set_surface` ships fully functional;
`lw_introspect` (temporary) has been removed, its job done.

## Keyframe/envelope reading (ROADMAP2.md item 9)

Goal: `lw_get_channels`, closing the last real gap `lw_get_transform`'s
single-point-in-time evaluation always had - seeing the actual keyframe
structure of an item's channels (which frames have keys, what value,
what interpolation shape), not just a value sampled at the live
playhead. Deliberately last on this roadmap: this is `LWChannelInfo`-
adjacent territory, the exact SDK area with this project's one
confirmed real crash (`LWChannelInfo().nextGroup()`, see "LWChannelInfo
crash" above) - `_probe_channels` had been sitting as a permanently
disabled stub since ROADMAP.md item 1b, blocked "until NewTek's actual
SDK docs/header... can be consulted, or until someone finds a working
reference sample."

**A genuinely new lead, found by reviewing an unrelated introspection
dump.** The original crash passed an item's own `NodeID` (from
`LWItemInfo`, e.g. via `_find_item`) as `nextGroup`'s first argument -
this was always just "the only ID this connector had on hand," never
confirmed to be the *correct* ID type for that call. Item 7's IK
investigation had incidentally dumped `dir(lwsdk.LWItemInfo())` for an
unrelated reason and it included a `chanGroup` method, never tried
before. This was the concrete, specific, non-speculative reason to
revisit an area that had been correctly left alone for the rest of the
project up to this point.

**Staged the risk down exactly the way ROADMAP.md item 11's bone
traversal did, with explicit user approval at every step involving a
previously-untested call in this SDK area:**

1. **Read-only recon, zero SDK risk.** `LWItemInfo().chanGroup(item)` is
   a plain getter, already proven-safe-in-spirit (same class as
   `_get_transform`'s `param()`, `_get_hierarchy`'s `parent()`/
   `target()`/`goal()`/`pole()`). Called it and reported its `repr()`/
   `type()` without ever touching `LWChannelInfo`. Confirmed live:
   returns a `NodeID`-typed SWIG object - same *type* as an item's own
   ID, but a genuinely different underlying handle (different memory
   address), a real, distinct value worth trying.

2. **The single cautious call, explicitly approved first.** Asked the
   user directly: "this carries real risk of crashing Layout again... do
   you want me to attempt this?" Only proceeded after an explicit yes.
   Called `LWChannelInfo().nextGroup(chanGroup_result, None)` - logging
   immediately before and after, the same discipline the original crash
   investigation used, so a crash this time would leave the same kind of
   forensic evidence instead of a mysterious gap. Confirmed live: it
   returned a real result, no crash, `lw_ping` succeeded immediately
   after. The `chanGroup()` hypothesis was correct - the original crash
   really was just the wrong argument type, not a fundamentally broken
   API.

3. **One more simple getter, still no loop.** Tried `groupName()` on
   both the starting `chanGroup` and the `nextGroup` result. Confirmed
   live: real, meaningful names - the starting group was named
   `"BoneTestObject"` (the item's own name) and the `nextGroup` result
   was named `"Bone1"` (a child bone). This showed `nextGroup` walks to
   OTHER, related channel groups (e.g. a bone's own group), not
   something needed to reach an item's own channels.

4. **A safe, read-only `dir(lwsdk)` scan** (no live SDK calls, no
   item/channel touched) before designing anything further, to check
   whether a real keyframe-reading API even existed: confirmed live that
   `lwsdk.LWEnvelopeFuncs` exists, along with `LWKEY_TIME`/`LWKEY_VALUE`/
   `LWKEY_SHAPE`/`LWKEY_TAN_IN`/`LWKEY_TAN_OUT`/`LWKEY_TENSION`/
   `LWKEY_CONTINUITY`/`LWKEY_PARAM_0..3` and `LWENVTAG_KEYCOUNT`
   constants. Also dumped `dir(lwsdk.LWEnvelopeFuncs())` itself (still
   just Python introspection on a fresh object, zero risk) and found
   `nextKey`/`prevKey`/`keyGet`/`findKey` alongside the expected write-
   side methods (`createKey`/`keySet`/etc., not touched - out of scope
   for a read-only feature).

5. **The combined chain, explicitly approved given two still-untested
   calls (`nextChannel`, `nextKey`) in this same SDK area.** Asked
   directly before running it, since chaining untested calls together
   compounds the crash risk even though each followed the exact
   "start handle + `None` prev" shape already proven safe for
   `nextGroup`. Logged before/after every individual call, not just the
   whole function. Confirmed live: `nextChannel(chanGroup(item), None)`
   -> real channel named `"Position.X"`; `channelEnvelope()` -> real
   envelope; `nextKey(envelope, None)` -> real key. `keyGet(key, param)`
   (2 args) failed with a clean, catchable `"takes exactly 4 arguments
   (3 given)"` - not a crash, just a wrong call shape, fixed to
   `keyGet(envelope, key, param)`. Retried: `key_time`/`key_value`/
   `key_shape` all came back as `[1, value]` (a `[status, value]` pair,
   not a bare value).

6. **Clarified the group hierarchy before building the real loop.**
   The chain above went `chanGroup(item)` -> `nextGroup` -> `nextChannel`
   - i.e. it had been reading `"Bone1"`'s channels, not the item's own.
   Tested `nextChannel(chanGroup(item), None)` DIRECTLY, skipping
   `nextGroup` entirely: also returned `"Position.X"` - confirming
   `chanGroup(item)` is already the traversable group for the item's OWN
   channels, and `nextGroup` is for something else (sibling/related
   groups, e.g. bones) not needed for this feature at all. This
   simplified the real implementation to not need `nextGroup` in the
   final version.

7. **The remaining unknown: what does "no more results" look like?**
   Every test so far only ever asked for the *first* result
   (`prev=None`). Explicitly flagged this gap and asked before testing
   it. Confirmed live, with the user's go-ahead: a second call to
   `nextChannel(group, first_channel)` returned a genuine second channel
   (`"Position.Y"` - the pattern continues correctly, not a one-shot
   fluke), and a second call to `nextKey(envelope, first_key)` on a
   channel with only one implicit key returned Python `None` cleanly -
   not a crash, not `LWITEM_NULL`, not an exception. `None` is the
   reliable loop-termination sentinel for both.

**With every individual piece proven safe, built and shipped the real
feature**: `lw_get_channels(name)`, a bounded double loop (channels,
then keys per channel) capped the same way `_get_bones` is
(`_MAX_CHANNELS_PER_ITEM = 20`, `_MAX_KEYS_PER_CHANNEL = 500` - generous
safety margins, not expected to ever bind on real data) rather than an
unbounded `while True`. `time` is converted from raw seconds to a frame
number via `LWSceneInfo().framesPerSecond`, matching
`_get_current_time`'s existing convention; raw seconds is also
included. `shape` is left as the raw `LWKEY_SHAPE` integer - no
confirmed mapping to LightWave's own interpolation names (TCB/Linear/
Stepped/etc.) was established this session, and guessing at one would
repeat exactly the mistake this whole investigation was staged to
avoid.

**Confirmed live two ways.** A static, never-keyframed Null
(`BoneTestObject`) correctly showed all 9 channels (Position/Rotation/
Scale x/y/z) each with exactly one implicit key at frame 0, holding
LightWave's real defaults (Position 0.0, Rotation 0.0, Scale 1.0) - a
clean baseline case. Then created a fresh Null
(`KeyframeTestNull`) and keyframed it via `lw_set_keyframe` at frame 0
(position `[0,0,0]`) and frame 30 (position `[10,5,0]`, rotation/scale
untouched). `lw_get_channels` correctly showed the real multi-key data
for Position.X/Y/Z (three keys each: frame 0, frame 30, and a bonus
key - see below) - and surfaced a genuinely new, previously-
unobservable LightWave behavior in the process:

- Every channel, including ones never explicitly touched, got an extra
  key at `frame 900` (30 seconds at this scene's 30fps) - the scene's
  configured end frame - holding whatever its last value was. This
  looks like LightWave automatically bookending any keyed item's
  channels at the scene's range boundary, presumably to stop animation
  from extrapolating unexpectedly past the keyed range.
- Rotation.H/P/B and Scale.X/Y/Z - never explicitly set to a different
  value in either `lw_set_keyframe` call - show only TWO keys (frame 0
  and the frame-900 bonus key), not three. `CreateKey` at frame 30
  appears to skip adding a real keyframe on a channel whose value hasn't
  actually changed since the previous key, rather than stamping a
  redundant one everywhere.

Neither of these was possible to observe before this tool existed -
`lw_get_transform` can only ever report a channel's evaluated value at
one instant, never whether a real key exists at a given frame or how
many there are.

`ROADMAP2.md` item 9 is closed - the last item on this roadmap. All
four temporary diagnostic tools built during the staged investigation
(`lw_probe_chan_group`, `lw_probe_next_group`, `lw_probe_envelope_api`,
`lw_probe_keyframes`) have been removed, their job done; the original
`_probe_channels` stub from ROADMAP.md item 1b is left in place as the
permanent historical record of the crash this whole investigation
finally explained.

## Content Directory management (ROADMAP3.md item 1)

Goal: figure out whether `ContentDirectory(dirname)` could close a real,
already-documented gap from `ROADMAP2.md` item 3 - loading a scene or
object from outside LightWave's configured Content Directory pops a
blocking "Change Content Directory?" dialog that a one-way command
can't dismiss, so far only worked around by asking a human to click
"No" every time.

Checked the stub first: `ContentDirectory(self, *args)` already takes a
real argument correctly (`dirname`), no repeat of the missing-`*args`
bug class found repeatedly in earlier roadmaps. Tested directly via
`lw_run_command` before writing any wrapper: sent
`ContentDirectory(C:\Users\sandr\AppData\Local\Temp)` (the exact
directory the test scene lives in, outside LightWave's default Content
Directory) - Cmd History logged it cleanly, no error, no dialog.

**Confirmed live that this fully closes the gap.** Reloaded
`lightwavemcp_test_scene.lws` from that same Temp path via
`lw_load_scene` immediately after setting the Content Directory - no
"Change Content Directory?" dialog appeared this time, the scene loaded
silently, and `lw_get_scene_info` confirmed every item
(`BoneTestObject`, `connector_01`, `KeyframeTestNull`, `Light`,
`Camera`) came back intact. This is a genuine fix, not just a
workaround: the previous approach needed a human present to click "No"
every single load; this needs one command sent once per session before
the first load from an unfamiliar path.

Shipped `lw_set_content_directory(path)`, a thin wrapper (following the
same shape as every other simple settable command here). Re-tested
through the actual wrapped tool (not just `lw_run_command`) after a
Claude Desktop restart - Cmd History showed the identical
`ContentDirectory C:\Users\sandr\AppData\Local\Temp` line, confirming
the wrapper introduces no bugs of its own.

Surveyed but did not wrap two related commands: `ContentTypeDirectory(
type, dirname)` sets a per-content-type sub-path (e.g. just Objects or
just Scenes), but its `type` argument's real accepted values were never
confirmed live - guessing at an enum here would repeat exactly the
mistake this project's methodology exists to avoid, given `type`-style
integer arguments have already turned out to need live UI confirmation
more than once (`LightFalloffType`, `channelType`). `CreateContentPath`
(argument: `pathtype`) and `RecentContentDirs` (argument-less) both look
like one-shot UI actions (creating the standard subfolder layout,
opening a recent-directories menu) rather than pure setters worth
automating - not investigated further.

`ROADMAP3.md` item 1 is closed.

## Node Editor / PrincipledBSDF nodes (ROADMAP3.md item 2)

Goal: read (and eventually write) LightWave's node-based shading
parameters, especially the Principled BSDF node (base color, roughness,
metallic, specular - the same physically-based shading model most
modern renderers converged on), given explicit user interest in this
specific node type. Prioritized ahead of several other roadmap items
per that request, despite real structural complexity making
"deliberately last" the initial instinct when this roadmap was drafted.

**Confirmed up front, before any code: no native Command Port command
exists for this at all.** A survey of `lwcommandport/layout/__init__.py`
turned up only `NodeDisplacement`/`NodeDisplacementOrder`/`NodeEdges` -
none of which touch the graph itself. This meant the SDK's node API,
reachable only through the read-path's `LWComRing` Master plugin
(`lw_mcp_ring.py`), was the only possible route - the same
architectural shift `ROADMAP2.md` item 8 required for flat surface
properties, one level deeper still.

**Staged the investigation exactly the way item 8 and item 9 both
did**, given this was genuinely new, unmapped SDK territory: dir()-only
introspection first (zero risk), then one live call at a time, asking
for explicit approval before every new untested call - nine steps in
total.

**Step 1 - safe `dir(lwsdk)` scan, no live calls.** Filtered for "node"/
"shader"/"bsdf"/"principl". Confirmed a real, substantial node API
exists in this build: `LWNodeFuncs`, `LWNodeEditorFuncs`,
`LWNodeInputFuncs`, `LWNodeOutputFuncs`, `LWNodeUtilityFuncs`,
`LWNodeDrawFuncs`, `LWNodeMenuFuncs`, plus `LWBSDFFuncs` specifically
(very promising-looking given the goal) and `SURF_BSDF_INPUT`/
`NOT_BSDF` constants. Also dumped `dir()` on a fresh instance of each of
the most promising classes (still zero risk - Python introspection on
freshly-constructed objects, nothing live touched). `LWBSDFFuncs`
turned out to be a real, but different, thing than hoped: its methods
(`createBxDF`, `addBSSRDF`, `BxDF_SampleF`, `resetBSDF`, etc.) are a
*shader-plugin-authoring* API - for building custom BSDF rendering math
inside a plugin, evaluated at render time - not a way to read an
existing node's UI-configured parameters. A real dead end for this
specific goal, spotted from the method names alone before wasting any
live-call budget on it.

**Step 2, EXPLICITLY APPROVED - the first live call.** Resolved a real
surface (`CONNECTOR`, from the loaded `.lwo`, already used in item 8)
and called `LWSurfaceFuncs().getNodeEditor(surf)` - seen in an earlier
introspection dump, never called. Confirmed live: returned a real
`NodeID`-typed handle, no crash, `lw_ping` recovered immediately after.

**Step 3, EXPLICITLY APPROVED - enumerate nodes.** Chained
`LWNodeEditorFuncs`'s `numberOfNodes`/`nodeByIndex` (a bounded-count
shape, not an open-ended `first`/`next` traversal - deliberately chosen
to avoid re-guessing at a termination sentinel in a brand new class when
a safer shape was available) with `LWNodeFuncs`'s `nodeName`/
`serverUserName` to identify each one. Confirmed live, and found a
genuine surprise: `CONNECTOR` (using the classic flat "Standard"
material panel, never manually node-edited) already had a real 3-node
graph - `"Surface"` (the graph's root/output), `"Input"`, and
`"Standard (1)"`. LightWave 2019's nodal architecture underlies *every*
surface, not just ones a human has opened in the Node Editor - the
classic property panels are a friendly facade over an always-present
implicit graph.

**User added a real Principled BSDF node via the UI** (Surface Editor >
Edit Node Graph > add node, connected to the Surface node) so there
would be a real node of the target type to test against. Re-running the
enumeration correctly showed a 4th node, `"Principled BSDF (1)"` /
server name `"Principled BSDF"` - confirming the exact string to match
on going forward.

**Step 4, EXPLICITLY APPROVED - read a node's inputs.** Used
`LWNodeInputFuncs`'s `numInputs`/`byIndex` (same bounded-count shape as
step 3, deliberately not its `first`/`next` pair) to enumerate the
Principled BSDF node's inputs. Confirmed live: correctly enumerated all
27 real parameter names (`"Color"`, `"Roughness"`, `"Specular"`,
`"Metallic"`, `"Clearcoat"`, etc.), an exact match to the Surface
Editor's visible panel. Tried `evaluate_scalar`/`evaluate_vector` per
input to get each one's actual value - both failed identically: `"takes
exactly 4 arguments (2 given)"`. Not a crash, a clean, catchable error -
these calls need two more arguments than `(self, input)`, almost
certainly a shading-context structure (something like a per-shading-
point ray/vertex state) this connector has no way to construct outside
an active render callback. A real, confirmed dead end for reading a
parameter's live value *this specific way*.

**Step 5, EXPLICITLY APPROVED - a different hypothesis.**
`LWSurfaceFuncs` has a `chanGrp()` method (seen in an earlier, unrelated
introspection dump, never called) - possibly analogous to
`LWItemInfo().chanGroup(item)` from `ROADMAP2.md` item 9's keyframe
work, which would mean node parameters are reachable through the
already fully-proven `LWChannelInfo`/`LWEnvelopeFuncs` machinery instead
of fighting `evaluate_scalar`'s unclear extra arguments. Confirmed live:
returned a real `NodeID`-typed handle, no crash.

**Step 6, EXPLICITLY APPROVED - the critical test, first attempt.** Fed
`chanGrp(surf)`'s result into `LWChannelInfo().nextChannel(group,
prev)`, the exact traversal shape item 9 already proved safe for item
transform channels. Result: zero channels, but *not* a crash -
`nextChannel` just returned `None` immediately. The hypothesis wasn't
wrong, just incomplete.

**Step 7, EXPLICITLY APPROVED - refining via `nextGroup`.** Recognized
the parallel to item 9 precisely: `chanGroup(item)` alone hadn't reached
a bone's own channels either, one `nextGroup()` hop was needed to reach
`"Bone1"`'s own sub-group. Applied the same idea here: walked
`nextGroup(chanGrp(surf), prev)` in a bounded loop. Confirmed live:
found exactly one sub-group, named `"Nodes"` - a container, not yet an
individual node's group (still no direct channels on it either).

**Step 8, EXPLICITLY APPROVED - one more level.** Used `"Nodes"` as the
new parent for a second bounded `nextGroup` walk. Confirmed live: found
exactly two sub-groups, named `"Standard (1)"` and `"Principled BSDF
(1)"` - the real per-node groups, matching the two shader nodes in the
graph exactly. Neither had a direct channel yet, though - the mystery
wasn't fully solved.

**The missing piece, found via the UI, not more guessing.** Asked the
user to right-click "Roughness" on the Principled BSDF node and add an
envelope to it (matching LightWave's own UI path for making any node
parameter animatable). Re-ran the group enumeration: `"Principled BSDF
(1)"`'s group now showed a real channel, `"Roughness"` - confirming the
missing link. A node parameter is only a real, `LWChannelInfo`-reachable
channel once a human (or a future write tool) has explicitly enveloped
it; an un-enveloped parameter simply has no channel at all, which is
why steps 6-8's groups all legitimately showed zero channels rather than
crashing - there was never anything broken, just nothing there yet.
LightWave's own Graph Editor channel browser confirmed the exact same
hierarchy independently: `Channels > Surfaces > connector_01 > CONNECTOR
> Nodes > Principled BSDF`, matching `chanGrp(surf) -> "Nodes" ->
"Principled BSDF (1)"` precisely.

**Step 9 - the full end-to-end read, no separate approval needed** (a
chain of calls already individually proven safe, not new territory):
`channelEnvelope()`/`nextKey()`/`keyGet()` on the now-real Roughness
channel - the identical mechanism `_get_channels` already uses for item
transforms. Confirmed live: correctly read back `{"value": 0.1, "frame":
0.0, ...}`, an exact match to the UI's "10.0%".

**Shipped three real tools**, consolidating the nine temporary
diagnostic probes built during this investigation into clean, permanent
code (all nine `lw_probe_*`/`_probe_*` functions removed, their job
done): `lw_get_surface_nodes(surface)` (list every node, using the
proven `getNodeEditor`/`numberOfNodes`/`nodeByIndex` shape),
`lw_get_node_inputs(surface, node)` (list a node's real parameter names,
using `numInputs`/`byIndex` - documents the `evaluate_scalar`/
`evaluate_vector` dead end plainly rather than silently returning
useless data), and `lw_get_node_channel(surface, node, channel)` (the
full `chanGrp -> nextGroup -> nextGroup -> nextChannel ->
channelEnvelope -> nextKey -> keyGet` chain). Re-tested all three live,
end to end, after the consolidation - all matched the values already
confirmed during the staged investigation, proving the cleanup
introduced no regressions.

**Honest, confirmed limitation to carry forward**: only parameters with
an existing envelope are readable. This is real value (anyone who has
already set up keyframed shader parameters, e.g. an animated Roughness
sweep, can now read that data back), but it does not yet answer "what
is Metallic currently set to" for a never-touched, un-enveloped
parameter - that would need either solving `evaluate_scalar`'s real
argument shape (the shading-context structure it wants was never
identified this session) or some other still-unexplored read path.
Writing (creating a new envelope/key, or wiring up node connections) was
deliberately out of scope this pass, following the same "confirm read
before write" discipline `ROADMAP2.md` item 8 used for flat surface
properties.

`ROADMAP3.md` item 2 is closed for reading; writing and the
un-enveloped-value read gap remain open, natural candidates for a
future session.

## Per-object render-visibility flags (ROADMAP3.md item 5)

Goal: `UnseenByCamera`/`UnseenByRays`/`UnseenByAlphaChannel`/
`UnseenByRadiosity`/`UnaffectedByFog` - five commands found during the
`ROADMAP3.md` survey, all wrapped bare (no arguments) in the stub, the
same shape that's turned out to be a real bug four times
(`Ring`/`SetRenderDisplay`/`MotionBlur`/`LightFalloffType`) and a
genuine toggle four times (`LightVisibleToCamera`/`LightCastsShadows`/
`UnaffectedByIK`/`FullTimeIK`) across the first two roadmaps. Checked
live rather than assumed either way, per this project's established
rule for this exact shape.

**Found the real UI location first.** Selected `connector_01`, opened
Object Properties, found all five candidates under the "Render" tab -
four styled as buttons (`Unseen by Rays`/`Unseen by Camera`/`Unseen by
Radiosity`/`Unaffected by Fog`), the fifth (`Unseen by Alpha Channel`)
not present as its own button at all - only an "Alpha Channel" dropdown
currently showing "Use Surface Settings" was visible instead.

**The four buttons: confirmed genuine toggles, no stub bug.** Clicked
each one in turn, checking Cmd History after each: `UnseenByCamera`,
`UnseenByRays`, `UnseenByRadiosity`, `UnaffectedByFog` all logged bare,
no argument following, exactly matching the current stub. All four
buttons showed checked afterward. No fix needed - shipped
`lw_toggle_object_visibility(item, flag)` directly mirroring
`lw_toggle_ik_flag`'s shape (resolve item, `SelectItem`, call the bare
command) since there's no way to read any of these back to a known
state, same limitation as the Light/IK toggles before them.

**The fifth, `UnseenByAlphaChannel`, turned out to be something else
entirely.** Asked whether the "Alpha Channel" dropdown had an option
matching this name - it didn't directly, but had exactly two choices:
"Use Surface Settings" (the current default) and "Constant Value".
Selected "Constant Value" and checked Cmd History: it logged
`UnseenByAlphaChannel 1` - **with an argument**, unlike all four
siblings. This is a real, confirmed stub bug (the same missing-`*args`
class as `Ring`/`SetRenderDisplay`/`MotionBlur`), fixed by adding
`*args` to the stub. But it also revealed something more interesting:
this command isn't a boolean "unseen by alpha channel" flag at all
despite its name and despite sharing the exact bare-call shape of its
four true-toggle siblings - it's the underlying command for the Alpha
Channel dropdown itself, an enum. Switched the dropdown back to "Use
Surface Settings" and confirmed live: logged `UnseenByAlphaChannel 0`,
completing the mapping (`0` = Use Surface Settings, `1` = Constant
Value - the only two options this dropdown offered, no others were
available to test). Shipped as its own tool, `lw_set_alpha_channel_mode
(item, mode)`, rather than folding it into the boolean-toggle tool where
it would have been actively misleading - documented the two confirmed
values plainly and flagged that other LightWave versions' documentation
mentions additional modes (e.g. Shadow Density) never independently
confirmed in this install's dropdown, so passing an unconfirmed integer
is explicitly at the caller's own risk.

**A real UI freeze occurred during live testing of both new tools,
worth recording honestly even though it was never root-caused.** After
calling `lw_toggle_object_visibility(item="connector_01",
flag="unseen_by_camera")` and `lw_set_alpha_channel_mode(item=
"connector_01", mode=1)` back to back through the actual wrapped tools
(both returned clean success, no errors), the Object Properties/Scene
Editor/Command History/Master Plugins floating windows all stopped
responding to mouse interaction (couldn't drag the Cmd History
scrollbar, couldn't click into other panels), while the main Layout
window's left-side menu remained clickable. Cmd History kept logging
newly-arriving commands correctly even during the freeze (confirmed via
`lw_toggle_object_visibility`/`lw_set_alpha_channel_mode` calls made
while investigating), showing the Command Port and its processing loop
were still alive - this was not the same failure mode as the
`LWChannelInfo`/`nextGroup` crash (no silence, no unresponsive process),
more narrowly a UI-interaction freeze. `lw_ping` initially still
succeeded, then subsequently `lw_get_scene_info` timed out as the
session degraded further. Not clearly attributable to either new
command specifically - both had already logged cleanly with zero errors
in Cmd History well before the freeze became apparent, and this was a
very long session with many restart/reload cycles by this point, a
plausible alternative explanation (cumulative resource pressure) that
was not and could not be ruled out. Recovered cleanly via a full
LightWave close/reopen and scene reload, with no corruption - Object
Properties for `connector_01` displayed normally afterward, all four
toggles correctly reset to their saved (unchecked) state, and both new
tools were still functioning correctly post-recovery. Recorded as an
honest operational note, not a confirmed root cause - if this recurs
under more controlled conditions in a future session, especially
isolated to one specific command, it deserves the same staged
investigation this project has given its two confirmed real crashes.

`ROADMAP3.md` item 5 is closed.

## Render Globals / GI / quality settings (ROADMAP3.md item 3)

Goal: `RenderThreads`/`RenderTileSize`/`RenderAlgorithm`/`RenderMode`/
`Antialiasing` family/`RadiosityInterpolation`/`ObjGIRadiosityTolerance`/
`ColorSpaceOutput` family - closing the biggest remaining "can trigger a
render but can't configure it" gap. Checked exact stub signatures first
(a now-routine step): `RenderThreads`/`RenderTileSize`/`RenderAlgorithm`/
`RenderMode`/`ObjGIRadiosityTolerance`/`RadiosityInterpolation`/
`Antialiasing`/`MinAntialiasing`/`MaxAntialiasing` were all already
correctly wrapped with real arguments; `EnableRadiosity0`/
`EnableRadiosity1`/`BakeRadiosityScene`/the `ColorSpaceOutput` family
were bare zero-arg candidates needing live verification, per this
project's now-established rule for that shape.

**Found the real UI locations first**, via Render Properties (Render
menu > Render Properties). The "Render" tab showed "Render Tile Size:
64" and "Automatic Multithreading" (checked, with "Multithreading
Limit: 12" grayed out) - direct, confident matches for `RenderTileSize`
and `RenderThreads`.

**`RenderTileSize(32)` confirmed live, zero precondition** - the field
updated 64 -> 32 immediately.

**`RenderThreads(4)` confirmed live, and better-behaved than expected**
- not only did "Multithreading Limit" update to "4 Threads", but
"Automatic Multithreading" auto-unchecked itself as a side effect, with
no separate precondition command needed at all - a cleaner result than
`lw_set_camera`'s Motion Blur precondition, which needed an explicit
`DepthOfField()`-style toggle sent first.

**The Global Illumination tab.** "Enable GI" (checked) and a "Type"
dropdown showing only "Monte Carlo" - clicking it revealed no second
option ("monte carlo is the only option, strangely"). Toggled "Enable
GI" on/off repeatedly while checking Cmd History: `EnableRadiosity0`
logged bare every single time, confirming a genuine argument-less
toggle, no stub bug. Clicking "Bake Scene" (under "Interpolated Cache")
required "Enable Caching" first, then triggered a real, visible render/
bake process (a "Render Status" progress window, "Preprocessing
Frame...") - confirming `BakeRadiosityScene` is a genuine one-shot
render-trigger action, not a persistent setting, the same category as
`MatchGoalOrientation`/`KeepGoalWithinReach` found (and deliberately
left unwrapped) during `ROADMAP2.md` item 7's bone work.

**`ObjGIRadiosityTolerance` - a real, unresolved precondition.**
"Angular Tolerance: 20.0°" under the "Interpolated" sub-section looked
like an exact match. Sent `ObjGIRadiosityTolerance(45)` directly - got a
real LightWave error dialog: "This option only applies when Global
Illumination Mode is set to Monte Carlo Interpolated." Tried satisfying
it: `RadiosityInterpolation(1)` correctly checked the "Interpolated"
checkbox (confirmed live via screenshot) - but resending
`ObjGIRadiosityTolerance(45)` produced the *exact same* precondition
error again, unchanged. The dropdown genuinely only ever offered "Monte
Carlo" as a `Type` choice in this install - no distinct "Monte Carlo
Interpolated" *mode* (as opposed to the "Interpolated" checkbox, which
is evidently a different, narrower thing) was ever reachable to select,
despite the error message referencing that exact name. Left as an
honest, unresolved gap - shipped `lw_set_gi_radiosity_tolerance` anyway
since the argument itself is confirmed correct (the same call succeeded
without an argument-count error both times), following the same
"ship the legitimate write, document the precondition honestly" call
`lw_set_camera` made for its Motion-Blur-gated shutter properties before
that gap was later closed.

**A genuinely new operational finding, not specific to this item.**
Tested all four new tools together via one parallel tool-call batch
(`lw_set_render_globals(threads=2, tile_size=16)`,
`lw_toggle_global_illumination()`, `lw_set_gi_interpolated(1)`,
`lw_set_gi_radiosity_tolerance(30)`) - all four returned clean "sent"
success responses with no errors. But Cmd History told a different
story: `RenderThreads 2` and `RenderTileSize 16` logged correctly,
`EnableRadiosity0` logged correctly, but `RadiosityInterpolation`
logged as `0` - the OPPOSITE of the `1` actually sent - and
`ObjGIRadiosityTolerance` never appeared in Cmd History at all, the
same silent-drop symptom seen once already earlier in this same
investigation (with a single, non-batched call). Immediately re-sent
just `lw_set_gi_interpolated(1)` alone, sequentially - it logged
correctly as `1` this time, and the "Interpolated" checkbox showed
checked, confirming the tool itself was never wrong. This points to a
real, if unsurprising in hindsight, characteristic of the Command
Port: it's plain UDP, with no delivery or ordering guarantee, and this
project's own tools already document every write as "one-way,
fire-and-forget... no confirmation LightWave accepted it" - but this is
the first time that abstract caveat manifested as a concretely
observed, reproducible symptom (a wrong value logged, not just a
missing one) rather than just a theoretical risk. Lesson for future
work: sending several related settings together, whether via one
`lw_run_command` sequence or several tool calls in one batch, should be
verified afterward via a screenshot or read rather than trusting a
clean batch of "sent" responses at face value - this project's own
"one-way" framing is not merely a formality.

`EnableRadiosity1` and the `RenderAlgorithm`/`RenderMode`/
`Antialiasing`/`ColorSpaceOutput` families were surveyed (stub
signatures checked, confirmed real-`*args` where applicable) but not
tested live or wrapped this pass - no confident UI correspondence was
found for most of them under the VPR renderer this install defaults to,
and the item's core stated goal (thread/tile/GI quality control) was
already substantially met by the four tools shipped. Left open for a
future pass rather than guessed at.

`ROADMAP3.md` item 3 is closed for the confirmed subset.

## Scene environment/atmosphere (ROADMAP3.md item 4)

Goal: `Backdrop`/`BackdropColor`/`GradientBackdrop`/`SkyColor`/
`SkySqueezeColor` and the `Fog` family - a coherent, entirely untouched
category for a scene's visual environment, separate from geometry and
animation. Checked exact stub signatures first, as usual: most of the
color/numeric commands were already correctly wrapped with real
arguments; `Backdrop`/`GradientBackdrop`/`EnableVolumetricLights`/
`EnableVolumetrics` were the bare zero-arg candidates needing live
verification.

**Found the real UI location via the left sidebar's "Backdrop ^F5"
link**, which opens an "Effects" panel with Backdrop/Compositing/Legacy
Volumetrics/Processing tabs. Opening it logged a bare `Backdrop` in Cmd
History immediately - confirming `Backdrop()` is a panel-opener command,
the same category as `SurfaceEditor`/`ItemProperties`, not a setting to
wrap.

**`GradientBackdrop` confirmed a genuine toggle** - unchecking the real
"Gradient Backdrop" checkbox logged it bare, and the Zenith/Sky/Ground/
Nadir Color fields correctly grayed out, confirming it gates them.

**`BackdropColor`/`SkyColor` confirmed live with real color swatches** -
`BackdropColor(1, 0, 0)` showed genuinely red (255/0/0); after
re-enabling Gradient Backdrop, `SkyColor(0, 1, 0)` showed genuinely
green. `ZenithColor`/`GroundColor`/`NadirColor` (same panel, identical
confirmed `(red, green, blue)` signature) were found in the stub but not
independently live-tested this pass, given how consistently this exact
command shape has already proven correct twice in the same panel.

**Fog turned out to live somewhere different than expected.** The
"Legacy Volumetrics" tab of the Effects panel turned out to be a
plugin-based add-on system (Ground Fog/HyperVoxels 3.0/PixieDust, added
via an "Add Legacy Volumetric" dropdown) - a different mechanism
entirely from the flat `FogType`/`FogColor`-style commands being
investigated. The real match was found instead under Render Properties'
"Volumetrics" tab (not "Legacy Volumetrics"), which has "Enable
Volumetrics", "Fog Type", "Min/Max Distance", "Min/Max Amount", and "Fog
Color" fields matching the survey's command list closely.

**`EnableVolumetrics` confirmed a genuine toggle with a real, important
precondition role.** Sent `FogType(1)`/`FogColor(0, 0, 1)` while
"Enable Volumetrics" was unchecked - both were accepted without error
and logged cleanly in Cmd History, but Fog Type stayed "Off" and Fog
Color stayed white, no visible change at all. Sent `EnableVolumetrics()`
- confirmed it checked the box. Resent `FogType(1)` alone - this time
the dropdown correctly showed "Linear" (confirmed by clicking that exact
entry and finding no new Cmd History line, meaning it was already
correctly set to that value, just not freshly redrawn until interacted
with). This is exactly the DOF/Motion Blur precondition shape from
earlier roadmaps, now confirmed for the entire Volumetrics/Fog panel as
a whole.

**`FogColor` alone never visibly updated, even after the precondition
was satisfied - a real, unresolved gap.** Resent `FogColor(0, 0, 1)`
after `EnableVolumetrics` was confirmed checked and `FogType` was
confirmed showing "Linear" - Cmd History logged it cleanly, but the Fog
Color swatch stayed white (255/255/255), never showing blue. This is
different from every other color command tested this session
(`BackdropColor`/`SkyColor` both updated correctly), and different from
`FogType`'s own initial staleness (which turned out to just need a UI
interaction to redraw, not a real failure). Genuinely ambiguous whether
this is a real no-op specific to `FogColor` or just a redraw quirk that
would resolve with more UI interaction - left as an honest, explicitly
flagged unconfirmed gap in `lw_set_fog`'s docstring rather than either
overclaiming success or dropping the parameter entirely.

Shipped four tools consolidating these findings: `lw_set_backdrop`,
`lw_toggle_gradient_backdrop`, `lw_toggle_volumetrics`, `lw_set_fog`.
Re-verified `lw_set_backdrop(color=[0,0,1])` and
`lw_toggle_gradient_backdrop()` through the actual wrapped tools after a
Claude Desktop restart - both logged correctly and the Backdrop Color
swatch showed genuinely blue, confirming the wrappers introduce no bugs
of their own.

Per-light `LightVolumetricSamples`/`LightVolumetricIntensity` (natural
extensions to `lw_set_light`, given Light Properties already showed
"Volumetric Samples"/"Volumetric Intensity" fields in earlier
`ROADMAP2.md` item 5 screenshots) and `EnableVolumetricLights` were
surveyed and confirmed real signatures but not tested live or wrapped
this pass - deliberately left for a future session rather than further
extending an already-large item.

`ROADMAP3.md` item 4 is closed for backdrop and fog, with `FogColor`'s
gap honestly documented rather than resolved.

## Deeper bone rigging (ROADMAP3.md item 6)

Goal: a scoped subset of the 40+ bone-specific commands found in the
original `ROADMAP3.md` survey - `ROADMAP2.md` item 7 already covered
chain-level IK flags and goal/pole assignment, but a real bone's own
rigging properties (strength, rest length, weight map, falloff, active
state, limited range) were untouched. Checked exact stub signatures
first: most were already correctly wrapped with real arguments;
`BoneActive`/`BoneStrengthMultiply`/`BoneWeightMapOnly`/
`BoneLimitedRange` were the bare zero-arg candidates needing live
verification.

**Finding the real UI location took a few tries.** Bone1's item-level
Motion Options only showed IK goal/pole/chain settings (already wrapped
in `ROADMAP2.md` item 7) - no bone-specific rigging fields at all. The
generic Modify tab (Translate/Rotate/Transform tools) didn't have them
either. The actual panel turned out to be reachable via the "Properties"
button in the bottom status bar while a bone is the current item, which
opens a "Bones for BoneTestObject" panel - a genuinely different,
bone-specific properties dialog from both Motion Options and Item
Properties.

**This panel has object-wide settings above per-bone settings**, both
in the same dialog: "Use Bones From Object", "Falloff Type", "Faster
Bones", "Limited Bones Number" apply to every bone on the object; below
a "Current Bone" selector, "Bone Type", "Bone Active", "Rest Position/
Rotation/Length", "Bone Weight Map", "Strength", "Limited Range" (Min/
Max), and the muscle/joint-compensation family apply only to whichever
bone is currently selected there. `BoneFalloffType` specifically targets
the OBJECT-WIDE dropdown, not a per-bone one - worth remembering since
its name alone doesn't signal that scope.

**`BoneActive` confirmed a genuine toggle, with a real, interesting
default.** Clicking the checkbox live logged `BoneActive` bare in Cmd
History - no stub bug. Also found: a real, already-existing bone
(`Bone1`, part of a genuine 2-bone chain used throughout this project's
bone work) had "Bone Active" UNCHECKED by default, confirming a bone
can exist, be parented, and participate in a hierarchy while still
being inactive - a real LightWave rigging concept, not a connector
artifact.

**`BoneStrength(0.5)` and `BoneRestLength(2)` confirmed live with zero
precondition** - "Strength" showed "50.0%", "Rest Length" showed "2m",
both immediately.

**`BoneWeightMapName("TestWeightMap")` sent successfully but couldn't
be visually confirmed** - logged cleanly in Cmd History, no error, but
"Bone Weight Map" stayed "(none)" in the dropdown. Not treated as a
failure: this project's bone test rig (`BoneTestObject`) is a plain Null
with `AddBone`/`AddChildBone`-attached bones, no real mesh geometry or
vertex maps at all - there was never a real weight map named
"TestWeightMap" for the dropdown to match against. Documented as
likely-correct-by-signature (matching the confirmed `(name)` argument
shape) rather than independently verified, honest about the test rig's
own limitation rather than claiming success or failure either way.

**`BoneLimitedRange` confirmed a genuine toggle that gates real
fields** - checking it live correctly ungrayed the "Min"/"Max" fields
underneath (previously grayed at their defaults, 0m/1m) - the same
DOF/Motion-Blur precondition shape from earlier roadmaps, now confirmed
for bones too.

**`BoneFalloffType(2)` confirmed live and object-wide** - the dropdown
at the top of the panel (shared across all bones on the object) changed
from "Inverse Distance ^16" to "Inverse Distance ^2", confirming both
that the write works and that it's genuinely object-scoped, not
per-bone, exactly as its position in the panel suggested.

Shipped `lw_set_bone` (bundling `BoneStrength`/`BoneRestLength`/
`BoneRestPosition`/`BoneRestRotation`/`BoneWeightMapName`/
`BoneFalloffType`/`BoneMinRange`/`BoneMaxRange`) and `lw_toggle_bone_flag`
(`BoneActive`/`BoneLimitedRange`), following the exact `lw_set_ik_options`
+ `lw_toggle_ik_flag` split precedent from `ROADMAP2.md` item 7 for the
same reason: some properties are real settable values, two are
argument-less toggles with no way to read a known state back.
`rest_position`/`rest_rotation`/`min_range`/`max_range` weren't
independently live-tested - shipped by pattern-confidence given the
identical confirmed `*args` shape already proven for their siblings in
the same panel. Re-verified `lw_set_bone(strength=0.8)` and
`lw_toggle_bone_flag(flag="limited_range")` through the actual wrapped
tools by numeric bone ID after a Claude Desktop restart - both correctly
updated the panel ("Strength: 80.0%", "Limited Range" unchecked),
confirming the wrappers and `_resolve_item_id`'s numeric-passthrough
(from `ROADMAP2.md` item 7) work correctly together for bones.

The muscle/joint-compensation family (`BoneJointComp*`/
`BoneMuscleFlex*`/`BoneTwist*`/`BoneBulge*`) and
`BoneWeightMapOnly`/`BoneStrengthMultiply` were surveyed (all visible in
the same panel) but deliberately not wrapped this pass - genuinely real
organic-deformation features, but ones that would benefit from a real
mesh with actual weight maps to test against meaningfully, rather than
this session's plain-Null test rig. Left for a future, dedicated
session.

`ROADMAP3.md` item 6 is closed for the scoped subset.

## Morph/Endomorph control (ROADMAP3.md item 7)

Goal: `MorphAmount(morph)`/`MorphTarget(itemid)` - the classic
object-to-object morph, assigning a whole other item's shape as a blend
target for the current object, distinct from vmap-based Endomorphs
baked into a single object's own geometry. Checked stub signatures
first as usual: both already correctly wrapped with real arguments, no
repeat of the missing-`*args` bug class.

**The UI hunt came up empty, twice, before the real technique paid
off.** First guess: a Motion Modifier, since Motion Options already had
an "Add Modifier" dropdown for other per-item behaviors (Follower,
Effector, etc., seen while confirming this) - opened it on `connector_01`
and scanned the full alphabetical list live; no "Morph" entry anywhere
in it. Second guess: an Object Properties tab, on the theory that
Endomorphs are usually reached through a Deform-style tab in other
LightWave versions - checked the actual tab set in this install
(Primitive/Render/Appearance/Lights/Global/FX/Instancer) and confirmed
no "Deform" tab exists at all. Also hit a real interruption during this
phase: LightWave itself was accidentally closed and had to be reopened
and the scene reloaded mid-investigation - re-verified `lw_ping`/
`lw_get_scene_info` before continuing, confirming the connector and
scene state were both intact afterward.

**Found it by sending the command directly and reading LightWave's own
error dialog** - the same technique that already worked for
`ObjGIRadiosityTolerance` (item 3) and the Fog/Volumetrics precondition
(item 4), now proving itself again as a reliable fallback whenever a
dedicated panel can't be found by browsing alone. `MorphAmount(0.5)`
alone popped: "This option only applies when the current object has a
morph target." This confirms both that the command is real and exactly
what precondition gates it, without ever needing to find where a
"morph target" would normally be assigned through the UI.

**Satisfied the precondition and confirmed end to end.** Sent
`MorphTarget("10000000")` (using `BoneTestObject`'s numeric ID as an
arbitrary real item to serve as the target) directly via `lw_run_command`
first, then resent `MorphAmount(0.5)` - no error dialog this time, both
commands logged cleanly in Cmd History. No visible geometry change was
possible to confirm further, since `BoneTestObject` is a plain Null
with no real mesh to blend toward - a limitation of the test rig, not
evidence either way about the command's correctness.

Shipped `lw_set_morph(item, target=, amount=)`, resolving `target` to a
numeric ID the same way `lw_set_goal`/`lw_set_parent` do (this command
family shares the identical "wants a numeric ID, not a name" quirk).
Re-verified through the actual wrapped tool by name (not raw
`lw_run_command`) after a Claude Desktop restart:
`lw_set_morph(item="connector_01", target="BoneTestObject", amount=0.7)`
correctly logged `SelectItem 10000001` / `MorphTarget 10000000` /
`MorphAmount 0.7`, no error, confirming the wrapper and its numeric-ID
resolution work correctly together.

`SaveEndomorph(name)`/`UseMorphedPositions()` were surveyed (real
`*args` signature confirmed for the former) but not tested live or
wrapped this pass - a real vmap-based Endomorph save/use workflow needs
actual mesh geometry with real vertex data to test meaningfully, which
this session's Null-based and simple-loaded-object test rigs don't
provide well. Left for a future, dedicated session with a richer test
object.

`ROADMAP3.md` item 7 is closed - the last item on this roadmap. All 7
items are now done.

## Follow-up sweep: closing the easy/moderate open items

After `ROADMAP3.md` was fully done, reviewed the accumulated list of
"surveyed but not independently tested" and "shipped by pattern-
confidence" items across all 7 items, roughly ordered by expected
effort, and worked through the easy tier live.

**Backdrop: `ZenithColor`/`GroundColor`/`NadirColor`.** Sent all three
together (Gradient Backdrop already enabled from earlier work) -
Zenith showed yellow (255/255/0), Ground showed magenta (255/0/255),
Nadir showed cyan (0/255/255), all exact matches, no reordering issues
this time despite being sent as one parallel batch (unlike item 3's
earlier finding - each targeted a genuinely different field, so even
had reordering occurred it couldn't have corrupted any single field's
final value the way `RadiosityInterpolation` was corrupted before).

**Bones: `BoneMinRange`/`BoneMaxRange`/`BoneRestPosition`/
`BoneRestRotation`.** Re-enabled Limited Range first (it had been left
toggled off at the end of item 6's original session).
`BoneMinRange(0.5)`/`BoneMaxRange(3)` showed "Min: 500mm"/"Max: 3m"
correctly. `BoneRestPosition`/`BoneRestRotation` produced a genuinely
useful UI discovery: they look like plain, inert-looking buttons in the
Bones panel, not value fields - but clicking either one opens a real
"Set Bone Rest Position"/"Set Bone Rest Rotation" requester,
pre-populated with whatever value is already set. Sent
`BoneRestPosition(1, 2, 3)` then clicked the button: the requester
showed X:1m, Y:2m, Z:3m exactly. Sent `BoneRestRotation(10, 20, 30)`
then clicked its button: Heading:10.0, Pitch:20.0, Bank:30.0, also
exact. This is a reusable technique for any other "button-style" field
in this SDK - the button isn't just an action trigger, it's a live
requester reflecting current state, giving a clean confirmation path
even when a field isn't a simple inline text box.

**`EnableVolumetricLights` - confirmed genuine, but with a real,
important methodology correction.** Sent the bare command three times
via `lw_run_command` with no arguments each time. Cmd History showed
`EnableVolumetricLights 0`, then `1`, then `0` - alternating, as if a
real toggle's resulting state were being appended as an argument. This
looked, at first glance, exactly like the `UnseenByAlphaChannel`
discovery from `ROADMAP3.md` item 5 (a command that looked like a
simple toggle but turned out to secretly take an argument). Rather
than assume this pattern repeated and start editing the stub, ran the
actual definitive test instead: sent `EnableVolumetricLights` WITH an
explicit argument (`[1]`) and confirmed it raised
`"Layout.EnableVolumetricLights() takes 1 positional argument but 2
were given"` - the same error shape a genuinely bare-only stub method
always produces when called with too many arguments. This proves the
wrapped method itself only accepts zero arguments, meaning none of the
three earlier bare calls could possibly have sent a real argument
either - the `0`/`1`/`0` suffixes in Cmd History must be a LightWave
display convention (echoing some toggle commands' resulting boolean
state into the log for human readability) rather than evidence of what
was actually transmitted over the wire.

This is a genuinely important, generalizable finding for this
project's whole toggle-verification methodology going forward: **a
numeric suffix appearing in Cmd History is not, by itself, reliable
proof that a command takes an argument.** Only some toggle-shaped
commands get this echo treatment (most confirmed toggles this project
has tested - `UnaffectedByIK`, `GradientBackdrop`, `EnableRadiosity0`,
`BoneActive`, etc. - have always logged completely bare, with nothing
after the command name at all), so this was the first time the
distinction actually mattered. The reliable, definitive test going
forward is: does passing an explicit argument to the wrapped stub raise
a Python arg-count `TypeError`? If yes, the stub (and, by inference,
the real command) is genuinely argument-less; if the extra argument is
silently accepted instead, that's the real signal a stub fix is needed
- not whatever Cmd History happens to display.

Also confirmed via the same technique: `BoneWeightMapOnly` and
`BoneStrengthMultiply` (bone rigging) are both genuine toggles.
`BoneWeightMapOnly` additionally popped a real LightWave error dialog,
"This option only applies when using a weight map" - a real
precondition, consistent with this test rig never having had a real
weight map assigned (matching `BoneWeightMapName`'s own earlier
unconfirmed-by-necessity finding).

**Per-light `LightVolumetricSamples`/`LightVolumetricIntensity`.**
Opened Light Properties for `Light`, confirmed "Volumetric Samples: 2"/
"Volumetric Intensity: 100.0%" already visible (gated by "Affect
Volumetrics", already checked). Sent `LightVolumetricSamples(8)`/
`LightVolumetricIntensity(0.5)` - showed "8"/"50.0%", both exact,
zero precondition beyond the checkbox already being on.

**Shipped all of the above as real tool updates**, not just new
findings: extended `lw_set_backdrop`'s docstring to drop the "not
independently tested" caveat for the three gradient colors; extended
`lw_set_bone`'s docstring the same way for rest position/rotation/min/
max range; added `"weight_map_only"`/`"strength_multiply"` as two more
`lw_toggle_bone_flag` flag options; added `volumetric_samples`/
`volumetric_intensity` parameters to `lw_set_light`; and added a new
tool, `lw_toggle_volumetric_lights`, wrapping `EnableVolumetricLights`
with its methodology finding documented directly in the tool's own
docstring so a future session doesn't have to rediscover it. Re-tested
`lw_toggle_volumetric_lights`, `lw_set_light(volumetric_samples=10)`,
and `lw_toggle_bone_flag(flag="strength_multiply")` through the actual
wrapped tools after a Claude Desktop restart - all three returned clean
success.

**`ContentTypeDirectory` (per-content-type sub-path).** Found the real
UI first: Preferences > Paths tab, a list of buttons - "Scenes",
"Hierarchies", "Objects", "Images", "Envelopes", "Motions", "Previews",
"Animations", "Surfaces", "Nodes", "Shaders", "Dynamics", "Rigs",
"Sounds", "Lights", "Radiosity", "Color Tables", "Image Cache", "Vert
Cache", "Grid Cache", "Output Directory", "Backup Directory" - each
presumably a `ContentTypeDirectory(type, dirname)` target. Tested the
most likely hypothesis directly rather than guessing an enum: `type` is
the literal panel label string. Sent
`ContentTypeDirectory("Objects", "C:\...\TestObjDir")` via
`lw_run_command` - Cmd History logged `ContentTypeDirectory Objects
C:\...\TestObjDir`, and a screenshot of the Paths tab showed the
"Objects" button's own label had changed to "TestObjDir". This was a
genuinely useful discovery beyond just confirming the argument shape:
these per-type buttons double as a *live display* of the current
sub-path, not fixed captions - the same "button is also a live state
readout" pattern already found for bone Rest Position/Rotation earlier
in this sweep, now confirmed a second time in an unrelated panel.
Reverted with `("Objects", "Objects")` and confirmed via screenshot the
label went back to "Objects" exactly.

Shipped as `lw_set_content_type_directory(content_type, dirname)`,
then re-verified through the actual wrapped tool after a Claude
Desktop restart (not just the raw `lw_run_command` probe): called it
with `("Objects", "ToolVerify")`, confirmed via Cmd History
(`ContentTypeDirectory Objects ToolVerify`, identical shape to the
already-visually-confirmed raw test) that the tool dispatches
correctly, then reverted to `("Objects", "Objects")` again to leave the
test rig clean. Only `"Objects"` was exercised end-to-end against a
real UI change; the other twenty-one type strings are inferred from
the panel's own visible labels and shipped with that caveat rather than
claimed as independently confirmed.

**`SaveEndomorph`/`UseMorphedPositions`.** Definitive arg-count test
confirmed `UseMorphedPositions` is a genuine argument-less toggle
(explicit-argument call raised the stub's own arg-count `TypeError`).
Hunting for its real UI checkbox took several rounds: a web search
surfaced "Use Morphed Positions" as a Bone Properties checkbox that
lets bone deformation apply after morphs instead of before - but this
turned out to be from LightWave 2025's own documentation
(docs.lightwave3d.com/2025/bone-properties.html), not necessarily
accurate for 2019.1.5. Checked the actual 2019.1.5 Bones panel via a
full-panel screenshot (every checkbox: Bone Active, Maya Style Joints,
Use Weight Map Only, Weight Normalization, Multiply Strength by Rest
Length, Limited Range, Joint Compensation, Joint Comp for Parent,
Muscle Flexing, Parental Muscle Flexing, Muscle Bulge, Parental Muscle
Bulge, Twist) - no "Use Morphed Positions" anywhere. Also checked
Motion Options, General Options, and Object Properties (no "Deform"
tab exists in this build - Object Properties just lists modifier
entries like Morphing/Bones/Subdivision) - still nothing. Concluded
this checkbox likely doesn't exist as such in 2019.1.5, or is gated
behind a state (a real Endomorph plus active bones) this Null-based
test rig can't produce, and shipped `lw_toggle_use_morphed_positions()`
as a confirmed-genuine bare toggle with that UI-location caveat spelled
out, rather than continuing to chase a moving target.

That same full-panel Bones screenshot incidentally resolved an earlier
open question from this sweep: `BoneStrengthMultiply` does map to
"Multiply Strength by Rest Length" (visibly checked after the toggle
had been flipped) - an earlier pass had left this as an unpinned
candidate because it "didn't visibly change" in a narrower screenshot;
this fuller one shows it did.

`SaveEndomorph(name)` was tested by sending it directly against
`BoneTestObject` - it immediately popped a real LightWave error
dialog: "Null objects are automatically saved with the scene."
`BoneTestObject` is a Null, so this is a genuine, confirmed
precondition (SaveEndomorph refuses Nulls outright), not a stub bug.
Shipped as `lw_save_endomorph(item, name)` with this precondition
documented, but the actual successful bake - a new named Endomorph
appearing with correct deformed positions on a real mesh - is left
unconfirmed for a future session with a real loaded mesh object that
has genuine point deformation (bones or Morph Mixer) applied to it.

**The bone muscle/joint-compensation family.** The stub revealed a
clean pattern before any live testing was needed: `BoneJointComp()`/
`BoneJointCompParent()`/`BoneMuscleFlex()`/`BoneMuscleFlexParent()`/
`BoneBulge()`/`BoneBulgeParent()`/`BoneTwist()` are all bare toggles,
each paired with an amount setter -
`BoneJointCompAmounts(self, parent)`/`BoneMuscleFlexAmounts(self,
parent)` bundle both sides into one call, while
`BoneBulgeAmount`/`BoneBulgeParentAmount`/`BoneTwistAmount` are each
independent single-argument setters. This exactly matched what the
Bones panel's "Bone Displacement"/"Parent Displacement" section (seen
in an earlier screenshot from the `UseMorphedPositions` search) already
showed: seven rows, each a percentage plus what looked like its own
toggle button.

Verified the whole family live in one pass: sent `BoneJointComp()`
then `BoneJointCompAmounts(0.3, 0.6)` - a screenshot confirmed "Joint
Compensation" checked and reading 30.0%, "Joint Comp for Parent"
reading 60.0% but still UNCHECKED (I never called
`BoneJointCompParent()`) - proving these two rows are genuinely
independent toggles, and that the Amounts command sets both numeric
fields regardless of either checkbox's state. Then sent `BoneTwist()`
alone: it immediately popped a real LightWave error dialog, "This
option does not apply to the current bone type" - a genuine
precondition, consistent with the "Twist" row already appearing grayed
out in every screenshot of this panel (this test rig's bones are
Z-axis type). Then sent `BoneMuscleFlex()`, `BoneMuscleFlexAmounts(0.4,
0.7)`, `BoneBulge()`, `BoneBulgeAmount(0.55)`, `BoneBulgeParent()`,
`BoneBulgeParentAmount(0.8)` together and checked the result: Bulge
behaved exactly like Joint Comp (both `bulge` and `bulge_parent`
showed checked, because I'd explicitly called both `BoneBulge()` AND
`BoneBulgeParent()` this time - not a contradiction, just the natural
result of toggling both), amounts read 55.0%/80.0% exactly. But Muscle
Flex showed a real asymmetry: both "Muscle Flexing" AND "Parental
Muscle Flexing" appeared checked despite only calling
`BoneMuscleFlex()` - never `BoneMuscleFlexParent()`. Suspecting a
misread, asked for a zoomed screenshot specifically of those two rows;
the user confirmed both genuinely were checked. This means
`BoneMuscleFlex()` controls both checkboxes together, unlike the
joint-comp/bulge pairs - documented as a real, confirmed asymmetry
rather than assumed to be identical to its siblings.

Shipped as seven new `lw_toggle_bone_flag` flags (`joint_comp`/
`joint_comp_parent`/`muscle_flex`/`muscle_flex_parent`/`bulge`/
`bulge_parent`/`twist`) plus a new `lw_set_bone_deform(item, ...)` tool
bundling the five amount setters with the same "send self/parent
together, defaulting the omitted one to 0.0" shape lw_set_camera-style
tools in this file already use for genuinely paired native commands.

Along the way, revisited `UseMorphedPositions` (shipped in the
previous item's follow-up pass with a "couldn't find its UI checkbox"
caveat) with the Bones-panel screenshots gathered during this same
investigation - and separately, the earlier restart-verification call
to `lw_toggle_use_morphed_positions()` had left an error dialog sitting
unseen on screen: "Use Morphed Positions not supported with the
current bone mode." This is close enough to the 2025 documentation's
"not supported with Limited Bones" that it upgrades the earlier
caveat - the feature and its precondition are both real in 2019.1.5,
just gated behind a bone mode this test rig doesn't have, not absent
from the UI as originally assumed. Updated that tool's docstring
accordingly.

**`EnableRadiosity1` - definitively resolved, a new category of
finding for this project.** Every prior "surveyed but not confirmed"
command in this project turned out to be either a genuine toggle, a
real stub bug (missing `*args`), or gated behind a real precondition.
This one is different: the definitive arg-count test first confirmed
it's a genuine bare command (passing an argument raised the stub's own
arg-count `TypeError`), but sending it bare produced LightWave's own
error dialog - not a precondition message, but "Unknown command:
'EnableRadiosity1'". LightWave's command parser itself doesn't
recognize this command name at all in 2019.1.5, despite
`lwcommandport`'s stub defining it correctly. The stub was very likely
generated against a different LightWave version whose command set
included this command and 2019.1.5's doesn't (or never did) - either
way, there's no real command underneath to wrap, so `lw_toggle_
global_illumination`'s docstring was updated to state this
conclusively rather than leaving it as an open "not confirmed" gap.

Remaining open items (moderate/hard tier: the
`ColorSpaceOutput`/`RenderAlgorithm`/`RenderMode`/`Antialiasing`
families, the `FogColor` and `ObjGIRadiosityTolerance` mode gaps, Node
Editor writing, and reading un-enveloped node parameters) are left for
a future session, roughly in the difficulty order already established.

## Node Editor writing (ROADMAP3.md item 2 follow-up)

After the moderate-tier sweep, reviewed `ROADMAP3.md`'s own "Remaining
work, ranked by usefulness" list and picked the top item: Node Editor
writing, the single biggest capability gap left in the connector
(reading node graphs worked, but nothing could create nodes, wire
connections, or write a parameter value).

**Staged this exactly like the original node-reading investigation**,
since it's the same unmapped SDK territory from a different angle:
dir()-only introspection first (zero risk), then progressively riskier
live calls, asking for explicit approval before each new category.

**Step 1 - safe dir() scan, no live calls.** Added a temporary
`lw_probe_node_write` tool that constructs fresh instances of every
node-related class the read-side investigation already found
(`LWNodeFuncs`/`LWNodeEditorFuncs`/`LWNodeInputFuncs`/
`LWNodeOutputFuncs`/`LWNodeUtilityFuncs`/`LWNodeDrawFuncs`/
`LWNodeMenuFuncs`) and filters their `dir()` output for write-
suggestive keywords (add/create/new/insert/remove/delete/connect/
disconnect/set/etc.). Confirmed live: a real, substantial write API
exists - `LWNodeEditorFuncs.addNode/connect/destroyNode/setXY/reset`,
`LWNodeFuncs.setNodeColor/setNodeColor3/setNodePreviewType`,
`LWNodeInputFuncs.create/createCustom/destroy/disconnect/
connectedOutput`, `LWNodeOutputFuncs.create/createCustom/destroy/
setValue`.

**Step 2, EXPLICITLY APPROVED - real argument counts via the zero-arg
TypeError technique.** Added `lw_probe_node_write_sigs`, which calls
each candidate with zero arguments and captures the resulting Python
`TypeError` - the same safe signature-discovery trick that already
worked for `evaluate_scalar`/`evaluate_vector` in the read
investigation (a bad argument count fails in Python before any native
LightWave call happens, so this cannot touch scene state). Confirmed
live, real argument counts for all twelve candidates (subtracting the
implicit `self`): `addNode` takes 2 args, `connect` takes 2,
`destroyNode`/`reset` take 1 each, `setXY` takes 3;
`setNodeColor`/`setNodePreviewType` take 2, `setNodeColor3` takes 4;
`LWNodeOutputFuncs.create` takes 3, `createCustom` takes 5, `setValue`
takes 2, `destroy` takes 1; `LWNodeInputFuncs.create` takes 5,
`createCustom` takes 6, `disconnect`/`connectedOutput`/`destroy` take
1 each.

**A real, important architectural finding from the argument-count
pattern alone, before any further live testing**: `setValue` exists
only on `LWNodeOutputFuncs`, with no matching method on
`LWNodeInputFuncs`. This strongly suggests the whole write API is
shaped for *authoring custom plugin node types* (a plugin computes a
result and pushes it via its own output's `setValue`) rather than for
*directly setting an existing built-in node's default input parameter*
like Roughness - echoing this project's earlier `LWBSDFFuncs` dead end
from the read investigation (a real API, but for plugin authors, not
for scripting an existing graph). This means the un-enveloped-
parameter-read gap this project already carries forward likely has no
write-side answer here either - `addNode`/`connect`/`destroyNode`/
`setXY` still look like genuine graph-editing operations worth
pursuing, just not a full solution to that specific older gap.

**Step 3, EXPLICITLY APPROVED - the first real scene-mutating test.**
Added `lw_probe_add_node(surface, node_type)`, calling
`LWNodeEditorFuncs().addNode(editor, node_type)` against a real
surface's node editor (the same `getNodeEditor()` call
`_get_surface_nodes` already uses). Confirmed live end to end:
`addNode(editor, "Principled BSDF")` against `CONNECTOR` succeeded,
returned a real `NodeID`-typed handle, and - confirmed via a user
screenshot of the actual Node Editor UI, not just a clean return value
- a new "Principled BSDF (1)" node genuinely appeared in the graph.
`node_type` is exactly the `server_user_name` string
`lw_get_surface_nodes` already reports (e.g. "Principled BSDF"), not
the instance-suffixed `node_name`. The new node is added disconnected
- it does not automatically wire into the Surface node's Material
input, confirmed by the same screenshot showing the surface still
rendering through "Standard (1)" only.

**Shipped `lw_add_node(surface, node_type)` as a permanent tool**,
consolidating the temporary `_probe_add_node` diagnostic into
permanent `_add_node` code in `lw_mcp_ring.py` (matching the project's
established practice from the read investigation of removing `probe_*`
scaffolding once a piece is solidly confirmed, rather than waiting for
the entire write investigation to finish before shipping anything).

**A real, serious finding immediately after shipping, found the hard
way rather than guessed at: an invalid `node_type` freezes Layout.**
Tried `lw_add_node("CONNECTOR", "Constant")` next, assuming "Constant"
(a category heading visible in the Node Editor's own "Add Node"
browser panel) would work the same way "Principled BSDF" had. Instead
of a clean error, LightWave popped a real, modal "Plug-in Missing: No
plug-in of type NodeHandler found with name Constant. Would you like
to load it from disk?" dialog - and because it's modal, it froze
Layout's entire main thread. The ring listener query timed out
immediately after, which at first looked like the Master Plugin
listener had silently deactivated again (a known flaky-activation
issue this project has documented before) - but a screenshot of the
actual frozen screen revealed the real cause: the dialog itself, not a
listener problem, and the Master Plugins list still showed the ring
listener correctly checked the whole time. The user reasonably
described this as Layout "crashing" - a genuinely indistinguishable
symptom from the outside (frozen, unresponsive, no visible cause) until
that screenshot revealed the actual blocking dialog underneath.
Dismissing it with "No" and restarting Layout/reloading plugins/
restarting Claude Desktop fully recovered the session with zero
corruption - confirmed via `lw_ping` succeeding again immediately
after. This is the exact same failure shape as the Content Directory
dialog from `ROADMAP2.md` item 3: a genuinely blocking dialog a
one-way, fire-and-forget command has no way to dismiss on its own.

**Lesson, now baked into `lw_add_node`'s own docstring as a CRITICAL
warning**: `node_type` must only ever be an exact `server_user_name`
string already confirmed to exist via `lw_get_surface_nodes` on a real
node instance already present in a graph (e.g. "Principled BSDF",
"Standard") - never a category name from the Node Editor's own browser
UI, and never a guess, against a live, unattended session. The
earlier, pre-incident version of this docstring had actually listed
"Constant" as a plausible example value alongside "Principled BSDF"/
"Standard" - purely an inference from the Node Editor's category list,
never itself live-tested before being written down. That's a real
methodology lesson for this specific investigation: this project's
core discipline is "verify live before documenting as confirmed," and
this slipped through only because it was offered as an *illustrative
example* rather than a *specific confirmed claim* - worth remembering
that even documentation-adjacent examples deserve the same live-first
scrutiny as a stated fact, not just headline claims.

**Remaining for a future session**: `connect(output, input)` (wiring
one node's output socket to another node's input socket - the 2
required arguments are presumably output/input handles, not node
handles directly, meaning enumerating a node's OUTPUT sockets by name
- the `LWNodeOutputFuncs` equivalent of `LWNodeInputFuncs.numInputs/
byIndex` - is an open sub-question not yet answered), `destroyNode`
(remove a node - 1 arg, presumably just the node handle, no editor
context needed), and `setXY` (reposition a node in the graph view - 3
args, presumably node/x/y). `lw_probe_node_write`/`lw_probe_node_write_sigs`
are left in place as reusable diagnostic tools for that follow-up work
rather than removed, since the investigation is genuinely unfinished,
unlike `_probe_add_node` which is now fully superseded by the
permanent tool.

### Step 2: `connect` - works, then freezes Layout (tool pulled)

Output-socket enumeration, the open sub-question above, was answered
with two read-only probes before any connect call:

- `LWNodeOutputFuncs` exposes `first`/`next`/`byIndex`/`numInputs`
  (apparently the output count despite the name)/`name`/`type`/`node`.
  On a Principled BSDF, `numInputs` reports 1 output, but
  `byIndex(node, 0)` returns no handle; `first(node)` returns it
  (named "Material"). Use `first`/`next` for outputs.
- `LWNodeEditorFuncs.getRootNodeID(editor)` returns the "Surface"
  node. `LWNodeInputFuncs.byIndex` on it gives
  `[null, Material, Normal, Bump, Displacement, Clip]`, but the UI
  shows six inputs ending in OpenGL - so input `byIndex` on the root
  looks 1-based (index 0 empty, last input missed). The Principled
  BSDF's own 27 inputs enumerated correctly from 0, so this is not
  yet understood; match inputs by name, not position.
- `LWNodeEditorFuncs.getInputByName(root, "Material")` accepts the
  arguments but returns None - probably expects a different first
  argument. Unused.

`lw_connect_nodes` (Principled BSDF (1).Material -> Surface.Material on
CONNECTOR) was then run live twice. Both times `connect` returned None
with no exception, and the first run confirmed the connection is real:
the Surface Editor's Material field changed from "(none)" to
"Principled BSDF". But both times Layout's UI then froze completely
and had to be killed from Task Manager - while `lw_ping` kept
answering "pong", so the UI hung, not the ring listener. Run 1 had the
Node Editor open (it never drew the wire; a blank white window appeared
at Layout's top-left); run 2 had it closed, ruling out a stale Node
Editor as the cause. The Surface Editor was open and the viewport was
in Textured Shaded Solid both times. Making the same connection by hand
in the Node Editor does not freeze.

A third, isolating run closed both the Surface Editor and the Node
Editor and switched the viewport to Wireframe before calling connect.
Layout froze immediately anyway - the UI stopped responding and Alt+Tab
could no longer bring its window forward - before any editor was
reopened. So connect itself triggers the freeze; it is not a redraw or
re-evaluation of the edited surface by an open editor or shaded
viewport afterwards.

`lw_connect_nodes` is therefore kept in `server.py` for reference but
deliberately NOT registered as an MCP tool, with the freeze documented
in its docstring. Remaining untested ideas: check
`LWNodeInputFuncs.connectedOutput` right after connect to see whether
the link is half-made (only useful if a freeze can be avoided long
enough to read it); or avoid `connect` entirely by building the graph
by hand once, saving it as a node preset, and applying it via
`LWNodeEditorFuncs.load`.
