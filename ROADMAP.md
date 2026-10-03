# Roadmap: what to build next

Context: the core connector is done and verified live - Layout writes
(`lw_create_null`, `lw_run_command`) and Layout reads (`lw_ping`,
`lw_get_scene_info`, via the `LWComRing`-based `lw_mcp_ring.py`) all work
end to end. See `PLAN.md` for how that was proven and
[GETTING_STARTED.md](GETTING_STARTED.md) for setup. This doc lists the realistic next increments, in the order I'd
tackle them, with why.

## 1. More Layout read queries - DONE

Shipped and confirmed live: `lw_get_selection`, `lw_get_camera_info`,
`lw_get_light_info`. Found via three rounds of live introspection
(temporary `lw_mcp_diag.py`/`diag2`/`diag3` probe plugins, since the
static SDK docs don't cover exact method signatures and have already
been shown to be out of sync with this build):

- `LWItemInfo().selected(item)` is the reliable per-item selection
  signal - `flags() & LWITEMF_SELECTED` was tested and does **not**
  reflect actual selection state despite the name (returned the same
  value for every item regardless of what was actually selected).
- `LWCameraInfo`/`LWLightInfo`'s animatable properties (focal length,
  f-stop, fov, zoom, color, intensity, range) need a second `time`
  argument beyond the item ID - confirmed working with `time=0.0`.
  Non-animated properties (`resolution`, `falloff`, `type`) take just
  the item ID.
- `LWLightInfo().color()` returns a `PCore::Vector` SWIG object, not
  directly JSON-serializable - converted via `.x`/`.y`/`.z`.

**Known limitation, carried forward - SOLVED, see item 9:** these tools
used to evaluate animatable values at `time=0.0` (scene start) instead
of the live playhead position. Fixed via `lwsdk.LWTimeInfo()`.

**Descoped this round** (see items below): item transform
(position/rotation/scale) and surface/material info. Transform needs
`LWChannelInfo` group/channel traversal with unclear sentinel values and
the same time-query problem; surface needs `SURF_*` constants that
weren't found in the introspection pass. Promoted to their own roadmap
items below rather than guessed at.

## 1b. Item transform query (position/rotation/scale) - DONE

Turned out not to need `lwsdk.LWChannelInfo()`/`nextGroup` at all - that
path is confirmed to crash Layout (see `PLAN.md`), but tracking down
NewTek's real SDK docs (etwright.org/lwsdk, since none ship with this
install) found that `LWItemInfo` already has a direct `param(item,
param_type, time)` call for exactly this. Real-world third-party Python
plugin code confirmed the Python calling convention. Shipped as
`lw_get_transform`, confirmed live against a real item including after
moving it (not just reading defaults) - see `PLAN.md`.

## 1c. Surface/material info query - DONE

Shipped as `lw_get_surface_info`, using `lwsdk.LWSurfaceFuncs()`
(`byName`, `getFlt`) plus the `SURF_*` channel constants. Calling
conventions confirmed via the same real-world Python plugin code used
for 1b. Confirmed live end to end against a real object with a real
surface (built a unit box in Modeler, loaded it into Layout, queried
its "Default" surface) - see `PLAN.md` for the full values returned.
One minor open question: the `smoothing` value's sign/scale under the
newer Principled BSDF shading model isn't fully decoded yet, but the
mechanism itself is proven safe.

## 2. Modeler write path - DONE

Shipped and confirmed live: `modeler_run_command`, mirroring
`lw_run_command` using the previously-unused `Modeler` class in
`lwcommandport/modeler/__init__.py` (booleans, extrude tools, mesh
cleanup, skinning, cloning/arrays, file ops). Sent `command="new"`,
Modeler's title bar changed from "Unnamed" to "Unnamed 1", confirming a
real new object layer was created.

Two things that didn't go as expected, both documented in `PLAN.md`:

- Enabling Modeler's Command Port really is a different mechanism from
  Layout's, as predicted - `lwsdk.ModCommand()` + executing
  `"ENABLECOMMANDPORT"` (see `lw_enable_modeler_command_port.py`, using
  port 9736). But loading the script via Add Plugins only *registers*
  it as a "Modeling Command" - it doesn't auto-run like Layout's Generic
  single-shot scripts do. It has to be separately invoked via Utilities
  > Additional afterward.
- `ModCommand.execute()`'s reported result code is unreliable - it said
  "failure" both for a free port and for one already
  successfully bound. Confirmed via a UDP bind-conflict test that it
  actually worked regardless. Third confirmed SDK/binding bug found this
  project, after `LWMessageFuncs.info()` and `IMaster.__init__`'s
  argument counts.

## 4. Animation helpers built on what already works - DONE

Shipped `lw_set_keyframe(name, frame, position, rotation, scale)`,
wrapping `SelectItem`/`GoToFrame`/`Position`/`Rotation`/`Scale`/
`CreateKey` into one call. Confirmed live on a fresh Null: keyed frame 0
at (0,0,0) and frame 30 at (5,5,5), then scrubbed to frame 15 and saw an
interpolated (3.104, 3.104, 3.104) - real proof the item animates between
keys, not just that two writes succeeded. See `PLAN.md` for the full
writeup, including a documented rotation-units mismatch (degrees on
write vs. radians on read).

## 5. Modeler read path - RESEARCHED, confirmed blocked (no known workaround)

Investigated thoroughly and live-tested; see `PLAN.md` for the full
writeup. Summary: Modeler has no Master-plugin/`LWComRing` equivalent at
all (confirmed via the local install's file layout and NewTek's SDK
docs - Modeler's Python plugin architecture is `CommandSequence`-only).
The natural workaround - invoke a custom `CommandSequence` plug-in by
name over the network Command Port, the same way built-in commands like
"new" already work via `modeler_run_command` - does not work. Confirmed
three independent ways, including against NewTek's own bundled sample
plug-in (not just this project's code), that the network Command Port
only reaches native/compiled commands, not Python-registered ones. This
is the same failure mode that ruled out Layout's first read-path attempt,
except Modeler has no `LWComRing`-style escape hatch.

**Status: blocked with no known path forward**, short of NewTek adding a
Modeler equivalent of `LWComRing`/Master plugins, or documentation
surfacing a mechanism this investigation didn't find. A real but limited
substitute exists: reading saved `.lwo` files directly from disk (bypasses
Modeler's Python API, only reflects saved state).

Effort already spent: thorough (SDK docs research + live testing with
three independent methods). Not recommending further time here without
new information (e.g. a NewTek support answer or a newer LightWave
version's SDK).

## 6. Render / camera automation with completion signaling - DONE

Shipped `lw_render_frame`, `lw_render_scene`, `lw_abort_render`,
`lw_set_camera_resolution`, and `lw_get_render_status`. The last one is
the real deliverable here: a real completion signal instead of
guessing after firing a one-way render command, built on
`lwsdk.IFrameBuffer` (NewTek's "Render Display" plug-in architecture -
found via NewTek's official docs, not live probing), which gets real
open()/close() callbacks from the render engine itself. Requires a
one-time manual step to select the plug-in as the active Render Display
(also now scriptable - see STATUS.md item 1's fix below; the "no
networked way to do this" claim here turned out to be based on a
wrapped-method bug, not a real limitation). Live-verified twice: once
by hand via lw_run_command before the tools were loaded, once fully
through the new tools (set resolution to 640x360, triggered a render,
watched rendering go true -> false with matching resolution/
frame_count). See PLAN.md for the full writeup.

**Multi-frame RenderScene progress tracking - now tested, see below.**

## 7. Item hierarchy query (parent/target/goal/pole) - DONE

Added ahead of the original list, prompted by a real use case: rigging
on top of an object that's already parented to something else requires
knowing the existing hierarchy first. Shipped `lw_get_hierarchy`, using
`LWItemInfo.parent()`/`target()`/`goal()`/`pole()` (found via NewTek's
official docs, same pattern as items 1b/1c/6). Live-verified against a
real parent/child relationship, not just an empty scene - see PLAN.md.
One real finding along the way: `ParentItem` via `lw_run_command` did
NOT actually reparent items as tested (name-as-argument didn't take);
the relationship had to be set through the UI to test the read side.
That was a real gap for anyone wanting to *write* parenting through
this connector - see item 8 below for the fix. Bone-chain traversal
(bones within an object) was explicitly out of scope at the time - no
boned object existed yet to verify traversal safely against - see item
11 below for the eventual fix.

## 8. Reparenting write path (the item 7 gap) - DONE

Root-caused and fixed. The failure wasn't specific to `ParentItem` -
`TargetItem` (same `(itemid)` signature) failed identically, silently
no-op'ing rather than erroring or popping a dialog. First ruled out
several wrong theories live: no modal requester appears (checked via
screenshot), it's not a "needs a UI redraw to flush a pending
scene-graph rebuild" thing (waited 15+ seconds and across multiple
polls, still null), and an apparent one-off "success" turned out to be
the user manually dragging items in Scene Editor while testing, not the
command actually working (caught by testing a second, untouched pair
of Nulls, which stayed unparented).

The real root cause, found via Utilities > Commands > Cmd History
(logs the literal native command LightWave runs for any UI action):
a real manual reparent via Motion Options logs as `ParentItem
10000000` - a plain numeric ID, not a name - while this connector's
name-based attempts logged as `TargetItem 0`, proving the argument
silently coerces to a bogus/no-op ID when it can't parse a name.
`SelectItem` is the one exception in this command family that really
does resolve names internally (confirmed by its own Cmd History
entries showing the correctly-resolved ID). These per-item numeric IDs
turned out to already be sequential and inspectable: `ParentTest` was
`10000000`, `ChildTest3` created five Nulls later was `10000004`.

The missing piece to convert a name into that ID from Python had
actually been sitting unused since early in this project: an old
`_introspect()` diagnostic dump (`_mcp_diag_response.json`) lists
module-level `lwsdk.itemid_to_str()` / `lwsdk.str_to_itemid()` helpers
that were never connected to this problem until now. Shipped as
`lw_get_item_id(name)` (new `get_item_id` query in `lw_mcp_ring.py`)
and `lw_set_parent(child, parent)` (wraps resolve-parent-id / select-
child-by-name / `ParentItem(id)` into one call). Confirmed live on a
completely fresh, untouched pair of Nulls (`ParentTest3`/`ChildTest3`)
with `lw_get_hierarchy` correctly showing the new relationship
afterward - not just re-checking the pair that had already been
manually parented by hand.

`TargetItem`/`GoalItem`/`PoleItem` share the exact same root cause
(same argument convention, same command family) but aren't wrapped in
their own convenience tools yet - `lw_get_item_id` already fixes the
underlying problem for them; only a thin wrapper analogous to
`lw_set_parent` is missing, would-be quick follow-up if IK rigging
through this connector is needed.

**Follow-up (same session-plus-one), a second related bug found while
building that follow-up:** shipped `lw_set_target`/`lw_set_goal`/
`lw_set_pole`, wrapping `TargetItem`/`GoalItem`/`PoleItem` the same way
as `lw_set_parent`. Live-testing `lw_set_target` against a real Camera
surfaced a second, distinct bug in the original wrapper shape:
`SelectItem(name)` - trusted to pick which item is being modified,
since it reliably resolves Object names - does NOT reliably do the
same for Camera/Light. A name-based attempt to target the Camera
silently applied the target to an unrelated, already-current Object
instead, no error. Cmd History of the real manual action (select
Camera, Motion Options, set Target Item) showed the working sequence
selects the Camera by its own numeric ID, not its name - and revealed
each item-type category has its own ID range (Objects `10000000+`,
Lights `20000000+`, Cameras `30000000+`). Fixed by resolving BOTH
arguments to numeric IDs before sending, never trusting SelectItem's
name resolution at all. Confirmed live for all three categories
(Object/Light/Camera) after the fix, with `lw_set_parent` re-verified
to still work (no regression). See PLAN.md "Second finding" for the
full writeup, including a process-level lesson: a Claude Desktop
restart can leave a stale `server.py` process running, meaning a
just-fixed tool can still exhibit the old bug until a true full
restart (verified via the process list) actually takes effect.

**`lw_set_goal`/`lw_set_pole` live-verified (immediate follow-up):**
turned out not to need bones or a true IK chain to test at all -
`goal()`/`pole()` are generic per-item properties in the SDK
(`lw_get_hierarchy` already queried them for every item type from the
start), so both were confirmed by setting them on a plain Null
(`ChildTest3`, which already had a parent and target set from earlier
testing) and reading back `lw_get_hierarchy` - `goal`/`pole` both
showed the correct new relationship alongside the existing
`parent`/`target` on the same item. All four `lw_set_*` tools are now
fully confirmed live, closing this out completely - no remaining
untested tool in this family.

## 9. Live playhead time query (the item 1 limitation, carried since the start) - DONE

Solved. The original `_introspect()` diagnostic (used to find
`LWCameraInfo`/`LWLightInfo` back in item 1) never searched for
time/frame-related keywords at all - a real gap in that search, not
evidence the SDK lacked a current-time query. A widened keyword search
(`Time`/`Frame`/`Current`/`Play`/`Clock`/`Tick`) found
`lwsdk.LWTimeInfo()`, a plain-attribute class in the same simple style
as `LWSceneInfo` (already proven safe elsewhere in this connector) -
`.time` is the live playhead position in seconds, exactly the unit
every animatable call already expected (they used to hardcode `0.0`
here). `lw_get_camera_info`/`lw_get_light_info`/`lw_get_transform` now
use it instead of the hardcoded value, and a new `lw_get_current_time`
tool exposes it directly.

Confirmed live with a real animated item, not just reading the
mechanism's plausibility: keyframed a fresh Null (`TimeTest`) at frame
0 (position 0,0,0) and frame 30 (position 10,10,10), moved the
playhead to frame 15 via `GoToFrame`, and `lw_get_transform` correctly
returned an interpolated position (~6.21 on each axis, matching
LightWave's default spline easing curve shape - not a naive linear
midpoint of 5.0, and consistent with the exact same easing shape seen
in the original item-4 keyframe test scaled 2x) instead of the
frame-0 default. `lw_get_current_time` independently confirmed
`frame: 15.0, time: 0.5` (30fps) at the same moment.

This required rediscovering, mid-session, that Layout itself had been
restarted at some point without redoing setup step 1 (Command Port
enable) - every symptom (writes silently not appearing, the Ring
listener endlessly attach/detach-cycling without ever receiving an
event) looked exactly like the already-documented Master Plugin
activation flakiness, and several remove/re-add cycles were spent on
that before checking the title bar for `(CP: 9735)` and noticing it
was missing. Worth checking that first next time symptoms look like
the known flakiness but persist past 2-3 retries.

## 10. Multi-frame RenderScene progress tracking (STATUS.md item 1) - DONE

Confirmed live and working, with two real bugs found and fixed along
the way. `frame_count` does correctly climb across a multi-frame
`lw_render_scene()` render rather than jumping straight to done or
stalling - the original open question from item 6. Two corrections to
`lw_mcp_render_monitor.py`'s original assumptions, both found live:

1. `open()`/`close()` fire once for the WHOLE render session, not once
   per frame (item 6's `frame_count` logic had assumed the latter). The
   real per-frame signal is `IFrameBuffer.begin()`, found by reading
   NewTek's own bundled sample plug-in - not previously overridden in
   this project's code at all.
2. `begin()` itself fires once per **enabled render buffer** per
   frame (Render Properties > Buffers), not once per frame alone -
   confirmed live: `Final_Render`+`Alpha` both enabled produced 8
   `begin()` calls for a 4-frame render; `Final_Render` alone produced
   a clean 4. Also fixed: `frame_count` was continuing to climb across
   separate renders within one Layout session instead of resetting.

Bonus, unrelated finding from the same investigation: `SetRenderDisplay`
turns out to be scriptable after all
(`lw_run_command("SetRenderDisplay", ["LW MCP Render Monitor"])`) -
this project's own item 6 write-up had concluded there was no networked
way to do this, based on a wrapped `lwcommandport` method missing its
argument (fixed, same class of bug as the `Ring()` fix). See PLAN.md
"Multi-frame RenderScene progress tracking" for the full investigation,
including real environment trouble (a mid-session computer restart, a
locked plug-in file, a red herring that looked exactly like the
documented Master Plugin flakiness but wasn't) that took as much
effort as the actual technical question.

With this, STATUS.md's item 1 is closed. Remaining: bone chain
traversal (needs a rigged object) and the confirmed Modeler-reads dead
end.

## 11. Bone chain traversal within an object (item 7's deferred piece) - DONE

Closed out with real caution, not routine extension - this project has
a documented case (`LWChannelInfo`/`nextGroup`, see PLAN.md) of an SDK
traversal call reproducibly crashing Layout outright, with no Python
exception. Staged the risk down before writing any real loop: first
confirmed `LWI_BONE` exists at all (`hasattr(lwsdk, "LWI_BONE")`), then
a single `first()`/`next()` call pair against a real bone chain via a
temporary, non-looping probe tool, and only wrote the actual bounded
`while` loop (matching the same pattern already proven safe for
Object/Light/Camera, plus a generous iteration cap as an extra margin)
once that came back clean.

Also found, unplanned: bones don't need a real mesh object to test
against at all - `AddBone`/`AddChildBone` attach directly to a Null
(confirmed live: `Bone1`/`Bone2` added to a Null named
`BoneTestObject`, visible in Scene Editor exactly like real
parent/child nesting). This made the whole investigation far cheaper
than the "get or build a rigged object" framing in STATUS.md assumed -
no Modeler mesh-building detour was needed.

`lw_get_hierarchy` now reports a `bones` list on each object's entry
(only when non-empty) with the same name/parent/target/goal/pole shape
as every other item. Confirmed live end to end: `Bone1.parent` ==
`"BoneTestObject"` (the host), `Bone2.parent` == `"Bone1"` - correctly
resolved by name, matching the real chain exactly.

Bonus context from an unrelated side investigation this same session:
checked whether a different, newer LightWave-MCP project (targeting
LightWave 2025.0.3, found locally as `lightwave-mcp-master-2025`) had
solved Modeler reads or offered anything else to leverage. It hadn't -
no read-path mechanism for either Layout or Modeler at all (pure
fire-and-forget command sending), and it still carries both bugs this
project found and fixed (`Ring()`'s doubled-brace bug, `SetRenderDisplay`
missing its argument). Modeler's command surface was also confirmed
byte-for-byte identical between the 2019.1.5 and 2025.0.3 SDKs - real,
independent evidence for item 5's dead-end conclusion, not just this
project's own testing.

With this, every roadmap item is done except item 5 (Modeler reads),
which remains a documented, confirmed dead end - the only item left on
STATUS.md's list.

## Recommended order

1. ~~Layout read queries (selection, camera/light)~~ - done
2. ~~Modeler write path~~ - done
3. ~~Item transform query (1b) and surface/material query (1c)~~ - done
4. ~~Animation helper tools~~ - done
5. ~~Modeler read path research~~ - researched, confirmed blocked
6. ~~Render/camera automation~~ - done
7. ~~Item hierarchy query~~ - done
8. ~~Reparenting write path~~ - done
9. ~~Live playhead time query~~ - done
10. ~~Multi-frame RenderScene progress tracking~~ - done
11. ~~Bone chain traversal within an object~~ - done

Rationale: started with the cheapest, lowest-risk extensions of what's
already proven (1, done), then opened the next major surface using a
pattern already validated once (2, done). Item 3 turned out to need a
real docs lookup rather than more live probing - once that was done
(see PLAN.md), both sub-items shipped quickly and safely. Item 5 was
investigated thoroughly and turned out to be a real dead end, not
just an unexplored option - documented rather than left open. Item 4
built convenience on top of proven native commands and was the fastest
item yet, confirming the project's core mechanisms are now solid. Item
6 needed one more real docs lookup (the Frame Buffer/Render Display
plug-in architecture) rather than guessing at a polling scheme. Item 7
was added mid-stream from a real user need rather than pre-planned, and
surfaced a real new gap (parenting via `lw_run_command` doesn't work)
that item 8 came back to close. Item 8 is the project's clearest
example yet of live ground-truth beating guesswork: several plausible
theories (modal dialog, needs a UI redraw, needs more elapsed time)
were tested and ruled out live before Cmd History - comparing what a
real working UI action actually logs against what this connector's
failed attempts logged - revealed the real root cause in one step.
Item 9 closed out the oldest open limitation in the whole project
(carried since item 1) by fixing the original introspection's real
gap - it simply never searched for the right keywords - rather than
concluding the SDK lacked the capability. Item 10 answered a
long-standing "untested" note from item 6 and found two real bugs in
the process (a wrong assumption about which callback fires per frame,
and a counter that didn't reset across renders) - proof that "probably
fine, just untested" items in this project keep turning out to have
real substance once actually checked, not just a formality to confirm.
Item 11 closed the last real open item on STATUS.md's list by staging
the risk down in cautious, verifiable steps rather than writing the
real traversal loop on faith - exactly the discipline this project's
one real crash (`LWChannelInfo`/`nextGroup`) should have taught from
the start. With this, every roadmap item is done except item 5
(Modeler reads), which remains a documented, confirmed dead end.

