# Roadmap 3: node graphs, render quality, scene environment, and deeper rigging

Context: `ROADMAP2.md` is fully done (all 9 items). The connector now
covers scene management, item creation/loading, hierarchy and IK,
camera/light/surface writes, bulk selection, and keyframe/envelope
reading, on top of everything `ROADMAP.md` shipped. This doc picks up
from there: another real survey of `lwcommandport/layout/__init__.py`'s
full ~824-command list (not guessed at), specifically hunting for
coherent categories of native commands with zero coverage so far, not
just incremental extensions of what already exists.

Same working method as every prior roadmap: live verification for
anything ambiguous, Cmd History as ground truth when a command's
argument shape or precondition is unclear, and the same live-test
discipline that's already found four separate missing-`*args` stub bugs
(`Ring`/`SetRenderDisplay`/`MotionBlur`/`LightFalloffType`) and one
transport bug (`_TOPIC_RE`) across the first two roadmaps - assume
nothing about a command's real behavior until it's been exercised
against a live Layout session. Several items below list argument-less
toggle candidates; per this project's established finding, some of
these turn out to be real stub bugs (missing `*args`) and some turn out
to be genuine toggles (`LightVisibleToCamera`/`LightCastsShadows`/
`UnaffectedByIK`/`FullTimeIK`) - never assume either way without
checking Cmd History against a real UI click first.

## Priority order

1. **Content Directory management - DONE, closes a real documented
   gap.** Shipped `lw_set_content_directory(path)`, wrapping the native
   `ContentDirectory(dirname)` command (confirmed correctly wrapped with
   `*args` in the stub, unlike several commands found broken in prior
   roadmaps).

   Confirmed live that this fully closes `ROADMAP2.md` item 3's
   documented limitation: loading a scene or object from outside
   LightWave's configured Content Directory used to pop a blocking
   "Change Content Directory?" dialog that a one-way command couldn't
   dismiss, needing a human to click "No" every time. Reproduced the
   exact scenario that originally triggered it (loading
   `lightwavemcp_test_scene.lws` from a Temp path outside the default
   Content Directory), then called `lw_set_content_directory` with that
   same Temp path and reloaded - the dialog did not appear, the scene
   loaded silently, and `lw_get_scene_info` confirmed every item came
   back intact. Call this once per session before loading from any path
   outside whatever Content Directory LightWave started with.

   `ContentTypeDirectory(type, dirname)` (a per-content-type sub-path)
   is now also shipped, as `lw_set_content_type_directory(content_type,
   dirname)`. Found the real UI - Preferences > Paths tab, a list of
   buttons ("Scenes"/"Objects"/"Images"/etc.) each opening a path
   editor for that content type. Confirmed live that `content_type` is
   the literal panel label string (tested with `"Objects"`): sending
   `ContentTypeDirectory("Objects", "TestObjDir")` changed the
   "Objects" button's own label to "TestObjDir" - these buttons double
   as a live display of the current sub-path rather than fixed
   captions, so no separate read-back is needed. Reverting with
   `("Objects", "Objects")` correctly restored the original label. The
   other content-type strings are inferred from the visible panel
   labels, not independently tested. `CreateContentPath`/
   `RecentContentDirs` remain unwrapped - both still look like one-shot
   UI actions (opening a dialog/menu) rather than pure setters worth
   automating. See `PLAN.md` "Content Directory management" and
   "Follow-up sweep: closing the easy/moderate open items" for the full
   investigation.

2. **Node Editor / surface & light node graphs, especially PrincipledBSDF
   nodes - DONE for reading, a real limitation found and honestly
   documented.** Shipped three tools: `lw_get_surface_nodes(surface)`
   (list every node in a surface's graph), `lw_get_node_inputs(surface,
   node)` (list a specific node's parameter names), and
   `lw_get_node_channel(surface, node, channel)` (read a parameter's
   actual keyframe data).

   Confirmed via this roadmap's own command-list survey up front: there
   is NO native Command Port command for node graph editing at all -
   this needed the SDK's node API directly, the same architectural shift
   `ROADMAP2.md` item 8 required for flat surface properties, one level
   deeper. A live `dir(lwsdk)` scan (zero risk, no SDK calls) confirmed a
   real, substantial node API exists in this build:
   `LWNodeFuncs`/`LWNodeEditorFuncs`/`LWNodeInputFuncs`/
   `LWNodeOutputFuncs`/`LWNodeUtilityFuncs`, plus `LWBSDFFuncs`
   specifically - which turned out to be a *shader-plugin-authoring* API
   (building custom BSDF rendering math), not a way to read an existing
   node's UI parameters, a real dead end for this specific goal spotted
   before any code was written around it.

   Explored in nine separate, explicitly-approved staged steps (the same
   discipline `ROADMAP2.md` items 8/9 established for genuinely new SDK
   territory - dir()-only recon first, then one live call at a time,
   asking before each new untested call): `LWSurfaceFuncs().
   getNodeEditor(surf)` (confirmed safe), `LWNodeEditorFuncs`'s
   `numberOfNodes`/`nodeByIndex` to enumerate nodes (found a surprise:
   even a plain "Standard"-material surface already has an implicit
   3-node graph - LightWave's nodal architecture underlies every
   surface, not just hand-built ones), `LWNodeInputFuncs`'s
   `numInputs`/`byIndex` to enumerate a node's 27 real parameter names
   (exact match to the UI panel) - but `evaluate_scalar`/
   `evaluate_vector` both failed needing 2 more arguments than expected,
   a real dead end for reading a parameter's *value* this way (these
   look like render-time calls needing shading context this connector
   can't supply outside an active render).

   **The real path mirrors `ROADMAP2.md` item 9's keyframe discovery
   almost exactly.** `LWSurfaceFuncs().chanGrp(surf)` is a surface's own
   channel group; one `nextGroup()` hop reaches a "Nodes" container; a
   second `nextGroup()` hop within "Nodes" reaches a specific node's own
   group; `nextChannel()` within that group finds a parameter - but
   **only once a human has explicitly added an envelope to it** (via the
   Graph Editor or the node's own envelope button). Confirmed live:
   `chanGrp(surf)` alone and an un-enveloped node's group both
   legitimately have zero channels (never a crash, always confirmed
   empty first), and the exact channel appears the instant an envelope
   is added - then `channelEnvelope()`/`nextKey()`/`keyGet()`, the
   identical already-proven-safe calls from item 9, correctly read back
   the real value (`0.1`, matching the UI's "10.0%" for Roughness
   exactly).

   **Confirmed, honest limitation**: only *enveloped* parameters are
   readable today - a fresh, never-touched Principled BSDF parameter has
   no value reachable through this connector, only a name. Writing
   (creating envelopes/keys, or connecting nodes) was out of scope for
   this pass, following the same "confirm read before write" discipline
   item 8 used. See `PLAN.md` "Node Editor / PrincipledBSDF nodes" for
   the complete nine-step investigation.

3. **Render Globals / GI / quality settings - DONE for the confirmed
   subset, with two honest open findings.** Shipped
   `lw_set_render_globals(threads=, tile_size=)`,
   `lw_toggle_global_illumination()`, `lw_set_gi_interpolated(enabled)`,
   and `lw_set_gi_radiosity_tolerance(degrees)`. Closes the biggest
   remaining "can run renders but can't configure them" gap - this
   connector could only trigger renders and read completion before this.

   `RenderThreads`/`RenderTileSize` confirmed live with zero
   preconditions - `tile_size` directly updated "Render Tile Size" (64 ->
   32); `threads` updated "Multithreading Limit" AND correctly
   auto-unchecked "Automatic Multithreading" as a side effect, cleaner
   than `lw_set_camera`'s Motion Blur precondition ever was.
   `EnableRadiosity0` confirmed live as a genuine argument-less toggle
   for the "Enable GI" checkbox (Cmd History logged it bare, repeatedly).
   `RadiosityInterpolation(1)` confirmed live to check the "Interpolated"
   checkbox correctly.

   `ObjGIRadiosityTolerance` (targets "Angular Tolerance") hit a real,
   unresolved precondition: LightWave's own error dialog says it "only
   applies when Global Illumination Mode is set to Monte Carlo
   Interpolated" - but this install's "Type" dropdown only ever offered
   one choice, "Monte Carlo", with no distinct "Monte Carlo Interpolated"
   mode reachable to select, even after enabling GI and Interpolated
   mode. Shipped anyway (the argument itself is confirmed correct),
   following `lw_set_camera`'s Motion-Blur-gated-shutter-properties
   precedent, with the gap honestly documented rather than papered over.

   **`EnableRadiosity1` - DONE, definitively resolved.** Calling it live
   popped LightWave's own error dialog: "Unknown command:
   'EnableRadiosity1'" - proof, not a guess, that this command doesn't
   exist in LightWave 2019.1.5's command parser at all, despite being
   defined in the bundled lwcommandport stub (likely generated against a
   different LightWave version). Left permanently unwrapped since
   there's nothing real underneath it. See `PLAN.md` "Follow-up sweep:
   closing the easy/moderate open items" for the full investigation.

   The whole `RenderAlgorithm`/`RenderMode`/
   `Antialiasing` family/`ColorSpaceOutput` family were surveyed but not
   tested or wrapped this pass - no clear UI correspondence was found
   for most of them under VPR (LightWave's other render engines/AA
   models may expose them differently), and this item's core stated goal
   (render thread/tile/GI quality control) was already substantially
   met. Left for a future pass rather than guessed at.

   **Real operational finding, not specific to any one command**: sending
   several `lw_run_command`-style calls in one parallel tool-call batch
   risks UDP packet loss/reordering - confirmed live when four commands
   sent together resulted in `RadiosityInterpolation` logging the wrong
   value (`0` instead of the `1` actually sent) and
   `ObjGIRadiosityTolerance` not appearing in Cmd History at all,
   while the other two calls in the same batch worked correctly.
   Re-sending the same `RadiosityInterpolation(1)` call alone,
   sequentially, worked perfectly - confirming this was a delivery
   artifact of the one-way, unordered UDP Command Port under
   concurrent load, not a bug in any of the new tools. Worth remembering
   for any future work that bundles several related settings into one
   call or one batch of parallel calls - verify the end result via a
   screenshot/read rather than trusting every "sent" response
   uncritically when several went out at once.

4. **Scene environment/atmosphere - DONE for backdrop and fog, one real
   unresolved color-write gap found.** Shipped `lw_set_backdrop(color=,
   zenith_color=, sky_color=, ground_color=, nadir_color=)`,
   `lw_toggle_gradient_backdrop()`, `lw_toggle_volumetrics()`, and
   `lw_set_fog(fog_type=, min_distance=, max_distance=, min_amount=,
   max_amount=, color=)`.

   Found live that `Backdrop()` (despite its central-looking name) is
   just a panel-opener, matching `SurfaceEditor`/`ItemProperties` -
   opening Effects > Backdrop itself logged a bare `Backdrop`, not a
   setting to wrap. `GradientBackdrop` confirmed a genuine argument-less
   toggle. All five backdrop colors confirmed live: `BackdropColor`/
   `SkyColor` first (red, then green), then `ZenithColor`/`GroundColor`/
   `NadirColor` together (yellow/magenta/cyan), all exact matches.

   `EnableVolumetrics` confirmed a genuine toggle, and confirmed to gate
   the *entire* Fog panel as a real precondition - Fog settings sent
   before enabling it are silently accepted (no error, logged cleanly in
   Cmd History) but have zero visible effect, exactly the DOF/Motion
   Blur precondition shape from earlier roadmaps. `FogType` confirmed
   live with its enum value `1` mapped to "Linear" by directly selecting
   that dropdown entry afterward. `FogMinDistance`/`FogMaxDistance`/
   `FogMinAmount`/`FogMaxAmount` share the same confirmed signature shape
   but weren't independently tested.

   **`FogColor` has a real, unresolved gap**: sent successfully both
   before and after enabling Volumetrics, logged cleanly both times, but
   the Fog Color swatch never visibly updated from its default white -
   unlike every other color command tested this item. Shipped anyway
   (accepted without error, ambiguous whether this is a real no-op or
   just a UI redraw lag like `FogType` briefly appeared to have) but
   explicitly flagged as unconfirmed, not proven working.

   Per-light `LightVolumetricSamples`/`LightVolumetricIntensity` (now
   added to `lw_set_light`) and `EnableVolumetricLights` (now
   `lw_toggle_volumetric_lights`) were confirmed live in a follow-up
   sweep: Light Properties showed "Volumetric Samples: 8"/"Volumetric
   Intensity: 50.0%" exactly matching. `EnableVolumetricLights` also
   surfaced a real methodology finding - Cmd History displayed its calls
   as `EnableVolumetricLights 0`/`1` alternating even though no argument
   was ever sent, apparently LightWave's own convention for echoing some
   toggles' resulting state into the log for readability. The reliable
   test remains whether an explicit argument raises a stub arg-count
   error (it does here), not what Cmd History happens to display. See
   `PLAN.md` "Scene environment/atmosphere" for the complete
   investigation.

5. **Per-object render-visibility flags - DONE, plus a real stub bug and
   a genuine surprise finding.** Shipped `lw_toggle_object_visibility(
   item, flag)` (flag is one of `"unseen_by_rays"`, `"unseen_by_camera"`,
   `"unseen_by_radiosity"`, `"unaffected_by_fog"`) and
   `lw_set_alpha_channel_mode(item, mode)`.

   `UnseenByRays`/`UnseenByCamera`/`UnseenByRadiosity`/`UnaffectedByFog`
   confirmed live to be genuine argument-less toggles - Cmd History
   logged each one bare after clicking the real "Object Properties >
   Render" buttons, no stub fix needed. These are genuinely different
   from `ROADMAP2.md` item 1's light/object illumination linking
   (`IncludeObject`/`ExcludeObject`/etc., which control which objects a
   light lights) - this cluster is about whether an object is visible to
   the camera, reflection/refraction rays, radiosity calculations, or
   fog at all, a distinct rendering-control axis.

   `UnseenByAlphaChannel` turned out to be a genuine surprise on two
   counts. First, a real bug: it's wrapped bare in the stub, same shape
   as the other four, but Cmd History showed `UnseenByAlphaChannel 1`
   after a real UI interaction - it actually takes an argument, the same
   missing-`*args` bug class found repeatedly in earlier roadmaps
   (`Ring`/`SetRenderDisplay`/`MotionBlur`), fixed here. Second, and more
   surprising: it isn't a boolean visibility flag at all, despite its
   name and despite matching the exact toggle shape of its four
   siblings - it's the Object Properties "Alpha Channel" dropdown's
   underlying command, an enum. Confirmed live: `0` = "Use Surface
   Settings" (default), `1` = "Constant Value" - the only two options
   this dropdown offered in this install. Shipped as
   `lw_set_alpha_channel_mode` rather than folded into the boolean-toggle
   tool, with the confirmed mapping documented and unconfirmed values
   (other LightWave versions' docs mention more, e.g. Shadow Density)
   explicitly flagged as unverified rather than guessed at.

   A UI freeze occurred partway through live-testing these two tools
   (Cmd History kept logging new commands, but window interaction like
   scrollbars stopped responding) - not clearly attributable to either
   new command, since both had already logged cleanly with no errors
   beforehand, and a full LightWave restart recovered cleanly with no
   corruption. Noted as an operational observation, not a confirmed
   root cause - see `PLAN.md` for the full writeup.

6. **Deeper bone rigging - DONE for the scoped subset.** `ROADMAP2.md`
   item 7 covered chain-level IK flags (`FullTimeIK`/`UnaffectedByIK`)
   and goal/pole assignment, but a real bone itself has a much larger
   property set - 40+ bone-specific commands found in the original
   survey, deliberately scoped down to the highest-value subset rather
   than wrapping all of them. Shipped `lw_set_bone(item, strength=,
   rest_length=, rest_position=, rest_rotation=, weight_map_name=,
   falloff_type=, min_range=, max_range=)` and `lw_toggle_bone_flag(item,
   flag)` (`flag` is `"active"`, `"limited_range"`, `"weight_map_only"`,
   or `"strength_multiply"`).

   Found the real UI location: Modify tab > Properties button (while a
   bone is the current item) opens a "Bones for &lt;object&gt;" panel -
   distinct from both the generic Modify toolbar and the item-level
   Motion Options (which only covers IK goal/pole, already wrapped).
   This panel has object-wide settings (Falloff Type, Limited Bones
   Number) at the top and per-bone settings (Bone Active, Rest Position/
   Length, Weight Map, Strength, Limited Range, the muscle/joint-comp
   family) below, keyed to whichever bone is "Current Bone".

   Confirmed live on `Bone1`: `BoneStrength(0.5)` showed "Strength:
   50.0%"; `BoneRestLength(2)` showed "Rest Length: 2m";
   `BoneFalloffType(2)` (the object-wide dropdown) changed "Falloff
   Type" from "Inverse Distance ^16" to "Inverse Distance ^2";
   `BoneActive`/`BoneLimitedRange` both confirmed genuine argument-less
   toggles (a freshly-created bone defaulted to `BoneActive` unchecked -
   a bone can exist and be parented into a chain while still inactive).
   `BoneWeightMapName` was sent and logged cleanly but couldn't be
   visually confirmed - this test rig's bones live on a plain Null with
   no real mesh/vmap data to match against.

   `BoneRestPosition`/`BoneRestRotation`/`BoneMinRange`/`BoneMaxRange`
   were confirmed live in a follow-up sweep, including a real UI
   discovery: "Rest Position"/"Rest Rotation" look like plain buttons in
   the panel (not value fields), but clicking either opens a "Set Bone
   Rest Position/Rotation" requester pre-populated with the value
   already written - `[1,2,3]`/`[10,20,30]` sent, X:1m/Y:2m/Z:3m and
   Heading:10/Pitch:20/Bank:30 shown, both exact. `BoneMinRange(0.5)`/
   `BoneMaxRange(3)` correctly showed "Min: 500mm"/"Max: 3m" once
   Limited Range was re-enabled.

   `BoneWeightMapOnly`/`BoneStrengthMultiply` also confirmed genuine
   toggles in the same sweep, via a new definitive test worth carrying
   forward: passing an explicit argument to a suspected toggle raises a
   clean Python arg-count error from the stub itself if it's truly
   bare - stronger evidence than any UI observation, since it directly
   probes the wrapped method's real signature. `BoneWeightMapOnly` also
   revealed a real precondition via LightWave's own error dialog: "This
   option only applies when using a weight map." A later full-panel
   screenshot of the Bones panel also resolved an earlier open
   question: `BoneStrengthMultiply` maps to the "Multiply Strength by
   Rest Length" checkbox, confirmed checked after the toggle was
   flipped.

   `SaveEndomorph(name)`/`UseMorphedPositions()` are now also shipped,
   as `lw_save_endomorph(item, name)`/`lw_toggle_use_morphed_positions()`.
   `SaveEndomorph` has a real, confirmed precondition found via
   LightWave's own error dialog: "Null objects are automatically saved
   with the scene" - it refuses Null objects outright, so the actual
   end-to-end bake (a new named Endomorph with correct deformed
   positions) is not independently confirmed against this Null-based
   test rig, only that the command exists and enforces this
   precondition. `UseMorphedPositions` is confirmed a genuine
   argument-less toggle via the definitive arg-count test; its own
   checkbox couldn't be found as a visible UI element anywhere in
   LightWave 2019.1.5 (checked the full Bones panel, Motion Options,
   General Options, and Object Properties), but calling it live DID pop
   a real error dialog: "Use Morphed Positions not supported with the
   current bone mode" - closely matching the 2025 documentation's "not
   supported with Limited Bones" claim, confirming the feature and its
   precondition are both genuinely real in 2019.1.5, just gated behind
   a bone mode this test rig's bones don't have.

   **DONE - the muscle/joint-compensation family** (`BoneJointComp*`/
   `BoneMuscleFlex*`/`BoneTwist*`/`BoneBulge*`) is now also shipped, as
   `lw_toggle_bone_flag`'s seven new flags (`joint_comp`/
   `joint_comp_parent`/`muscle_flex`/`muscle_flex_parent`/`bulge`/
   `bulge_parent`/`twist`) plus `lw_set_bone_deform(item, joint_comp=,
   joint_comp_parent=, muscle_flex=, muscle_flex_parent=, bulge=,
   bulge_parent=, twist=)`. Confirmed live end to end via the Bones
   panel's "Bone Displacement"/"Parent Displacement" section:
   `BoneJointComp()` + `BoneJointCompAmounts(0.3, 0.6)` showed "Joint
   Compensation: 30.0%"/"Joint Comp for Parent: 60.0%" exactly, with
   only the "Joint Compensation" checkbox toggled on - confirming
   `joint_comp`/`joint_comp_parent` are genuinely independent
   checkboxes. Same independence confirmed for `bulge`/`bulge_parent`
   (`BoneBulge()`+`BoneBulgeParent()` both explicitly toggled, both
   showed checked; amounts `0.55`/`0.8` matched exactly). A real
   asymmetry found for `muscle_flex`: toggling only `BoneMuscleFlex()`
   (never calling `BoneMuscleFlexParent()`) checked BOTH "Muscle
   Flexing" AND "Parental Muscle Flexing" simultaneously - confirmed
   via a zoomed screenshot, not just a general read - unlike the
   joint-comp/bulge pairs. `twist` (`BoneTwist()`) has a real
   precondition, confirmed live via LightWave's own error dialog: "This
   option does not apply to the current bone type" - consistent with
   its row appearing grayed out for this test rig's Z-axis bones.
   Bones already had a working numeric-ID resolution path from
   `ROADMAP2.md` item 7 (`_get_bones` reports each bone's own `id`,
   `_resolve_item_id` passes numeric strings straight through) - this
   item builds directly on that groundwork with no new resolution work
   needed. See `PLAN.md` "Deeper bone rigging" and "Follow-up sweep:
   closing the easy/moderate open items" for the full investigation.

7. **Morph/Endomorph control - DONE.** Shipped `lw_set_morph(item,
   target=, amount=)`, wrapping `MorphTarget(itemid)`/`MorphAmount
   (morph)` - the classic object-to-object morph (assigning a whole
   other item's shape as a blend target), distinct from vmap-based
   Endomorphs on a single object.

   Real UI location took some searching - not a Motion Modifier (the
   "Add Modifier" dropdown in Motion Options has no "Morph" entry) and
   not an Object Properties tab (no "Deform" tab exists in this
   install's Primitive/Render/Appearance/Lights/Global/FX/Instancer
   set). Found instead by sending the command directly and reading
   LightWave's own error dialog, the same technique that has already
   worked repeatedly this project: `MorphAmount` alone popped "This
   option only applies when the current object has a morph target" -
   confirming both that the command is real and exactly what
   precondition gates it, without ever finding a dedicated panel for it.

   `target` resolved to a numeric ID like `lw_set_goal`/`lw_set_parent`
   (same "wants a numeric ID, not a name" quirk as that whole command
   family). Confirmed live end to end: sending `MorphTarget` then
   `MorphAmount(0.7)` no longer raised the error, both logged cleanly.
   No visible geometry change was possible to confirm further given the
   test scene's morph target (`BoneTestObject`, a Null) has no real mesh
   to blend toward - a limitation of the test rig, not the command.
   `SaveEndomorph`/`UseMorphedPositions` were surveyed but not tested or
   wrapped this pass - a real vmap-based Endomorph workflow needs actual
   mesh geometry to meaningfully test, better suited to a future session
   with a richer test object. See `PLAN.md` "Morph/Endomorph control"
   for the full investigation.

## Status: all 7 items done

Item 2 (Node graphs) was the deepest investigation on this roadmap -
nine explicitly-approved staged steps, one genuine dead end spotted from
method names alone (`LWBSDFFuncs`) before wasting live-call budget on
it, and a final answer that mirrored `ROADMAP2.md` item 9's keyframe
discovery almost exactly. Item 3 (render globals) surfaced a new,
concrete example of this project's "one-way, no delivery guarantee"
Command Port caveat actually manifesting as a wrong logged value, not
just a theoretical risk. Item 4 (scene environment) found a real,
still-unresolved `FogColor` write gap, documented honestly rather than
hidden. Item 5 (visibility flags) found both a genuine stub bug
(`UnseenByAlphaChannel`) and that it wasn't even the boolean its name
suggested. Item 6 (bone rigging) found the genuinely separate "Bones
for &lt;object&gt;" panel, distinct from both Motion Options and Item
Properties. Item 7 (morph) found its real precondition purely through
LightWave's own error dialog, without ever locating a dedicated UI
panel for it at all - proof that this project's "when in doubt, send it
and read the error" methodology still works even when the UI hunt comes
up empty. Combined with `ROADMAP.md` and `ROADMAP2.md`, this connector
now covers scene management, item creation/loading, hierarchy/IK/bone
rigging, cameras, lights, surfaces (flat and node-based), selection,
animation/keyframes, render quality/GI, scene environment/atmosphere,
per-object visibility, and object-to-object morphing.

## Not investigated this pass

`Wind`/`Dynamics`-style keyword searches turned up only Layout/Scene/
Item *window management* commands (`Layout_SetWindowPos`,
`DynamicUpdate`, etc.) - no real particle/cloth/hard-body dynamics
command cluster was found in this survey. If LightWave 2019.1.5's
particle/dynamics systems (HardFX, SoftFX, ParticleFX) are controllable
at all via the Command Port, their command names weren't found under
the keywords searched this pass - would need its own, differently-
keyworded survey before concluding they're out of reach the way Modeler
writes are, rather than just not yet found.
