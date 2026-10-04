# Using the connector

Every tool the connector offers, an example workflow, how it talks to
LightWave, and detailed notes on each tool's behaviour and caveats. For
installation and setup, see [GETTING_STARTED.md](GETTING_STARTED.md).

## Available Tools

**Connection & diagnostics**

| Tool | Description |
| --- | --- |
| `lw_ping()` | Round-trip check that the read path (`LWComRing`) is alive. |
| `lw_run_command(command, args=)` | Send any of the ~800 native Layout commands directly - generic passthrough. |
| `modeler_run_command(command, args=)` | Send any native Modeler command directly, over Modeler's own Command Port. |
| `modeler_ping()` | Always times out - Modeler has no working read path (confirmed dead end). |
| `modeler_get_object_info()` | Always times out - same Modeler read-path limitation. |

**Scene management**

| Tool | Description |
| --- | --- |
| `lw_get_scene_info()` | Get the current scene's name, filename, and full item list. |
| `lw_create_null(name=)` | Create a Null item in the current scene. |
| `lw_load_object(filename)` | Load a real mesh object (`.lwo`) into the scene. |
| `lw_save_object(name, filename)` | Save one object to its own file. |
| `lw_save_scene_as(filename)` | Save the current scene to a file. |
| `lw_load_scene(filename)` | Load a scene file, replacing the current scene. |
| `lw_clear_scene()` | Clear the scene back to its default empty state. |
| `lw_set_content_directory(path)` | Set LightWave's base Content Directory. |
| `lw_set_content_type_directory(content_type, dirname)` | Set a per-content-type sub-path ("Objects", "Scenes", "Images", etc.). |

**Item queries & hierarchy**

| Tool | Description |
| --- | --- |
| `lw_get_item_id(name)` | Resolve an item's name to its plain numeric ID. |
| `lw_get_transform(name)` | Get an item's position/rotation/scale at the live playhead. |
| `lw_get_hierarchy()` | Get every item's parent, IK target/goal/pole, and bone chains. |
| `lw_get_channels(name)` | Get an item's full keyframe/envelope structure. |
| `lw_get_current_time()` | Get the live playhead's frame and time (seconds). |
| `lw_probe_channels(name)` | Diagnostic: raw channel-group introspection. |

**Selection**

| Tool | Description |
| --- | --- |
| `lw_get_selection()` | Get every item's name/type and current selected state. |
| `lw_add_to_selection(item)` | Add an item to the current multi-selection. |
| `lw_remove_from_selection(item)` | Remove an item from the current multi-selection. |

**Hierarchy & IK**

| Tool | Description |
| --- | --- |
| `lw_set_parent(child, parent)` | Reparent one item to another. |
| `lw_set_target(item, target)` | Set an item's IK/camera/light target. |
| `lw_set_goal(item, goal)` | Set an item's IK goal. |
| `lw_set_pole(item, pole)` | Set an item's IK pole. |
| `lw_set_ik_options(item, goal_strength=, ik_fk_blending=)` | Set chain-level IK numeric properties. |
| `lw_toggle_ik_flag(item, flag)` | Flip "Full-time IK" or "Unaffected by IK". |

**Cameras**

| Tool | Description |
| --- | --- |
| `lw_get_camera_info(name=)` | Get resolution, focal length, f-stop, FOV, and shutter properties. |
| `lw_set_camera(camera, zoom_factor=, f_stop=, aperture_height=, shutter_open=, shutter_efficiency=, rolling_shutter=)` | Set a camera's zoom, DOF, and motion-blur shutter properties. |
| `lw_set_camera_resolution(width, height)` | Set the scene's render resolution. |

**Lights**

| Tool | Description |
| --- | --- |
| `lw_get_light_info(name=)` | Get a light's type, falloff, color, intensity, and range. |
| `lw_set_light(light, intensity=, color=, falloff_type=, cone_angle=, volumetric_samples=, volumetric_intensity=)` | Set a light's intensity, color, falloff, cone angle, and volumetrics. |
| `lw_include_light(light, obj)` / `lw_exclude_light(light, obj)` | Manage a light's object inclusion/exclusion list. |
| `lw_include_object_light(obj, light)` / `lw_exclude_object_light(obj, light)` | Same relationship, set from the object's own side. |

**Surfaces & node graphs**

| Tool | Description |
| --- | --- |
| `lw_get_surface_info(name)` | Get a surface's color/diffuse/luminosity/specularity/glossiness/etc. |
| `lw_set_surface(surface, color=, diffuse=, luminosity=, specularity=, glossiness=, reflection=, transparency=, smoothing=)` | Write a surface's flat properties. |
| `lw_get_surface_nodes(surface=)` | List every node in a surface's node graph. |
| `lw_get_node_inputs(surface=, node=)` | List a specific node's real parameter names. |
| `lw_get_node_channel(surface=, node=, channel=)` | Read a node parameter's actual keyframe data. |
| `lw_set_node_key(node, channel, frame, value, surface=)` | On an animated node input, change the key at `frame` or add one there (value in the same units as `lw_get_node_values`). |
| `lw_delete_node_key(node, channel, frame, surface=)` | Delete the key at `frame` on an animated node input (won't delete the last key). |
| `lw_get_node_values(node, surface=)` | Read every stored input value of a node (e.g. Principled's Color, Roughness), with its units; animated inputs are marked `enveloped` and include their keys. |
| `lw_set_node_input(node, input_name, value, surface=)` | Set one input value - one number, or three 0-1 numbers for a color. Percent is a fraction (35% = `0.35`). Refuses animated (enveloped) inputs. |
| `lw_add_node(surface=, node_type=, x=, y=)` | Create a new node (added disconnected; at the graph's origin unless `x`/`y` are given). **`node_type` must be a confirmed-real `server_user_name`, never a guess - an invalid one freezes Layout with a blocking dialog.** |
| `lw_connect_nodes(surface=, from_node=, to_node=, input_name=, output_name=)` | Wire one node's output into another's input, replacing what fed it (`to_node="Surface"` is the root, e.g. its `Material` input). Reports the connections LightWave actually has afterwards. |
| `lw_disconnect_nodes(surface=, to_node=, input_name=)` | Remove the wire feeding one input. |
| `lw_remove_node(node, surface=)` | Delete a node and every wire to or from it ("Surface" and "Input" are refused). |
| `lw_move_node(node, x, y, surface=)` | Reposition a node in the Node Editor (cosmetic). Axes run backwards - larger x goes left, larger y goes up - at roughly a pixel per unit; for spacing nodes apart, not exact placement. |
| `lw_probe_surf()` | Diagnostic: list `SURF_*` constants from the SDK. |

**Bones & rigging**

| Tool | Description |
| --- | --- |
| `lw_set_bone(item, strength=, rest_length=, rest_position=, rest_rotation=, weight_map_name=, falloff_type=, min_range=, max_range=, bone_type=)` | Set a bone's rigging properties; `bone_type` is "z_axis" or "joint". |
| `lw_toggle_bone_flag(item, flag)` | Flip a bone's toggle flag (`active`, `limited_range`, `weight_map_only`, `strength_multiply`, `joint_comp`, `joint_comp_parent`, `muscle_flex`, `muscle_flex_parent`, `bulge`, `bulge_parent`, `twist`). |
| `lw_set_bone_deform(item, joint_comp=, joint_comp_parent=, muscle_flex=, muscle_flex_parent=, bulge=, bulge_parent=, twist=)` | Set the muscle/joint-compensation family's amount fields. |
| `lw_set_morph(item, target=, amount=)` | Set an object-to-object Morph target/amount. |
| `lw_save_endomorph(item, name)` | Bake an object's current deformed positions into a new Endomorph vmap. |
| `lw_toggle_use_morphed_positions()` | Flip "Use Morphed Positions". |

**Object visibility**

| Tool | Description |
| --- | --- |
| `lw_toggle_object_visibility(item, flag)` | Flip a render-visibility flag (`unseen_by_rays`, `unseen_by_camera`, `unseen_by_radiosity`, `unaffected_by_fog`). |
| `lw_set_alpha_channel_mode(item, mode)` | Set an object's Alpha Channel dropdown mode. |

**Render & render globals**

| Tool | Description |
| --- | --- |
| `lw_render_frame(frame=)` | Render a single frame. |
| `lw_render_scene()` | Render the full configured frame range. |
| `lw_abort_render()` | Abort an in-progress render. |
| `lw_get_render_status()` | Get real render completion state and progress, not a time-based guess. |
| `lw_set_render_globals(threads=, tile_size=)` | Set render thread count / tile size. |
| `lw_get_color_space()` | Read every colour space setting (display, final render, file types, alpha, ...), the four CS checkboxes, and the colour spaces available. |
| `lw_set_color_space(display=, final_render=, buffer=, embedded_alpha=, picked_colors=, light_color=, palette_files=, eight_bit_files=, float_files=, alpha=, auto_sense=, correct_opengl=, affect_picker=, convert_8bit_to_float=)` | Set colour spaces by name (e.g. `final_render="sRGB"`); unknown names are refused before anything is sent. |
| `lw_get_render_options()` | Read the Render tab: raytrace shadows/reflection/refraction, recursion limits, diffuse bounces, reflection/refraction/SSS samples. |
| `lw_set_render_options(raytrace_shadows=, raytrace_reflection=, raytrace_refraction=, ray_recursion_limit=, ..._recursion_limit=, diffuse_bounces=, ..._samples=, ray_precision=, polygon_intersection=, noise_filter=, despike=, despike_tolerance=)` | Set the Render tab's quality settings; reads back what LightWave exposes. |
| `lw_get_antialiasing(camera=)` | Read a camera's antialiasing: min/max samples, adaptive sampling and threshold, filter radius, and the reconstruction filter. |
| `lw_set_antialiasing(camera=, min_samples=, max_samples=, adaptive_sampling=, adaptive_threshold=, filter_radius=)` | Set a camera's antialiasing (draft vs. final quality); reads every value back to confirm. |
| `lw_toggle_global_illumination()` | Flip "Enable GI". |
| `lw_set_gi_interpolated(enabled)` | Set GI's "Interpolated" mode. |
| `lw_get_object_gi(item)` | Read an object's own GI settings (mode, rays, pixel spacing, angular tolerance) and whether Enable GI is on. |
| `lw_set_object_gi(item, mode=, angular_tolerance=, brute_force_rays=, primary_rays=, secondary_rays=, min_pixel_spacing=, max_pixel_spacing=)` | Set an object's own GI settings (Object Properties > Global Illum); checks the preconditions first. |

**Scene environment**

| Tool | Description |
| --- | --- |
| `lw_set_backdrop(color=, zenith_color=, sky_color=, ground_color=, nadir_color=)` | Set the flat backdrop color and the four gradient-backdrop stops. |
| `lw_toggle_gradient_backdrop()` | Flip "Gradient Backdrop". |
| `lw_toggle_volumetrics()` | Flip the scene's "Enable Volumetrics" (Fog panel gate). |
| `lw_toggle_volumetric_lights()` | Flip the scene-wide "Enable Volumetric Lights". |
| `lw_get_fog()` | Read the scene fog: type, distance range, amount range, and color. (Fog can't be *set* from here - see below.) |

**Animation**

| Tool | Description |
| --- | --- |
| `lw_set_keyframe(name, frame, position=, rotation=, scale=)` | Create a keyframe for an item at a given frame. |

See "Detailed Tool Notes" below for what each tool's confirmed-live
behavior, real preconditions, and open caveats actually are - the
table above is a quick reference, not the full story.

## Example Workflow

A typical Claude conversation might do this, one tool call per step:

```
lw_create_null(name="Anchor")
lw_set_keyframe(name="Anchor", frame=0, position=[0, 0, 0])
lw_set_keyframe(name="Anchor", frame=30, position=[0, 5, 0])

lw_load_object(filename="C:/scenes/props/crate.lwo")
lw_set_surface(surface="Crate", color=[0.6, 0.4, 0.2], diffuse=0.8)

lw_set_camera_resolution(width=1920, height=1080)
lw_render_frame(frame=15)
lw_get_render_status()
```

You don't write this yourself - you'd just ask Claude in plain English
("create a Null that moves up over a second, load this crate object, give
it a brown surface, and render frame 15"), and Claude calls the underlying
tools shown above.

## Protocol Details

- **Claude ↔ MCP server**: stdio (standard input/output), the standard
  local MCP transport - Claude Desktop launches `server.py` as a
  subprocess.
- **MCP server ↔ LightWave (writes)**: LightWave's official Command Port
  (`lwsdk.LWCommandPort`), a plain UDP, one-way, fire-and-forget channel -
  there is no delivery or ordering guarantee, and no confirmation
  LightWave actually accepted a given command, only that it was sent.
  Layout listens on `9735`, Modeler on `9736` by default.
- **MCP server ↔ LightWave (reads)**: the native Command Port is
  write-only, so reads go through a custom Master plug-in
  (`lw_mcp_ring.py`, class `LWComRing`) that this repo installs into
  Layout - see step 2 of [GETTING_STARTED.md](GETTING_STARTED.md#quick-start).

## LightWave Command Port

| Component | Purpose |
| --- | --- |
| Layout | Scene orchestration, hierarchy/IK/bone rigging, cameras, lights, surfaces, animation, rendering. |
| Modeler | Mesh editing - writes only; reads are a confirmed dead end (see the Modeler notes above). |

## Detailed Tool Notes (confirmed-live findings & caveats)

Everything below is the full write-up behind the tool table above -
what was actually confirmed live against a running LightWave 2019.1.5
session (screenshots, Cmd History, and LightWave's own error dialogs as
ground truth), every real precondition found, and every gap that's still
open. See `PLAN.md` for the complete build log
this is distilled from.

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
  the *first* time this session - a real manual click was needed
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
- `lw_set_content_type_directory(content_type, dirname)` (ROADMAP3.md
  item 1 follow-up) - wraps `ContentTypeDirectory(type, dirname)`, the
  per-content-type sub-path buttons in Preferences > Paths ("Scenes",
  "Objects", "Images", etc.). Confirmed live for `"Objects"`:
  `content_type` is the literal panel label string, and sending a new
  `dirname` visibly changes that button's own label to the new
  sub-path - a live state readout, not a fixed caption, the same
  pattern found for bone Rest Position/Rotation. The other twenty-one
  type strings are inferred from the panel's visible labels, not
  independently tested. See `PLAN.md` "Follow-up sweep: closing the
  easy/moderate open items" for the full investigation.
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
  Editor screenshot with both rows highlighted. The earlier
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

**Layout reads** (all via `LWComRing`, see step 2 of [GETTING_STARTED.md](GETTING_STARTED.md#quick-start))
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
  `lw_get_node_values(node)` reads them instead from the saved graph
  (see "Node Editor writing" below). `lw_get_node_channel(surface,
  node, channel)` reads an enveloped parameter's keyframe data -
  confirmed live end to end (Roughness read back as `0.1`, matching the
  UI's "10.0%").
  See `PLAN.md` "Node Editor / PrincipledBSDF nodes" for the full
  nine-step staged investigation, including a real dead end
  (`LWBSDFFuncs` turned out to be a shader-plugin-authoring API, not a
  way to read an existing node's parameters).

  **Node Editor writing - nodes can be added, removed, moved, wired and
  given input values.** `lw_add_node`, `lw_remove_node`,
  `lw_move_node`, `lw_connect_nodes`, `lw_disconnect_nodes`,
  `lw_get_node_values` and `lw_set_node_input` all work
  by saving the surface's whole node graph as ASCII
  (`LWFileIOFuncs.openSave` + `LWNodeEditorFuncs.save`), editing the
  text - its `{ Connections }` block names every wire by node and socket
  name, and a new node is a short block with empty data that picks up
  the node type's own defaults - and loading it back (`openLoad` +
  `load`), then saving once more to report what LightWave actually has.
  Input values are plain text in each node's block too, in LightWave's
  internal units (Percent as a fraction, Color as 0-1 per channel,
  Distance in metres). Confirmed live end to end: added a Principled
  BSDF, wired it into Surface > Material, set its Color to red and
  Roughness to 35%, and the Surface Editor showed exactly that.

  The obvious SDK calls (`addNode`, `connect`, `destroyNode`, `setXY`) are
  deliberately NOT used. `addNode` creates a
  node that looks normal but poisons the graph: a later `load` of it
  never returns, wedging the connector until Layout restarts.
  `connect` made the connection but froze Layout's UI all three times
  it was tried - plausibly the same `addNode` nodes' fault. Known
  limitations: an open Surface Editor only shows changes after being
  closed and reopened, and node coordinates are only approximate (see
  `lw_move_node`).

  **CRITICAL, confirmed live: an invalid `node_type` freezes Layout.**
  `lw_add_node("CONNECTOR", "Constant")` - a category heading in the
  Node Editor's "Add Node" browser, not a node type - popped a real,
  modal "Plug-in Missing: No plug-in of type NodeHandler found with
  name Constant" dialog that froze Layout until a human clicked "No"
  (recovered cleanly, no corruption). `node_type` must only ever be an
  exact `server_user_name` already confirmed via `lw_get_surface_nodes`
  on a real existing node - never a category name, never a guess. See
  `PLAN.md` "Node Editor writing" for the full investigation.
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
  showed the real multi-key data, and surfaced a new,
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
- `lw_set_light(light, intensity=, color=, falloff_type=, cone_angle=,
  volumetric_samples=, volumetric_intensity=)`
  (ROADMAP2.md item 5) - the write-side counterpart to
  `lw_get_light_info`. Same shape and numeric-ID `SelectItem` pattern as
  `lw_set_camera`. Confirmed live: `intensity`/`color` take effect
  immediately. `falloff_type` is 0 (Off) or 1 (Inv Distance^2) - the
  only two options in LightWave 2019 - and only applies to Point/Spot
  lights (LightWave pops "This option does not apply to the current
  light type" for Distant). `lw_get_light_info` reads it back
  correctly, **as long as Light Properties is closed when you change
  it**: with the panel open, the light changes but the panel gets out of
  step (stops responding) and the reading stays stale. Fixed a real duplicate-definition bug found
  in the stub: `LightFalloffType` was defined twice, and Python silently
  kept only the argument-less second copy, making the real one
  unreachable. Deliberately does **not** wrap `LightVisibleToCamera`/
  `LightCastsShadows` - both were suspected of having the same
  missing-argument bug as `MotionBlur`, but live verification (clicking
  their real checkboxes and checking Cmd History) proved they're real
  argument-less toggles with no way to set or read a known state; use
  `lw_run_command` directly for those two. Also confirmed live:
  "Visible to Camera" is disabled in the UI for Point lights, only
  usable on Spot/Distant. See `PLAN.md` "Light property writes" for the
  full investigation. `volumetric_samples`/`volumetric_intensity`
  (ROADMAP3.md item 4, gated by "Affect Volumetrics") confirmed live
  with zero precondition beyond that checkbox already being on. See
  also `lw_toggle_volumetric_lights()`, the scene-wide "Enable
  Volumetric Lights" toggle - distinct from these per-light values and
  from `lw_toggle_volumetrics`' scene Volumetrics/Fog panel.
- `lw_render_frame(frame=None)`, `lw_render_scene()`, `lw_abort_render()`
  - one-way, fire-and-forget like every command here.
- `lw_get_render_status()` - the actual point of this group: real
  completion state (`rendering: true/false`, resolution, `frame_count`)
  read from `lwsdk.IFrameBuffer` callbacks (see step 3 of [GETTING_STARTED.md](GETTING_STARTED.md#quick-start)),
  not a guess based on elapsed time. Confirmed live: resolution set,
  render triggered, status correctly went `true` -> `false` with
  matching numbers. **Multi-frame `RenderScene` progress tracking is now
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
- **Colour space** - `lw_get_color_space()` /
  `lw_set_color_space(...)`, the Edit > General Options > CS tab.
  Commands from Cmd History; several don't match their labels (Picked
  Colors is `ColorSpaceSurfaceColor`, Display is `ColorSpaceViewer`,
  Default Final Render is `ColorSpaceOutput`), and every one takes its
  value although the stubs declare none, so they're sent raw. Names are
  checked case-insensitively against LightWave's live list (Linear,
  sRGB, rec709, Cineon, ciexyz; alpha slots only the first three)
  before sending, and everything is read back via LWColorSpaceFuncs -
  except Default Buffer, whose reader returns nothing. These are
  preferences and didn't survive a Layout restart in testing.
- **Render tab quality settings** - `lw_get_render_options()` /
  `lw_set_render_options(...)`: raytraced shadows/reflection/refraction,
  ray/transparency/reflection/refraction recursion limits, diffuse
  bounces, reflection/refraction/SSS samples, ray precision, polygon
  intersection mode, noise filter and despike. This install's renderer
  dropdown only offers VPR, so there's no engine to switch; these are
  the speed-vs-quality controls instead. Every command was found and
  confirmed via Cmd History, and every readable value is read back.
  Two surprises: `RenderAlgorithm` is the Polygon Intersection Mode
  (Fastest/Watertight/Double Precision), not a render engine; and the
  GPU noise filter pops a modal "A supported GPU is not available"
  error on this machine, so the tool only offers Off and CPU. Ray
  precision, polygon intersection, noise filter and despike can't be
  read back.
- **Antialiasing** - `lw_get_antialiasing(camera)` /
  `lw_set_antialiasing(camera, min_samples=, max_samples=,
  adaptive_sampling=, adaptive_threshold=, filter_radius=)`, the
  sampling block of Camera Properties. Confirmed live end to end,
  checked against both the UI and Cmd History. The real command names
  came from Cmd History, not the obvious stubs: Minimum/Maximum Samples
  are `MinAntialiasing`/`MaxAntialiasing`, Filter Radius is
  `Oversampling`, and Adaptive Sampling is a bare `AdaptiveSampling`
  toggle - so the tool reads the current state and only toggles when it
  differs. Every call reads all values back (LWCameraInfo per camera,
  LWSceneInfo for adaptive sampling/threshold/filter) and returns them.
  With adaptive sampling off, LightWave renders at the minimum sample
  count. The reconstruction filter (Render Properties > Buffers) is
  read-only: changing it by hand logs no command.
- **Render Globals / GI quality settings** (ROADMAP3.md item 3) -
  `lw_set_render_globals(threads=, tile_size=)`, `lw_toggle_global_
  illumination()`, `lw_set_gi_interpolated(enabled)`,
  `lw_get_object_gi(item)`, `lw_set_object_gi(item, ...)`. Closes the biggest remaining
  "can trigger renders but can't configure them" gap. `threads`/
  `tile_size` confirmed live with zero preconditions - `threads` even
  auto-unchecked "Automatic Multithreading" as a side effect.
  `lw_toggle_global_illumination` confirmed live as a real
  argument-less toggle for "Enable GI". `lw_set_gi_interpolated(1)`
  confirmed live to check the "Interpolated" checkbox. Angular
  tolerance, which the old `lw_set_gi_radiosity_tolerance` could never
  set, turned out to be a **per-object** setting: Object Properties >
  Global Illum has its own "Global Illumination Mode" (Use Global /
  Monte Carlo Brute Force / Monte Carlo Interpolated - the "Monte Carlo
  Interpolated" that LightWave's error message names), and the whole
  `ObjGI*` command family acts on the selected object.
  `lw_set_object_gi(item, mode=, angular_tolerance=, brute_force_rays=,
  primary_rays=, secondary_rays=, min_pixel_spacing=,
  max_pixel_spacing=)` replaces it: it selects the object by ID,
  checks the two preconditions LightWave enforces with modal error
  dialogs (Enable GI on; the interpolated settings need mode
  "interpolated", `brute_force_rays` needs "brute_force") and refuses
  instead of sending, then reads everything back via
  `lw_get_object_gi`. Tolerance is in plain degrees - Cmd History shows
  it as 1 - cos(angle), but that's only how it's logged. All values
  confirmed live against the read-back and the Object Properties panel.
  `ObjGIMissingSampleRays` isn't offered: LightWave drops it without
  logging it, and it isn't on the tab. `EnableRadiosity1` (a sibling
  of the wrapped `EnableRadiosity0`) is definitively resolved as
  non-existent: calling it live popped LightWave's own error dialog,
  "Unknown command: 'EnableRadiosity1'" - proof, not a guess, that
  2019.1.5's command parser doesn't recognize it at all despite the
  bundled stub defining it (likely generated against a different
  LightWave version). Left permanently unwrapped.

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
  `lw_toggle_volumetrics()`, `lw_toggle_volumetric_lights()`,
  `lw_get_fog()`. `Backdrop()`
  (despite the central-looking name) turned out to just be a panel-opener
  like `SurfaceEditor` - opening Effects > Backdrop logged it bare, not a
  setting. `GradientBackdrop` confirmed a real toggle; all five
  backdrop colors confirmed live with real color swatches -
  `BackdropColor`/`SkyColor` (red, then green), and with Gradient
  Backdrop on, `zenith_color`/`ground_color`/`nadir_color` sent together
  correctly showed yellow/magenta/cyan. Fog lives under Render
  Properties > Volumetrics
  (not the "Legacy Volumetrics" Effects tab, which turned out to be an
  unrelated plugin-based system - Ground Fog/HyperVoxels/PixieDust) -
  `EnableVolumetrics` confirmed a real toggle that gates the *entire*
  Fog panel as a precondition, same shape as DOF/Motion Blur.
  `lw_toggle_volumetric_lights()`
  wraps the scene-wide `EnableVolumetricLights` toggle, confirmed real
  via a new definitive test (see "Methodology" note below), distinct
  from per-light `volumetric_samples`/`volumetric_intensity` on
  `lw_set_light` and from this section's scene Volumetrics/Fog panel.

  **Methodology finding**: `EnableVolumetricLights` initially looked
  suspicious because Cmd History logged it as `EnableVolumetricLights
  0`/`1` alternating with each bare call, resembling the
  `UnseenByAlphaChannel` missing-argument bug from item 5. A more
  definitive test resolved it: passing an explicit argument to the
  wrapped stub raised a Python arg-count `TypeError`
  ("takes 1 positional argument but 2 were given"), proving the stub -
  and by inference the real command - takes none. The Cmd
  History suffix turned out to be LightWave's own display convention
  for echoing a toggle's resulting boolean state, not evidence of a
  real argument on the wire. A numeric suffix in Cmd History alone is
  **not** reliable proof a command takes an argument; the arg-count
  test is.

  **Fog is read-only.** The `Fog*` commands (`FogType`,
  `FogMinDistance`, `FogMaxDistance`, `FogMinAmount`, `FogMaxAmount`,
  `FogColor`) are accepted and logged in Cmd History but change
  nothing in LightWave 2019 - confirmed live with Volumetrics enabled,
  both with and without "Use Legacy Volumetrics". The panel's fog
  belongs to the Volume Integrator plug-in, and changing it by hand
  logs no command at all. `lw_get_fog()` reads it correctly (it
  followed a hand change to Linear), so the former `lw_set_fog` was
  withdrawn rather than left reporting "sent" for changes that never
  happen. See `PLAN.md` "Fog commands have no effect".
- **Deeper bone rigging** (ROADMAP3.md item 6) - `lw_set_bone(item,
  strength=, rest_length=, rest_position=, rest_rotation=,
  weight_map_name=, falloff_type=, min_range=, max_range=)` and
  `lw_toggle_bone_flag(item, flag)` (`flag` is `"active"`,
  `"limited_range"`, `"weight_map_only"`, `"strength_multiply"`,
  `"joint_comp"`, `"joint_comp_parent"`, `"muscle_flex"`,
  `"muscle_flex_parent"`, `"bulge"`, `"bulge_parent"`, or `"twist"`) and
  `lw_set_bone_deform(item, joint_comp=, joint_comp_parent=,
  muscle_flex=, muscle_flex_parent=, bulge=, bulge_parent=, twist=)`.
  `item` must be a bone's numeric ID (from
  `lw_get_hierarchy`'s bone `id` field). Found the real UI location - a
  "Bones for &lt;object&gt;" panel reachable via the Properties button
  while a bone is current, distinct from both Motion Options (IK only)
  and the generic Modify tab. Confirmed live: `strength=0.5` showed
  "Strength: 50.0%"; `rest_length=2` showed "Rest Length: 2m";
  `falloff_type=2` (object-wide, not per-bone) changed "Inverse Distance
  ^16" to "Inverse Distance ^2"; `BoneActive`/`BoneLimitedRange`
  confirmed real argument-less toggles - a real bone defaulted to
  inactive, confirming a bone can exist and be parented while still
  off. `weight_map_name` and the `weight_map_only` toggle were later
  confirmed on a real weight-mapped mesh (`test_assets/`): turning
  "weight map only" on changed a 45-degree bend into a gentle lean, and
  switching the map from "Upper" to "Lower" straightened the top again.
  `min_range=0.5`/`max_range=3` confirmed live ("Min: 500mm"/"Max: 3m")
  once `limited_range` was toggled on first (grayed out otherwise, same
  precondition shape as DOF/Motion Blur). `rest_position=[1,2,3]`/
  `rest_rotation=[10,20,30]` confirmed live via a UI discovery: the
  "Rest Position"/"Rest Rotation" fields look like plain buttons, not
  value fields, but clicking one opens a "Set Bone Rest
  Position"/"...Rotation" requester pre-populated with the
  already-written value - a reusable confirmation technique for any
  other button-styled field. `weight_map_only`/`strength_multiply`
  confirmed real argument-less toggles via the same definitive
  arg-count test described above; `weight_map_only` has a real
  precondition, LightWave's own error dialog: "This option only applies
  when using a weight map". `BoneStrengthMultiply` maps to "Multiply
  Strength by Rest Length" (confirmed via a later full-panel
  screenshot). The muscle/joint-compensation family
  (`joint_comp`/`joint_comp_parent`/`muscle_flex`/`muscle_flex_parent`/
  `bulge`/`bulge_parent`/`twist` on `lw_toggle_bone_flag`, plus
  `lw_set_bone_deform` for their amounts) is now also confirmed live:
  `joint_comp`/`joint_comp_parent` and `bulge`/`bulge_parent` are each
  independent checkboxes, and so are `muscle_flex` ("Muscle Flexing")
  and `muscle_flex_parent` ("Parental Muscle Flexing") - each flips
  only its own box (an earlier note saying `muscle_flex` ticked both
  was wrong). `twist` only works on a **Joint**
  bone (`lw_set_bone(bone_type="joint")`, logged as `BoneType 1`); on a
  Z axis bone LightWave refuses it with "This option does not apply to
  the current bone type". Confirmed on the weight-mapped test rig:
  with WT_Upper set to Joint and its Twist checkbox on, `twist=0.5`
  showed "Twist: 50.0%". See
  `PLAN.md` "Deeper bone rigging" and "Follow-up sweep: closing the
  easy/moderate open items" for the full investigation.
- `lw_get_bone_mode(item)` / `lw_set_bone_mode(item, mode)` - the
  Bones panel's mode dropdown: "full", "full_morphed_positions",
  "faster", "limited" (`BoneMode 0-3`), set and read back. "Use Morphed
  Positions" is the second of these, not a separate checkbox, which is
  why `lw_toggle_use_morphed_positions` was refused from Faster Bones.
  All four confirmed live; the SDK header's own list (three modes) is
  out of date.
- `lw_save_endomorph(item, name)` and `lw_toggle_use_morphed_positions()`
  (ROADMAP3.md item 6 follow-up) - wrap `SaveEndomorph(name)`/
  `UseMorphedPositions()`. `SaveEndomorph` has a real, confirmed
  precondition found via LightWave's own error dialog: "Null objects
  are automatically saved with the scene" - it refuses Null objects
  outright, so the actual end-to-end bake onto a real mesh is left
  unconfirmed against this project's Null-based test rig.
  `UseMorphedPositions` is confirmed a real argument-less toggle via
  the arg-count test; its own checkbox isn't visible anywhere in
  LightWave 2019.1.5's UI (checked the full Bones panel, Motion
  Options, General Options, and Object Properties), but calling it live
  DID pop a real error dialog, "Use Morphed Positions not supported
  with the current bone mode" - closely matching a web search hit's
  LightWave 2025 documentation ("not supported with Limited Bones"),
  confirming the feature and precondition are real in
  2019.1.5 too, just gated behind a bone mode this test rig doesn't
  have. Shipped as a bare toggle with that
  caveat. See `PLAN.md` "Follow-up sweep: closing the easy/moderate
  open items" for the full investigation.
- **Morph/Endomorph control** (ROADMAP3.md item 7, the last item on
  `ROADMAP3.md`) - `lw_set_morph(item, target=, amount=)`, wrapping
  `MorphTarget`/`MorphAmount` (the classic object-to-object morph,
  distinct from vmap-based Endomorphs). No dedicated UI panel was ever
  found for this (not a Motion Modifier, no "Deform" tab in Object
  Properties) - found instead by sending `MorphAmount` directly and
  reading LightWave's own error dialog ("This option only applies when
  the current object has a morph target"), the same technique already
  used for `ObjGIRadiosityTolerance`/Fog preconditions. Confirmed live
  end to end through the actual wrapped tool: `target`/`amount` both
  logged cleanly with no error once a target was assigned first. See
  `PLAN.md` "Morph/Endomorph control" for the full investigation.

**`ROADMAP3.md` is now fully complete (all 7 items)** - see its own
"Status" section for a summary of the whole roadmap, plus its "Known
misses" and "Remaining work, ranked by usefulness" sections for what's
left and where to look first.

**Modeler**
- `modeler_run_command` - same pattern as `lw_run_command` but for
  Modeler's separate Command Port mechanism (see step 4 of [GETTING_STARTED.md](GETTING_STARTED.md#quick-start)).
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
real argument-less toggles (Cmd History logged them bare after
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
`color=[1,0,0]` + `glossiness=0.8` together showed a red
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
Different from the light/object illumination linking above -
this is about whether an object is visible to the camera, reflection/
refraction rays, radiosity, or fog at all, not which light illuminates
it. The four toggle flags confirmed live to be real argument-less
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
see `PLAN.md` "Per-object render-visibility flags" for the
writeup.
