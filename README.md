# Claude ↔ LightWave 2019 MCP connector (proof of concept)

Built on LightWave 2019's official Command Port (`lwsdk.LWCommandPort`).
**Both writes and reads are proven working end to end**, confirmed live
through the real `lw_ping` (returned `"pong"`) and `lw_get_scene_info`
(correctly returned the live scene's actual items) MCP tools - see
`PLAN.md` for the full log, including several confirmed dead ends before
each working mechanism was found, and `ROADMAP.md` for what's been built
and what's explicitly out of scope.

## What works right now

**Layout writes**
- `lw_create_null` - sends `AddNull`, confirmed to create a real item.
- `lw_load_object(filename)` (ROADMAP2.md item 2) - loads a real mesh
  object (`.lwo`) into the scene via the native `LoadObject` command,
  closing this connector's biggest capability gap up to this point:
  previously only Nulls could be created directly in Layout, and real
  geometry needed a separate Modeler round-trip. Confirmed live:
  loading a small rig-part `.lwo` produced real triangle geometry
  visible in the viewport and a working item (`connector_01` appeared
  in `lw_get_scene_info`, `lw_get_transform` returned a valid
  position). `filename` must be an absolute path readable by the
  LightWave process.
- **Scene file I/O** (ROADMAP2.md item 3) - `lw_save_scene_as(filename)`,
  `lw_load_scene(filename)`, `lw_clear_scene()`, `lw_save_object(name,
  filename)`. Confirmed live end to end: saved a real scene, verified
  its file content referenced the actual items with correct numeric
  IDs, cleared the scene, reloaded it, and confirmed every item came
  back. Loading from outside LightWave's configured Content Directory
  used to pop a blocking "Change Content Directory?" dialog a one-way
  command can't dismiss (answering "No" still let the scene load, but
  needed a human present) - **now solvable**, see
  `lw_set_content_directory` below (ROADMAP3.md item 1).
  `lw_save_object` has a real, documented limitation: for a freshly
  loaded multi-layer object (via `lw_load_object`), `SelectItem` by
  name or by its regular numeric ID may not switch the current object
  the *first* time this session - a genuine manual click was needed
  once before automation-only selection became reliable for that
  object. See `PLAN.md` "Scene file I/O" for the full investigation.
- `lw_run_command` - generic passthrough to any of the ~800 native
  commands in `lwcommandport/layout/__init__.py`. One-way, no
  confirmation LightWave accepted it, just that it was sent.
- `lw_set_content_directory(path)` (ROADMAP3.md item 1) - wraps the
  native `ContentDirectory(dirname)` command. Confirmed live this fully
  closes the Content Directory dialog gap noted above: called with the
  target path, then reloaded the exact scene/path combination that
  previously triggered the dialog - it loaded silently instead, with
  `lw_get_scene_info` confirming every item came back intact. Call once
  per session before loading from a path outside whatever Content
  Directory LightWave started with.
- `lw_set_keyframe(name, frame, position, rotation, scale)` - wraps the
  common by-hand animation sequence (select, go to frame, set
  transform, create key) into one call. Confirmed live: two keyframes
  on a Null produce real interpolated motion, not just two writes.
  Note: `rotation` here is in **degrees** (Layout's UI/command-line
  convention); the read-side `lw_get_transform` reports rotation in
  **radians** (the SDK's convention) - a real unit mismatch to be aware
  of, not a bug.
- `lw_add_to_selection(item)`, `lw_remove_from_selection(item)`
  (ROADMAP2.md item 6) - add/remove one item from a real multi-item
  selection without disturbing the rest. Confirmed live end to end (by
  name, through the numeric-ID resolver): `lw_get_selection` correctly
  showed two Objects `selected: true` simultaneously, matching a Scene
  Editor screenshot with both rows genuinely highlighted. The earlier
  suspicion that `AddToSelection` "does nothing" was a broken-read
  artifact (checking `flags() & LWITEMF_SELECTED`, not
  `LWItemInfo().selected()`), not a real bug. **Real limitation
  confirmed live:** this does not enable batch writes - a write command
  sent afterward (`AddPosition`) only affected the single most
  recently-touched item, not every item shown as selected. Every write
  tool in this connector still needs its own per-item loop; these two
  tools are for representing/building a selection state, not batching
  writes. See `PLAN.md` "Multi-item / bulk selection investigation" for
  the full investigation.

**Layout reads** (all via `LWComRing`, see Setup step 2)
- `lw_ping`, `lw_get_scene_info` - round trip + live item list.
- `lw_get_selection` - every item's name/type/selected state.
- `lw_get_camera_info`, `lw_get_light_info` - resolution, focal length,
  f-stop, FOV, zoom, shutter open/efficiency/rolling-shutter skew /
  type, falloff, color, intensity, range.
- `lw_get_transform` - position/rotation/scale via `LWItemInfo.param()`.
- `lw_get_surface_info` - color, diffuse, luminosity, specularity,
  glossiness, reflection, transparency, smoothing via `LWSurfaceFuncs`.
- **Node graphs** (ROADMAP3.md item 2) - `lw_get_surface_nodes(surface)`
  lists every node in a surface's graph (confirmed live: even a
  "Standard"-material surface never manually node-edited already has an
  implicit "Surface"/"Input"/"Standard (1)" graph - LightWave's nodal
  architecture underlies every surface). `lw_get_node_inputs(surface,
  node)` lists a node's real parameter names (confirmed live: all 27
  real Principled BSDF parameters, matching the UI exactly) - but not
  values, since `LWNodeInputFuncs.evaluate_scalar/evaluate_vector` both
  need shading context this connector can't supply outside a render.
  `lw_get_node_channel(surface, node, channel)` reads a parameter's
  actual keyframe data - confirmed live end to end (Roughness read back
  as `0.1`, matching the UI's "10.0%") - but **only for parameters that
  already have an envelope**; a never-touched parameter has no value
  reachable this way, a real, confirmed, honestly-documented limitation.
  See `PLAN.md` "Node Editor / PrincipledBSDF nodes" for the full
  nine-step staged investigation, including a genuine dead end
  (`LWBSDFFuncs` turned out to be a shader-plugin-authoring API, not a
  way to read an existing node's parameters).
- `lw_get_hierarchy` - every item's parent, plus IK target/goal/pole,
  by name. Useful before rigging on top of something already parented.
  **Now also walks bone chains within each object** (`LWItemInfo.first(
  LWI_BONE, object)`/`next()`) - confirmed live and safe against a real
  2-bone chain. `LWChannelInfo`/`nextGroup` also crashed Layout outright
  once (see `PLAN.md` "LWChannelInfo crash") - since resolved, see
  `lw_get_channels` below. Bones don't need a real mesh object to test
  against - `AddBone`/`AddChildBone` attach directly to a Null.
- `lw_get_channels(name)` (ROADMAP2.md item 9) - an item's real keyframe/
  envelope structure: which channels exist (Position.X, Rotation.H,
  etc.) and every keyframe's frame, value, and interpolation shape.
  Closes the last gap `lw_get_transform`'s single-point-in-time
  evaluation always had. Root-caused this project's one confirmed real
  crash in the process: the original `LWChannelInfo().nextGroup()` crash
  had passed an item's own ID as the argument, when
  `LWItemInfo().chanGroup(item)` was the correct one all along - found
  via an unrelated introspection dump, confirmed safe via the same
  staged, explicitly-approved, one-call-at-a-time discipline
  `lw_get_hierarchy`'s bone traversal used. Confirmed live two ways: a
  static Null showed all 9 channels with one implicit key each at frame
  0 (real LightWave defaults); a Null keyframed at frames 0 and 30
  showed the real multi-key data, and surfaced a genuinely new,
  previously-unobservable behavior - every channel gets an automatic
  extra key at the scene's end frame, and a channel whose value never
  actually changed only gets that bonus key, not a redundant real one.
  `shape` is the raw `LWKEY_SHAPE` integer (no confirmed name mapping
  established). See `PLAN.md` "Keyframe/envelope reading" for the full
  staged investigation.
- `lw_get_current_time` - the live playhead's frame and time (seconds).

  **Formerly a known limitation, now solved:** camera/light/transform
  animatable values (`lw_get_camera_info`/`lw_get_light_info`/
  `lw_get_transform`) used to be hardcoded to `time=0.0` (scene start)
  instead of LightWave's live playhead. Fixed via `lwsdk.LWTimeInfo()`
  - confirmed live: keyframed a Null at frame 0/frame 30, moved the
  playhead to frame 15 with `GoToFrame`, and `lw_get_transform`
  correctly returned the interpolated frame-15 position instead of the
  frame-0 default. See `PLAN.md` for the full investigation.

**Render / camera automation**
- `lw_set_camera_resolution(width, height)` - wraps `FrameSize` (a
  scene-wide render global, not literally per-camera despite the name).
- `lw_set_camera(camera, zoom_factor=, f_stop=, aperture_height=,
  shutter_open=, shutter_efficiency=, rolling_shutter=)` (ROADMAP2.md
  item 4) - the write-side counterpart to `lw_get_camera_info` (which
  was read-only until now). Same numeric-ID `SelectItem` fix as the
  item-relationship tools. Confirmed live: `zoom_factor`/
  `aperture_height` take effect immediately; `f_stop` requires Depth of
  Field enabled first (`DepthOfField()`, a toggle - LightWave pops "This
  option only applies when Depth of Field is turned on" and silently
  no-ops otherwise); `shutter_open`/`shutter_efficiency`/
  `rolling_shutter` need Motion Blur or Particle Blur enabled
  (`lw_run_command("MotionBlur", [1])`) - this was fixed after shipping:
  the bundled `lwcommandport` had wrapped `MotionBlur` with no way to
  pass an argument at all, the same class of bug as `Ring()`/
  `SetRenderDisplay()`. Confirmed live: with the fix, `MotionBlur(1)`
  correctly satisfies the precondition and all three shutter properties
  read back their previously-set values. See `PLAN.md` "Camera property
  writes" for the full investigation.
- `lw_set_light(light, intensity=, color=, falloff_type=, cone_angle=)`
  (ROADMAP2.md item 5) - the write-side counterpart to
  `lw_get_light_info`. Same shape and numeric-ID `SelectItem` pattern as
  `lw_set_camera`. Confirmed live: `intensity`/`color` take effect
  immediately. `falloff_type` write confirmed live via UI screenshot,
  but only applies to Point/Spot lights (LightWave pops "This option
  does not apply to the current light type" for Distant); its own
  read-back through `lw_get_light_info` is a known-stale bug, unrelated
  to the write (see below). Fixed a real duplicate-definition bug found
  in the stub: `LightFalloffType` was defined twice, and Python silently
  kept only the argument-less second copy, making the real one
  unreachable. Deliberately does **not** wrap `LightVisibleToCamera`/
  `LightCastsShadows` - both were suspected of having the same
  missing-argument bug as `MotionBlur`, but live verification (clicking
  their real checkboxes and checking Cmd History) proved they're genuine
  argument-less toggles with no way to set or read a known state; use
  `lw_run_command` directly for those two. Also confirmed live:
  "Visible to Camera" is disabled in the UI for Point lights, only
  usable on Spot/Distant. See `PLAN.md` "Light property writes" for the
  full investigation.
- `lw_render_frame(frame=None)`, `lw_render_scene()`, `lw_abort_render()`
  - one-way, fire-and-forget like every command here.
- `lw_get_render_status()` - the actual point of this group: real
  completion state (`rendering: true/false`, resolution, `frame_count`)
  read from `lwsdk.IFrameBuffer` callbacks (see Setup step 3), not a
  guess based on elapsed time. Confirmed live: resolution set, render
  triggered, status correctly went `true` -> `false` with matching
  numbers. **Multi-frame `RenderScene` progress tracking is now
  confirmed live too** - `frame_count` correctly climbs across a
  multi-frame render rather than stalling or jumping straight to done.
  One real subtlety found along the way: the real per-frame signal is
  `IFrameBuffer.begin()` (`open()`/`close()` only fire once for the
  whole render session), and `begin()` fires once per **enabled render
  buffer** per frame (Render Properties > Buffers), not once per frame
  alone - divide `frame_count` by the number of enabled buffers if an
  exact frame count matters. Also fixed a real bug: the counter was
  continuing to climb across separate renders in the same session
  instead of resetting. See `PLAN.md` for the full investigation.
- **Render Globals / GI quality settings** (ROADMAP3.md item 3) -
  `lw_set_render_globals(threads=, tile_size=)`, `lw_toggle_global_
  illumination()`, `lw_set_gi_interpolated(enabled)`,
  `lw_set_gi_radiosity_tolerance(degrees)`. Closes the biggest remaining
  "can trigger renders but can't configure them" gap. `threads`/
  `tile_size` confirmed live with zero preconditions - `threads` even
  auto-unchecked "Automatic Multithreading" as a side effect.
  `lw_toggle_global_illumination` confirmed live as a genuine
  argument-less toggle for "Enable GI". `lw_set_gi_interpolated(1)`
  confirmed live to check the "Interpolated" checkbox. `lw_set_gi_
  radiosity_tolerance` hit a real, unresolved precondition - LightWave's
  error dialog references a "Monte Carlo Interpolated" mode this
  install's Type dropdown never actually offered as a selectable option
  - shipped anyway since the argument itself is confirmed correct,
  documented honestly rather than hidden.

  **Real operational finding**: sending several of these tools together
  in one parallel batch caused `RadiosityInterpolation` to log the wrong
  value and `ObjGIRadiosityTolerance` to vanish from Cmd History
  entirely - a UDP packet-reordering/loss artifact of the one-way
  Command Port under concurrent load, not a bug in the tools (re-sending
  the same call alone, sequentially, worked correctly). Verify important
  settings via a screenshot/read after a batch of parallel writes rather
  than trusting every "sent" response at face value. See `PLAN.md`
  "Render Globals / GI / quality settings" for the full investigation.
  Bonus: `SetRenderDisplay` turns out to be scriptable after all
  (`lw_run_command("SetRenderDisplay", ["LW MCP Render Monitor"])`) -
  a wrapped-method bug, not a real LightWave limitation.
- **Scene environment/atmosphere** (ROADMAP3.md item 4) -
  `lw_set_backdrop(color=, zenith_color=, sky_color=, ground_color=,
  nadir_color=)`, `lw_toggle_gradient_backdrop()`,
  `lw_toggle_volumetrics()`, `lw_set_fog(fog_type=, min_distance=,
  max_distance=, min_amount=, max_amount=, color=)`. `Backdrop()`
  (despite the central-looking name) turned out to just be a panel-opener
  like `SurfaceEditor` - opening Effects > Backdrop logged it bare, not a
  setting. `GradientBackdrop` confirmed a genuine toggle;
  `BackdropColor`/`SkyColor` confirmed live with real color swatches
  (red, then green). Fog lives under Render Properties > Volumetrics
  (not the "Legacy Volumetrics" Effects tab, which turned out to be an
  unrelated plugin-based system - Ground Fog/HyperVoxels/PixieDust) -
  `EnableVolumetrics` confirmed a genuine toggle that gates the *entire*
  Fog panel as a precondition, same shape as DOF/Motion Blur; `FogType`
  confirmed live with enum value `1` = "Linear".

  **Real, unresolved gap**: `FogColor` is accepted and logged cleanly in
  Cmd History both before and after satisfying the Volumetrics
  precondition, but the swatch never visibly updates - unlike every
  other color command tested this item. Shipped with this explicitly
  flagged as unconfirmed rather than proven working. See `PLAN.md`
  "Scene environment/atmosphere" for the full investigation.
- **Deeper bone rigging** (ROADMAP3.md item 6) - `lw_set_bone(item,
  strength=, rest_length=, rest_position=, rest_rotation=,
  weight_map_name=, falloff_type=, min_range=, max_range=)` and
  `lw_toggle_bone_flag(item, flag)` (`flag` is `"active"` or
  `"limited_range"`). `item` must be a bone's numeric ID (from
  `lw_get_hierarchy`'s bone `id` field). Found the real UI location - a
  "Bones for &lt;object&gt;" panel reachable via the Properties button
  while a bone is current, distinct from both Motion Options (IK only)
  and the generic Modify tab. Confirmed live: `strength=0.5` showed
  "Strength: 50.0%"; `rest_length=2` showed "Rest Length: 2m";
  `falloff_type=2` (object-wide, not per-bone) changed "Inverse Distance
  ^16" to "Inverse Distance ^2"; `BoneActive`/`BoneLimitedRange`
  confirmed genuine argument-less toggles - a real bone defaulted to
  inactive, confirming a bone can exist and be parented while still
  off. `weight_map_name` sent cleanly but couldn't be visually confirmed
  since this test rig's bones have no real mesh/vmap to match against.
  The muscle/joint-compensation family was surveyed but not wrapped this
  pass. See `PLAN.md` "Deeper bone rigging" for the full investigation.

**Modeler**
- `modeler_run_command` - same pattern as `lw_run_command` but for
  Modeler's separate Command Port mechanism (see Setup step 4).
  Confirmed live: `command="new"` created a real new object layer.
- Modeler **reads are a confirmed dead end** - `modeler_ping` and
  `modeler_get_object_info` will always time out. Modeler has no
  `LWComRing`-equivalent, and the network Command Port only reaches
  native/compiled commands, not Python-registered ones (confirmed three
  independent ways, including against NewTek's own bundled sample
  plug-in). See `PLAN.md`/`ROADMAP.md` item 5 - not worth retrying
  without new information (NewTek support, or a newer SDK version).

**Item relationships** - `lw_set_parent(child, parent)`,
`lw_set_target(item, target)`, `lw_set_goal(item, goal)`,
`lw_set_pole(item, pole)`, `lw_get_item_id(name)`
- fixed a real gap: `ParentItem`/`TargetItem`/`GoalItem`/`PoleItem`
  silently no-op when given an item's name instead of the plain numeric
  ID LightWave's Command Port actually expects for these specific
  commands. Two related bugs, both root-caused via Cmd History
  (Utilities → Commands → Cmd History, which logs the literal native
  command any UI action runs): (1) these commands need a numeric ID
  argument, not a name - `SelectItem` is the one exception that really
  does resolve names; (2) `SelectItem(name)` itself is only reliable
  for Objects - Camera/Light need `SelectItem` called with their own
  numeric ID too, not their name, to correctly become the "current
  item" this command family reads. Each item-type category has its own
  ID range (Objects `10000000+`, Lights `20000000+`, Cameras
  `30000000+`). `lw_get_item_id` resolves a name to its numeric ID via
  `lwsdk.itemid_to_str()`; the four `lw_set_*` tools resolve BOTH
  arguments to IDs and never trust `SelectItem`'s name resolution.
  Confirmed live: `lw_set_parent`/`lw_set_target` work for all three
  item categories (Object/Light/Camera); `lw_set_goal`/`lw_set_pole`
  confirmed too - no bones/true IK chain needed to test, since
  `goal()`/`pole()` are generic per-item properties, set and read back
  correctly on a plain Null - see `PLAN.md` for the full investigation.

**IK chain configuration** (ROADMAP2.md item 7) -
`lw_set_ik_options(item, goal_strength=, ik_fk_blending=)`,
`lw_toggle_ik_flag(item, flag)` (`flag` is `"full_time_ik"` or
`"unaffected_by_ik"`). Confirmed live on a real bone: `goal_strength`/
`ik_fk_blending` take effect immediately (Motion Options showed "Goal
Strength: 0.9" / "IK/FK Blending: 30.0%" right after sending them - the
0.0-1.0-as-percent convention already known from `lw_set_camera`'s
`shutter_efficiency`). `full_time_ik`/`unaffected_by_ik` are confirmed
genuine argument-less toggles (Cmd History logged them bare after
clicking the real checkboxes) with no way to read a known state back,
so `lw_toggle_ik_flag` flips rather than sets - same limitation as
`lw_set_light`'s unwrapped `LightVisibleToCamera`/`LightCastsShadows`.
"Full-time IK" is grayed out until a Goal Object is assigned
(`lw_set_goal`) - LightWave auto-checks it as a side effect of the goal
assignment, no separate command needed.

Found and fixed a real gap along the way: **bones could not be
targeted by name through this connector at all**, for reading or
writing - `lw_get_item_id`/`_resolve_item_id` only search Objects/
Lights/Cameras, never bones (a separate `LWI_BONE` traversal only
`_get_bones` performs). Fixed by having `_get_bones` report each bone's
own numeric `id` (now visible via `lw_get_hierarchy`) and by having
`_resolve_item_id` pass a purely numeric `item` string straight through
instead of always searching for it by name - so a bone's ID, once known
via `lw_get_hierarchy`, can be fed directly into any tool built on
`_resolve_item_id`. Confirmed live: bones have their own ID range,
`40000000+`, distinct from Object/Light/Camera's
`10000000+`/`20000000+`/`30000000+` - `lw_get_hierarchy` reporting
`Bone1`'s id as `"40000000"` matched Cmd History's own log of a real
manual click on that bone exactly. See `PLAN.md` "IK chain
configuration writes" for the full investigation, including a
suggestive (not yet confirmed) link to item 3's unexplained
`SelectItem 40010000`.

**Surface/material writes** (ROADMAP2.md item 8) -
`lw_set_surface(surface, color=, diffuse=, luminosity=, specularity=,
glossiness=, reflection=, transparency=, smoothing=)` - the write-side
counterpart to `lw_get_surface_info`, and the first write in this
connector to go through the read-path's Master plugin (`LWComRing`)
instead of the one-way Command Port, since there's no native
`SurfaceEditor` command - it just opens the UI panel - and
`lwsdk.LWSurfaceFuncs()`'s `setFlt()` is the only real path. Confirmed
live end to end against a real surface (`CONNECTOR`, on a loaded
`.lwo`): `diffuse=0.5` alone showed "Diffuse 50.0%" in Surface Editor;
`color=[1,0,0]` + `glossiness=0.8` together showed a genuinely red
color swatch and "Glossiness 80.0%", both matching
`lw_get_surface_info`'s read-back exactly.

The first live attempt appeared to hang Layout forever (the exact
debug-log signature of this project's one other confirmed crash,
`LWChannelInfo`/`nextGroup`) - reproduced twice, but Layout's own UI
stayed fully responsive both times and `lw_ping` recovered immediately,
ruling out a full crash. **That diagnosis turned out to be wrong**: the
real bug was `_TOPIC_RE`, the regex `lw_mcp_ring.py` uses to parse
`"{MCP} ..."` messages - its original GREEDY pattern matched from the
first `{` to the *last* `}` in the whole message, so `set_surface`'s
JSON-encoded argument (which has its own `{`/`}`) corrupted the topic
match and got silently dropped before `setFlt()` was ever reached, on
*both* "confirmed" attempts. Caught by writing a standalone regex test
rather than re-trusting the same live symptom, fixed by making the
regex non-greedy, then fully re-verified live from scratch. See
`PLAN.md` "Surface/material writes" for the complete investigation -
worth reading as a methodology lesson on its own, not just for the
feature.

**Light/object visibility linking** (ROADMAP2.md item 1) -
`lw_include_light(light, obj)`, `lw_exclude_light(light, obj)`,
`lw_include_object_light(obj, light)`, `lw_exclude_object_light(obj,
light)` - wraps `IncludeObject`/`ExcludeObject`/`IncludeLight`/
`ExcludeLight`, controlling which objects a light illuminates (Light
Properties → Objects tab / Item Properties → Lights tab - the same
underlying data either way, confirmed to stay in sync from both
sides). Same numeric-ID fix as the item-relationship tools above.
Confirmed live end to end via the actual UI panels, not just Cmd
History: adding, and toggling Include ↔ Exclude, both correctly
updated the same list entry rather than creating duplicates.

**Per-object render-visibility flags** (ROADMAP3.md item 5) -
`lw_toggle_object_visibility(item, flag)` (`flag` is one of
`"unseen_by_rays"`, `"unseen_by_camera"`, `"unseen_by_radiosity"`,
`"unaffected_by_fog"`) and `lw_set_alpha_channel_mode(item, mode)`.
Genuinely different from the light/object illumination linking above -
this is about whether an object is visible to the camera, reflection/
refraction rays, radiosity, or fog at all, not which light illuminates
it. The four toggle flags confirmed live to be genuine argument-less
toggles (Cmd History logged each bare after clicking the real Object
Properties > Render buttons) - no way to read them back, so the tool
flips rather than sets, same limitation as the Light/IK toggles.
`UnseenByAlphaChannel` turned out to be a real find: it's wrapped bare
in the stub like its four siblings, but Cmd History showed it actually
takes an argument (a real missing-`*args` bug, same class as
`Ring`/`SetRenderDisplay`/`MotionBlur`, fixed here) - and despite its
name, it isn't a boolean at all, it's the Object Properties "Alpha
Channel" dropdown's underlying enum command (confirmed live: `0` = "Use
Surface Settings", `1` = "Constant Value", the only two options this
install's dropdown offered). Shipped as its own tool rather than folded
into the boolean toggles, where it would have been misleading. A UI
freeze occurred during live testing of these two tools, not clearly
attributable to either (both had already logged cleanly beforehand) -
see `PLAN.md` "Per-object render-visibility flags" for the honest
writeup.

## Setup

**1. Enable the Command Port (once per Layout session)**

Utilities → Plugins → Add Plugins → select `lw_enable_command_port.py`.
It runs automatically on load (it's a "single-shot" plug-in) - the title
bar should change to show `(CP: 9735)`.

**2. Enable the read path (once per Layout session)**

Utilities → Plugins → Add Plugins → select `lw_mcp_ring.py`. Then
Utilities → Master Plugins → "Add Layout or Scene Master" dropdown →
select "LW MCP Ring4" (listed as "Claude MCP Command Port Ring listener")
→ make sure its "On" checkbox is ticked. Unlike step 1, this one needs
both the Add Plugins step and this activation step.

If `lw_ping` times out even after this, LightWave's Master Plugin
activation is known to be flaky in this environment - remove the
listener from the Master Plugins list, re-add the file via Add Plugins,
and reselect it from the dropdown. This has been needed after nearly
every fresh Layout launch throughout development; treat it as expected
friction, not a bug.

**3. Enable render completion signaling (once per Layout session,
optional - only needed for `lw_get_render_status`)**

Utilities → Plugins → Add Plugins → select `lw_mcp_render_monitor.py`
(needs re-adding each fresh Layout session, same as `lw_mcp_ring.py` -
the Render Display dropdown can visually keep showing "LW MCP Render
Monitor" as a leftover preference even when the underlying plug-in
class isn't actually loaded this session, which looks like it worked
but silently doesn't). Then Render → Render Properties → General tab →
"Render Display" dropdown → select "LW MCP Render Monitor" - or script
it: `lw_run_command("SetRenderDisplay", ["LW MCP Render Monitor"])`
(this command does take an argument over the network; an earlier
version of this doc claimed it didn't, based on a wrapped-method bug
now fixed). If Add Plugins reports the plug-in can't be added/is
locked, it's because it's currently the active Render Display - switch
the display away first (e.g. to "Image Viewer"), reload, then switch
back.

**4. Enable Modeler's Command Port (once per Modeler session, optional -
only needed for `modeler_run_command`)**

Modeler uses a different mechanism than Layout - not
`LWCommandPort().enable()`, but `ModCommand()` + executing a command
called `ENABLECOMMANDPORT`. In Modeler: Utilities → Plugins → Add
Plugins → select `lw_enable_modeler_command_port.py` (this only
*registers* it - Modeler treats single-file plug-ins differently than
Layout). Then Utilities → Additional → find and click
`lw_enable_modeler_command_port` in the list to actually run it. Title
bar should change to show `(CP: 9736)`. Note: the script may report
"failure" internally (a real bug in this SDK build's `ModCommand.
execute()` return code, not an actual failure) - trust the title bar,
not any printed result.

**5. Install the MCP server's dependency**

```
pip install "mcp[cli]" --break-system-packages
```

**6. Point Claude Desktop at `server.py`**

In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lightwave": {
      "command": "python",
      "args": ["C:\\Users\\sandr\\IdeaProjects\\LightwaveMCP\\server.py"]
    }
  }
}
```

Restart Claude Desktop.

**7. Test**

With Layout running and steps 1-2 done, ask Claude to create a Null
item, then ask it to ping LightWave or get scene info. Check Layout -
the Null should appear immediately, and the ping/scene-info replies
should reflect the live scene.

If you ever see writes silently stop working (success responses but
nothing appears in Layout), suspect a hung or duplicate Layout process
first - Windows can end up running more than one `Layout.exe`
simultaneously, with the MCP query listener bound to a stale one while
the visible window is a different, disconnected process. Check the
Scene Editor (Utilities → Editors → Scene Editor) against query
responses to catch this; a clean restart of all Layout processes
reliably fixes it.

## Files

- `lw_enable_command_port.py` — run once inside Layout. Enables Layout writes. Working.
- `lw_mcp_ring.py` — Master plug-in enabling Layout reads via `LWComRing` (scene info, selection, camera/light/transform/surface/hierarchy/render-status/item-id queries). Needs both Add Plugins and Master Plugins activation. Working.
- `lw_mcp_render_monitor.py` — Render Display plug-in (`lwsdk.IFrameBuffer`) providing real render completion signaling for `lw_get_render_status`. Needs Add Plugins plus manual selection as the active Render Display. Working.
- `lw_enable_modeler_command_port.py` — run once inside Modeler (Add Plugins, then Utilities > Additional). Enables Modeler writes. Working.
- `lw_mcp_modeler_query.py` — Modeler read-path attempt. Works when invoked from inside Modeler's own UI, but confirmed unreachable over the network - kept for the record, not usable as-is. See `ROADMAP.md` item 5.
- `server.py` — MCP server Claude Desktop launches. Layout writes/reads, animation, render/camera automation, hierarchy queries, and Modeler writes all work; Modeler reads do not (see above).
- `lwcommandport/` — NewTek's official Command Port client (copied from the LightWave install), with one real bug fixed in `Ring()` (see `PLAN.md`).
- `lw_mcp_master.py`, `lw_mcp_query.py` — two earlier, unsuccessful attempts at solving Layout reads, kept for reference/history. Do not load.
- `lw_socket_master.py` — superseded very first draft. Do not load.
- `lw_mcp_diag.py`, `lw_mcp_diag2.py`, `lw_mcp_diag3.py`, `lw_diag_modeler_cp.py` — throwaway live-introspection probe plug-ins, not needed going forward.
- `PLAN.md` — full build log: what's verified, what failed, what to try next.
- `ROADMAP.md` — what's been built, in order, and why; the current state of every planned increment.
