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
   nodes.** Prioritized explicitly, given real interest in driving
   PBR-style shading, despite this area's real structural complexity
   (discussed below) making "deliberately last" the initial instinct -
   LightWave 2019's Surface Editor node graph includes a "Principled BSDF" node
   (base color, roughness, metallic, specular, etc. - the same
   physically-based shading model most modern renderers converged on),
   reachable today only by hand via the Surface Editor's "Edit Node
   Graph" button (already seen in this project's `ROADMAP2.md` item 8
   screenshots).

   Confirmed via this roadmap's own command-list survey: there is NO
   native Command Port command for node graph editing at all (only
   `NodeDisplacement`/`NodeDisplacementOrder`/`NodeEdges` exist, none of
   which touch the graph itself) - this will need the SDK's node
   API directly, the same architectural shift `ROADMAP2.md` item 8
   required for flat surface properties (`LWSurfaceFuncs` instead of a
   Command Port command), likely one level deeper still: LightWave's C
   SDK exposes node graph construction through classes conventionally
   named around `LWNodeFuncs`/`LWNodeInputFuncs`/`LWNodeOutputFuncs` (or
   whatever this specific SWIG build actually calls them - **do not
   trust that name, or any other generic LWSDK recollection, without
   live confirmation**, since this project has already found this
   build's Python bindings diverge from generic docs multiple times).
   `LWSurfaceFuncs` itself has `getNodeEditor()` (already seen in an
   earlier introspection dump, never called) as a likely entry point
   into whatever this build's real node object model is.

   **Start exactly the way item 8 started**: a live, read-only
   `dir(lwsdk)` scan filtered for "Node"/"Shader"/"BSDF"/"Principled",
   plus `dir()` on whatever `getNodeEditor()` returns, before writing
   any real code - this is genuinely new, unmapped territory for this
   connector, one level more structurally complex than item 8's flat
   `setFlt()` calls (a node graph has nodes, sockets, and connections
   between them, not just scalar properties), so treat it with at least
   the same staged, explicitly-approved caution item 8 and item 9 both
   required, probably more given the added structural complexity. A
   good first concrete goal once the real API is mapped: read
   (`lw_get_surface_info`-style) an existing PrincipledBSDF node's
   parameters on a real surface, before attempting to write/create one.

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

5. **Per-object render-visibility flags.** `UnseenByCamera`,
   `UnseenByRays`, `UnseenByAlphaChannel`, `UnseenByRadiosity`,
   `UnaffectedByFog` - all argument-less, same shape as the confirmed
   real toggles `UnaffectedByIK`/`FullTimeIK` from `ROADMAP2.md` item 7
   (and worth checking against the same shape that turned out to be
   real *bugs* for `Ring`/`SetRenderDisplay`/`MotionBlur` - don't assume
   either way). These are genuinely different from `ROADMAP2.md` item
   1's light/object illumination linking (`IncludeObject`/
   `ExcludeObject`/etc., which control which objects a light lights) -
   this cluster is about whether an object is visible to the *camera*,
   *reflections/refractions*, *alpha channel*, or *radiosity*
   calculations at all, a real and distinct rendering-control axis.
   Object Properties' render-visibility checkboxes were seen in earlier
   screenshots this project has taken but never wrapped.

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
