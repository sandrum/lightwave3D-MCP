# Roadmap 2: controlling more of Layout

Context: `ROADMAP.md`'s original plan is fully done except Modeler
reads (a confirmed, documented dead end - see `PLAN.md`/`STATUS.md`).
The connector can create items, run any of the ~800 native Layout
commands, read back scene/selection/camera/light/transform/surface/
hierarchy state (including bone chains), animate via keyframes, manage
item relationships (parent/target/goal/pole), and drive render
automation with real completion signaling. This doc picks up from
there: the goal now is breadth - controlling as many real facets of
Layout as possible, not just the increments that happened to come up
along the way.

Grounded in a real survey of `lwcommandport/layout/__init__.py`'s
command list (not guessed at) - see the notes under each item for what
was actually found there. Same working method as before applies: live
verification only test-fresh items, Cmd History for anything ambiguous,
and real caution around any SDK traversal call given this project's one
documented crash (`LWChannelInfo`/`nextGroup`).

## Priority order

1. **Item visibility / render-inclusion - DONE.** `IncludeObject`,
   `ExcludeObject`, `IncludeLight`, `ExcludeLight` share the same
   `(itemid)` signature quirk as the `ParentItem`/`TargetItem` family -
   wrapped with the same `_set_reference_item` helper (resolve both
   arguments to numeric IDs) rather than assuming it would just work.
   Confirmed live end to end, via the actual UI panels, not just Cmd
   History: `lw_include_light`/`lw_exclude_light`/
   `lw_include_object_light`/`lw_exclude_object_light` all shipped as
   `server.py` tools. This turns out to control which objects a light
   illuminates (Light Properties > Objects tab, or equivalently an
   object's own Item Properties > Lights tab - the same underlying
   data either way). Confirmed the relationship is genuinely
   bidirectional and stays in sync: setting it from the light's side
   (`IncludeObject`) and later toggling it from the object's side
   (`ExcludeLight`) both correctly updated the same shared list entry,
   visible identically on both panels, not two separate lists that
   happened to agree once. See `PLAN.md` "Light/object visibility
   linking" for the full writeup.

2. **Load real geometry into Layout - DONE.** Shipped `lw_load_object`,
   wrapping the previously-unused `LoadObject(filename)` command.
   Confirmed live end to end: loaded a small rig-part `.lwo`
   (`connector_01.lwo`, from LightWave's own bundled Genoma content) -
   `lw_get_scene_info` showed the new item by name, `lw_get_transform`
   returned a valid position, and a screenshot confirmed real triangle
   geometry visible in the viewport, not just a placeholder entry.
   `filename` must be an absolute path readable by the LightWave
   process - no relative-path or content-directory resolution was
   tested. This was the single biggest capability gap in "control as
   many facets of Layout as possible" up to this point - previously
   only Nulls could be created directly, and real geometry needed a
   separate Modeler round-trip. See `PLAN.md` "Load real geometry into
   Layout" for the full writeup.

3. **Scene file I/O - DONE.** Shipped `lw_save_scene_as` (wrapping
   `SaveSceneAs`, not the bare no-argument `SaveScene`, since a fresh
   unnamed scene has no known filename to save to yet), `lw_load_scene`,
   `lw_clear_scene`, and `lw_save_object`. Confirmed live end to end:
   a full save -> clear -> reload round trip correctly restored every
   item, and the saved `.lws` file's own content was checked directly
   (not just that a file appeared) to confirm it genuinely referenced
   the real items with their correct numeric IDs. One real UI gotcha
   found and documented: loading from outside LightWave's configured
   Content Directory pops a blocking confirmation dialog a one-way
   command can't dismiss (answering "No" still lets the load proceed).

   `lw_save_object` surfaced a genuinely new, unsolved wrinkle in this
   connector's numeric-ID story: for a real multi-layer object loaded
   via `lw_load_object`, neither `SelectItem(name)` NOR `SelectItem`
   with the object's regular numeric ID (from `lw_get_item_id`)
   reliably switched the current object the first time this session -
   a genuine manual click was needed once (revealing, via Cmd History,
   a second, differently-scoped `SelectItem` call LightWave's own UI
   sends first) before the object's regular ID became reliable on its
   own for the rest of the session. Shipped with the best available
   fix (resolve to numeric ID rather than trust the name, matching
   every other tool here) and an honest, documented limitation rather
   than a guessed formula for the scoped ID - see `PLAN.md` "Scene file
   I/O" for the full investigation and why baking in an unverified
   pattern from one data point would have been worse than admitting
   the gap.

4. **Camera property writes - DONE, with an honest open sub-item.**
   Shipped `lw_set_camera`, wrapping `ZoomFactor`/`LensFStop`/
   `ApertureHeight`/`ShutterOpen`/`ShutterEfficiency`/`RollingShutter`
   into one call (following `lw_set_keyframe`'s bundled-optional-params
   shape), using the same numeric-ID `SelectItem` pattern already
   proven for `lw_set_target`/`lw_set_parent`. Also extended
   `lw_get_camera_info` to read back the three shutter fields, needed
   to actually verify the writes rather than trust them blind.

   Confirmed live: `zoom_factor` and `aperture_height` take effect
   immediately. `f_stop` needed a real precondition discovered live -
   LightWave silently no-ops it and pops "This option only applies when
   Depth of Field is turned on" unless DOF is enabled first
   (`DepthOfField()`, confirmed to be a working toggle). The three
   shutter properties have the same kind of precondition (needs Motion
   Blur or Particle Blur enabled - confirmed via the same style of
   error, popped three times for the three properties in one call).

   **The Motion Blur gap is now resolved** (was open at first ship):
   `MotionBlur()` looked like an argument-less toggle - Camera
   Properties shows it as a button opening a sub-panel, not a checkbox
   - and calling it bare didn't make the precondition pass. The real
   cause was a bug in the bundled `lwcommandport` stub: `MotionBlur`
   was wrapped as `def MotionBlur(self): ...` with no way to pass an
   argument at all, silently making a real settable command
   (`MotionBlur(enable)`) look argument-less. Spotted via a stray
   "MotionBlur 1" in Cmd History from a manual UI click, fixed the same
   way as the earlier `Ring()`/`SetRenderDisplay()` fixes, confirmed
   live: `lw_run_command("MotionBlur", [1])` now correctly satisfies
   the precondition and all three shutter properties read back their
   previously-set values. See `PLAN.md` "Camera property writes" for
   the full investigation.

5. **Light property writes - DONE.** Shipped `lw_set_light`, wrapping
   `LightIntensity`/`LightColor`/`LightFalloffType`/`LightConeAngle`
   into one call, same shape and numeric-ID `SelectItem` pattern as
   `lw_set_camera`. Confirmed live: intensity and color take effect
   immediately.

   Found and fixed a real bug in the same family as `MotionBlur`:
   `LightFalloffType` was defined TWICE in the `lwcommandport` stub -
   once correctly taking a `type` argument, then immediately
   overwritten by a bare no-argument version right after it. Python
   silently keeps only the last definition, so the working version was
   completely unreachable until this was found by reading the stub
   file directly (not live testing) and fixed by deleting the
   duplicate. The write itself was then confirmed live via a UI
   screenshot ("Intensity Falloff: Inv Distance^2" appeared immediately
   after setting `falloff_type=2`) - but `lw_get_light_info`'s own
   `falloff` read remains a known-stale bug, unaffected by the write
   fix and not resolved this round (tried reading with a time argument
   the way every other animatable field here does; confirmed live that
   this does not help either - see `lw_mcp_ring.py`'s `_get_light_info`
   docstring). `falloff_type` also turned out to be a real LightWave
   constraint, not a bug: it only applies to Point/Spot lights,
   confirmed via LightWave's own error dialog when tried on a Distant
   light ("This option does not apply to the current light type").

   `LightVisibleToCamera`/`LightCastsShadows` were suspected of having
   the same missing-argument bug as `MotionBlur`, since calling either
   through `lw_run_command` with an argument raised the same shape of
   Python `TypeError`. Live verification proved that wrong: clicking
   their real checkboxes in the UI and checking Cmd History showed a
   bare `LightVisibleToCamera`/`LightCastsShadows` with no argument
   following - both are genuine argument-less toggles, and the
   `TypeError` was simply Python correctly rejecting an argument that
   was never valid to begin with. This is exactly the failure mode this
   project's live-verification norm exists to catch: a wrapper-level
   error alone doesn't tell you whether the *native* command takes an
   argument, only that our stub's current signature rejected the call.
   Also confirmed live: "Visible to Camera" itself is grayed out in the
   UI for Point lights - only Spot and Distant lights can use it,
   mirroring `falloff_type`'s Point/Spot-only restriction from the
   other direction. Neither toggle is settable to a known state or
   readable back, so `lw_set_light` deliberately does not wrap them;
   use `lw_run_command("LightVisibleToCamera", [])` /
   `lw_run_command("LightCastsShadows", [])` directly. See `PLAN.md`
   "Light property writes" for the full investigation.

   Together, items 4 and 5 close the biggest remaining "reads but
   can't write" gap in the connector.

6. **Multi-item / bulk selection investigation - DONE, mixed result.**
   `AddToSelection` was tested during earlier work and appeared to do
   nothing observable - `lw_get_selection` showed no change after
   calling it. Root cause: that earlier check used the unreliable
   `flags() & LWITEMF_SELECTED` read (documented as broken in
   `lw_get_selection`'s own docstring, returned the same value for
   every item), not `LWItemInfo().selected()`. Re-tested with the
   correct read and it works exactly as expected: shipped
   `lw_add_to_selection`/`lw_remove_from_selection`, confirmed live end
   to end (by name, through the numeric-ID resolver) that both
   correctly add/remove one item at a time from a real multi-selection
   without disturbing the rest, verified against both
   `lw_get_selection` and a Scene Editor screenshot showing both rows
   genuinely highlighted.

   **But this doesn't unlock the batch-write efficiency this item was
   hoping for.** Confirmed live: with two Objects selected this way,
   sending a write command (`AddPosition(1, 0, 0)`) only moved the one
   most recently touched by `AddToSelection` - the other, still
   `selected: true`, didn't move. Every command sent over the one-way
   Command Port acts on a single "current item" pointer, not the
   highlighted selection set as a whole - the same "current item"
   concept `_set_reference_item` already works around via `SelectItem`.
   These two tools are genuinely useful for building/inspecting a
   selection-state result (e.g. handing a user a specific multi-select
   for their own subsequent manual work), but every write tool in this
   connector still needs its own per-item loop - there's no shortcut
   for batching writes across multiple items in one call. See `PLAN.md`
   "Multi-item / bulk selection investigation" for the full writeup.

7. **IK chain configuration writes - DONE, plus a real bone-ID gap
   found and fixed along the way.** Shipped `lw_set_ik_options(item,
   goal_strength=, ik_fk_blending=)` and `lw_toggle_ik_flag(item, flag)`
   (`flag` is `"full_time_ik"` or `"unaffected_by_ik"`). Surveyed the
   stub first: `GoalStrength`/`IKFKBlending`/`GoalObjective`/`SoftIK`
   family/`IKInitialState`/`UseIKChainVals` were all already correctly
   wrapped with real arguments - no stub bug in this command family.
   `UnaffectedByIK`/`FullTimeIK`/`EnableIK`/`EnableDeformations`/
   `EnableMC` were the only bare zero-arg candidates, matching the
   shape that turned out to be a real bug three times this phase
   (`Ring`/`SetRenderDisplay`/`MotionBlur`) and a genuine toggle twice
   (`LightVisibleToCamera`/`LightCastsShadows`) - checked the two named
   in this item's own description live rather than assuming either way.

   Confirmed live on a real bone in an actual chain (`Bone1` under
   `BoneTestObject`, goaled to `lightwavemcp_test_object_out`):
   `goal_strength`/`ik_fk_blending` took effect immediately (Motion
   Options showed "Goal Strength: 0.9" / "IK/FK Blending: 30.0%"
   right after sending 0.9 / 0.3 - the same 0.0-1.0-fraction-as-percent
   convention as `lw_set_camera`'s `shutter_efficiency`).
   `UnaffectedByIK`/`FullTimeIK` are both confirmed genuine
   argument-less toggles (Cmd History logged them bare after clicking
   the real checkboxes) - no stub fix needed, and no way to set/read a
   known state, so `lw_toggle_ik_flag` flips rather than sets, the same
   honest limitation as the Light toggles. Real precondition found:
   "Full-time IK" is grayed out until the item has a Goal Object
   assigned - LightWave auto-checks it as a side effect of the goal
   assignment itself, no separate command needed.

   **The real discovery: bones have no name this connector could
   resolve at all.** `lw_get_item_id`/`_resolve_item_id` only search
   Objects/Lights/Cameras (`_find_item`'s item-type list never included
   `LWI_BONE`) - a bone genuinely could not be targeted by name through
   any tool here, IK-related or not. Fixed two ways: `_get_bones` (in
   `lw_mcp_ring.py`) now reports each bone's own numeric "id" via
   `lwsdk.itemid_to_str()`, exposed through `lw_get_hierarchy`; and
   `_resolve_item_id` now passes a purely numeric `item` string straight
   through instead of always trying to look it up by name. Confirmed
   live end to end: `lw_get_hierarchy` reported `Bone1`'s id as
   `"40000000"`, matching Cmd History's own log of a real manual click
   on that bone in the Scene Editor (`"SelectItem 40000000"`) exactly -
   bones live in their own ID range, distinct from Object/Light/Camera's
   10000000/20000000/30000000. Both new tools were then re-tested with
   that real numeric ID and worked correctly. See `PLAN.md` "IK chain
   configuration writes" for the full investigation.

8. **Surface/material writes - DONE, plus a real methodology lesson
   about this project's own crash-detection norm.** Shipped
   `lw_set_surface(surface, color=, diffuse=, luminosity=,
   specularity=, glossiness=, reflection=, transparency=, smoothing=)`,
   the first write in this connector to go through the read-path's
   Master plugin (`LWComRing`) instead of the one-way Command Port -
   `SurfaceEditor` in the command list just opens the UI panel, it
   doesn't take settable arguments, so `lwsdk.LWSurfaceFuncs()` (the
   same class `lw_get_surface_info` already reads through) via its
   `setFlt()` method was the only real path. A temporary `lw_introspect`
   diagnostic tool (since removed) confirmed `LWSurfaceFuncs` genuinely
   exposes `setFlt`/`setColorVMap`/`setImg`/`setMaterial`/`setInt`/
   `setShadingModel`/`setTex` as real bound methods before writing
   anything against them.

   **The first live test appeared to hang Layout forever** - the debug
   log logged the incoming request and then went silent permanently for
   that call, the same signature as this project's one previously
   confirmed crash (`LWChannelInfo`/`nextGroup`, see `PLAN.md`).
   Reproduced twice, ruled out a full app crash (LightWave's own UI
   stayed fully responsive both times, confirmed via screenshot, and a
   subsequent `lw_ping` succeeded immediately), and shipped `setFlt` as
   a permanently-disabled stub rather than guess at a fix - the same
   "confidently wrong code is worse than an honest gap" call this
   project has made before.

   **That diagnosis turned out to be wrong**, caught before this was
   ever finalized: a standalone regex test (not just re-reading the
   same live symptom again) revealed the real bug was transport-level,
   not `setFlt` at all. `_TOPIC_RE`'s original pattern used a GREEDY
   `(.+)`, which matches from the first `{` to the *last* `}` in the
   whole raw message - harmless for every earlier command, whose
   payloads never contained braces, but `set_surface`'s JSON-encoded
   argument does. The regex silently parsed a real `set_surface`
   message's topic as garbage (not `"MCP"`), so `_handle_query` - let
   alone `setFlt()` - was never even reached the first time this was
   tested; there was never a hang to diagnose. Fixed by making the
   regex's first group non-greedy, then fully reverted the disabled
   stub and re-verified live from scratch: `diffuse=0.5` alone (Surface
   Editor showed 50.0%), then `color=[1,0,0]` + `glossiness=0.8`
   together (a genuinely red color swatch and "Glossiness 80.0%"),
   both matching `lw_get_surface_info`'s read-back exactly.

   Real, reusable lesson for this project's own methodology: a
   debug-log signature that looks exactly like the one documented crash
   (message logged, then silence) does not by itself prove the same
   failure mode - the silence here had a completely different, mundane
   cause. The fix was to write the smallest possible standalone
   reproduction (a three-line regex test) rather than trust a plausible
   diagnosis from the live symptom alone. See `PLAN.md` "Surface/
   material writes" for the full investigation.

9. **Keyframe/envelope reading** - `lw_get_transform` only reports the
   evaluated value at one point in time (now via the live playhead, see
   ROADMAP.md item 9); there's no way to see the actual keyframe
   structure of an item's channels - which frames have keys, what
   interpolation type each uses. Real value for inspecting existing
   animation rather than just sampling it. Last on purpose: this is
   `LWChannelInfo`-adjacent territory, the exact SDK area that has
   already crashed Layout outright once with no Python exception (see
   PLAN.md "LWChannelInfo crash"). Do this only with the same staged,
   cautious probing bone traversal got (ROADMAP.md item 11) - confirm
   the mechanism exists and a single call is safe before writing any
   real loop - once the rest of this list is solid.
