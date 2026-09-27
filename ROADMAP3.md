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
   and `CreateContentPath`/`RecentContentDirs` were surveyed but not
   wrapped - the first needs a `type` argument whose real values were
   never confirmed live, and the other two look like one-shot UI actions
   (opening a dialog/menu) rather than pure setters worth automating.
   See `PLAN.md` "Content Directory management" for the full
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

3. **Render Globals / GI / quality settings.** Right now this connector
   can trigger a render (`lw_render_frame`/`lw_render_scene`) and read
   completion state (`lw_get_render_status`), but has zero control over
   render *quality* - every render runs at whatever settings a human
   last configured in the UI. Real, confirmed-`*args` commands found
   for: `RenderThreads(threads)`, `RenderTileSize`, `RenderAlgorithm`,
   `RenderMode`, `Antialiasing(level)`/`MinAntialiasing`/
   `MaxAntialiasing`, `RadiosityInterpolation(enabled)`,
   `ObjGIRadiosityTolerance`, `ColorSpaceOutput`/`ColorSpaceOutputAlpha`/
   `ColorSpaceOutputVPR`. Also found argument-less toggle candidates
   needing live verification before use: `EnableRadiosity0`,
   `EnableRadiosity1` (possibly two different radiosity passes/methods -
   LightWave 2019's Global Illumination panel has multiple radiosity
   algorithm options, worth checking Cmd History against the real UI
   dropdown before assuming these are simple on/off toggles rather than
   a `LightFalloffType`-style enum command with a wrong-looking
   zero-arg wrapper), and `BakeRadiosityScene`. High value: this is the
   biggest remaining "can run renders but can't configure them" gap.

4. **Scene environment/atmosphere.** A coherent, entirely untouched
   category: `Backdrop`, `BackdropColor(r, g, b)`, `GradientBackdrop`,
   `SkyColor(r, g, b)`, `SkySqueezeColor`, and a full `Fog` family -
   `FogType(type)`, `FogMinDistance`/`FogMaxDistance`/`FogMinAmount`/
   `FogMaxAmount`(all confirmed `*args`-taking), `FogColor(r, g, b)`,
   plus `FogLevel` (not yet checked for argument shape). Also
   `EnableVolumetricLights`/`EnableVolumetrics` (argument-less,
   unverified) and per-light `LightVolumetricSamples`/
   `LightVolumetricIntensity` (real `*args` commands, natural
   extensions to `lw_set_light` alongside `LightConeAngle` etc. - Light
   Properties already showed "Volumetric Samples"/"Volumetric
   Intensity" fields in earlier screenshots from this project's light
   work, never wired up). Real value for anyone using this connector to
   set up a scene's look, not just its geometry/animation.

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

6. **Deeper bone rigging.** `ROADMAP2.md` item 7 covered chain-level IK
   flags (`FullTimeIK`/`UnaffectedByIK`) and goal/pole assignment
   (`lw_set_goal`/`lw_set_pole`, from `ROADMAP.md`), but a real bone
   itself has a much larger property set never touched:
   `BoneActive` (argument-less, unverified - enable/disable a bone),
   `BoneStrength`/`BoneStrengthMultiply`, `BoneWeightMapName`/
   `BoneWeightMapOnly` (bind a bone to a named weight map - real value
   for anyone driving a rigged character), `BoneRestPosition`/
   `BoneRestRotation`/`BoneRestLength`, `BoneFalloffType`,
   `BoneLimitedRange`/`BoneMinRange`/`BoneMaxRange`, and a "muscle"
   family for organic deformation - `BoneJointComp`/`BoneJointCompParent`/
   `BoneJointCompAmounts`, `BoneMuscleFlex`/`BoneMuscleFlexParent`/
   `BoneMuscleFlexAmounts`, `BoneTwist`/`BoneTwistAmount`,
   `BoneBulge`/`BoneBulgeAmount`/`BoneBulgeParent`/
   `BoneBulgeParentAmount`. This is a genuinely large surface (40+
   bone-specific commands found) - real, but needs scoping down to the
   most valuable subset (`BoneWeightMapName`/`BoneStrength`/
   `BoneActive`/`BoneFalloffType` look like the highest-value, most
   commonly-needed subset for basic rigging control) rather than
   wrapping all 40+ in one pass. Bones already have a working numeric-ID
   resolution path from `ROADMAP2.md` item 7 (`_get_bones` reports each
   bone's own `id`, `_resolve_item_id` passes numeric strings straight
   through) - this item builds directly on that groundwork.

7. **Morph/Endomorph control.** Small but genuinely new: `MorphAmount(morph)`
   and `MorphTarget(itemid)` (both confirmed `*args`-taking), plus
   `SaveEndomorph`/`UseMorphedPositions`. Lets automation drive morph
   target blending on an object - a distinct capability from anything
   shipped in either prior roadmap. Lower priority than the items above
   since it's a narrower, single-purpose feature rather than a whole
   category, but cheap to add once picked up.

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
