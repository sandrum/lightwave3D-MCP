# Claude ↔ LightWave 2019 MCP connector

[![tests](https://github.com/sandrum/lightwave3D-MCP/actions/workflows/tests.yml/badge.svg)](https://github.com/sandrum/lightwave3D-MCP/actions/workflows/tests.yml)

A Model Context Protocol (MCP) server that gives Claude direct, live control
over a running LightWave 2019 session - both Layout and, for writes only,
Modeler - via LightWave's official Command Port. **Both writes and reads are
proven working end to end**, confirmed live through the real `lw_ping`
(returned `"pong"`) and `lw_get_scene_info` (correctly returned the live
scene's actual items) MCP tools - see `PLAN.md` for the full build log,
including every confirmed dead end before each working mechanism was found,
and `ROADMAP.md`/`ROADMAP2.md`/`ROADMAP3.md` for what's been built, in order,
and why.

## What is an MCP?

If MCP is a new term for you: a Model Context Protocol server wraps a program
or API in a way that lets an AI assistant like Claude call it directly, in
response to plain-English requests, instead of you writing and running a
script by hand. This connector wraps LightWave's own Command Port so you can
ask Claude to build a scene, rig a character, adjust lighting, or kick off a
render - and have it actually happen in a running LightWave session - without
leaving the chat.

## Features

- **Full scene management** - create/load/save objects and scenes, manage
  LightWave's Content Directory and per-content-type sub-paths.
- **Item hierarchy & IK** - parenting, targets, goals, poles, and chain-level
  IK options (goal strength, IK/FK blending, full-time IK).
- **Bone rigging** - rest pose, weight maps, limited range, the full
  muscle/joint-compensation family, and Endomorph baking.
- **Cameras & lights** - resolution, depth of field, motion blur, falloff,
  volumetrics, and per-light object inclusion/exclusion lists.
- **Surfaces & node graphs** - read and write flat surface properties,
  introspect a surface's actual node graph (e.g. every PrincipledBSDF
  parameter), and build one: add, remove and wire/unwire nodes (e.g.
  switch a surface's material to Principled BSDF).
- **Render automation** - trigger frame/scene renders, track real completion
  state (not a time-based guess), and configure GI/radiosity/thread/tile
  settings.
- **Scene environment** - backdrop and gradient-backdrop colors, fog,
  volumetric lighting.
- **Animation** - keyframe creation with real interpolated motion, plus full
  envelope/channel reading for anything already keyframed.
- **Selection management** - build and query a real multi-item selection.
- **Generic passthrough** - `lw_run_command`/`modeler_run_command` reach any
  of the ~800 Layout / ~60 Modeler native commands directly, for anything not
  wrapped in a dedicated tool yet.
- **Extensively live-verified** - every tool here was confirmed against a
  real, running LightWave 2019.1.5 session (screenshots, Cmd History, and
  LightWave's own error dialogs as ground truth), never assumed from static
  SDK docs alone. See `PLAN.md` for the full investigation log and
  [USAGE.md](USAGE.md)'s "Detailed Tool Notes" for the caveats that came
  out of it.

## Documentation

- **[GETTING_STARTED.md](GETTING_STARTED.md)** - prerequisites, platform
  support, configuration (`.env`), and the step-by-step setup in Layout,
  Modeler and Claude Desktop.
- **[USAGE.md](USAGE.md)** - every tool, an example workflow, how the
  connector talks to LightWave, and detailed notes on each tool's
  behaviour and caveats.
- **[STATUS.md](STATUS.md)** - what's done and what's left, at a glance.
- **`PLAN.md`** / **`ROADMAP*.md`** - the full build log and history.

## Files

- `lw_enable_command_port.py` — run once inside Layout. Enables Layout writes. Working.
- `lw_mcp_ring.py` — Master plug-in enabling Layout reads via `LWComRing` (scene info, selection, camera/light/transform/surface/hierarchy/render-status/item-id queries). Needs both Add Plugins and Master Plugins activation. Working.
- `lw_mcp_render_monitor.py` — Render Display plug-in (`lwsdk.IFrameBuffer`) providing real render completion signaling for `lw_get_render_status`. Needs Add Plugins plus manual selection as the active Render Display. Working.
- `lw_enable_modeler_command_port.py` — run once inside Modeler (Add Plugins, then Utilities > Additional). Enables Modeler writes. Working.
- `lw_mcp_modeler_query.py` — Modeler read-path attempt. Works when invoked from inside Modeler's own UI, but confirmed unreachable over the network - kept for the record, not usable as-is. See `ROADMAP.md` item 5.
- `lw_mcp_config.py` — shared settings (host, ports, exchange folder) read by `server.py` and every LightWave-side script, from `.env` if present. Not a plug-in; don't load it into LightWave.
- `.env.example` — documented template for `.env` (see [GETTING_STARTED.md](GETTING_STARTED.md#configuration-optional)).
- `server.py` — MCP server Claude Desktop launches. Layout writes/reads, animation, render/camera automation, hierarchy queries, and Modeler writes all work; Modeler reads do not (see above).
- `tests/` — offline test suite (no LightWave needed), run on every push by GitHub Actions; see Tests below.
- `test_assets/` — test fixtures: `make_weight_test.py` generates `WeightTest.lwo` (a 1 m column with "Upper"/"Lower" weight maps - none of LightWave's own sample objects has a weight map), and `WeightTest_rig.lws` loads it with a two-bone rig (`WT_Lower`, `WT_Upper`). Set the Content Directory to `test_assets/` before loading the scene.
- `lwcommandport/` — NewTek's official Command Port client (copied from the LightWave install), with one real bug fixed in `Ring()` (see `PLAN.md`).
- `lw_mcp_master.py`, `lw_mcp_query.py` — two earlier, unsuccessful attempts at solving Layout reads, kept for reference/history. Do not load.
- `lw_socket_master.py` — superseded very first draft. Do not load.
- `lw_mcp_diag.py`, `lw_mcp_diag2.py`, `lw_mcp_diag3.py`, `lw_diag_modeler_cp.py` — throwaway live-introspection probe plug-ins, not needed going forward.
- `README.md`, `GETTING_STARTED.md`, `USAGE.md`, `STATUS.md` — overview, setup guide, tool guide, and current status.
- `PLAN.md` — full build log: what's verified, what failed, what to try next.
- `ROADMAP.md` — what's been built, in order, and why; the current state of every planned increment.

## Tests

The tests run without LightWave, so they work on any machine and in CI
(GitHub Actions runs them on every push and pull request).

- **`tests/unit/`** - the business logic, run against stand-ins and never
  against LightWave: the node tools end to end (connect, disconnect, add,
  remove, move, read and set input values) against a stand-in node editor;
  the node-graph text handling they rely on; the exact commands each server
  tool sends, with Layout replaced by a recorder; the input checks that stop
  the server sending something LightWave would answer with a blocking
  dialog; `.env` loading. These should only fail when the logic they cover
  changes.
- **`tests/repo_checks/`** - checks on the repository rather than logic:
  every private name used is defined, every file compiles, every tool is
  registered, docs and fixtures stay in sync, no local paths in tracked
  files.

```
pip install -r requirements-dev.txt
python -m pytest
```

The stand-in for LightWave's SDK is `tests/fake_lwsdk.py`.

What LightWave does with those commands can only be checked live, in a
running Layout - see `PLAN.md` for how each tool was verified.

## License

Released under the MIT License - see [LICENSE](LICENSE).

`lwcommandport/` is Copyright (c) LightWave Digital, LTD. All rights
reserved - it's NewTek's/LightWave Digital's own Command Port client from
the LightWave SDK, included here unmodified except for the specific bug
fixes documented in `PLAN.md`, under its own original terms rather than
this repo's MIT license.

## Support

For issues with this connector, open an issue at
[github.com/sandrum/lightwave3D-MCP](https://github.com/sandrum/lightwave3D-MCP/issues).
