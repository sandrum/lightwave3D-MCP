# Status: what's done, what's left, how to proceed

A quick-glance summary. For the full build log and evidence behind
every claim below, see `PLAN.md`; for the increment-by-increment
history and rationale, see `ROADMAP.md`; for setup and the current
tool list, see `README.md`.

## Where this stands

The connector is feature-complete against its original plan. All 11
roadmap items are done except one confirmed dead end (Modeler reads) -
that's the only item left on this list now.
Everything below has been verified live against a real running
LightWave 2019.1.5 session, not just reasoned about from SDK docs -
this project's docs are demonstrably out of sync with this build in
places, so nothing here is trusted until it's been tested against the
real thing.

**Working today** (see `README.md` for the full tool-by-tool list):
- Layout writes: create items, run any of the ~800 native commands,
  keyframe animation.
- Layout reads: scene info, selection, camera/light info, transform,
  surface/material info, item hierarchy, live playhead time.
- Item relationships: parent, target, IK goal/pole - all four confirmed
  live, including a fix for two non-obvious LightWave argument quirks
  (numeric IDs vs. names; `SelectItem` not resolving names reliably for
  Camera/Light).
- Full item hierarchy including bone chains within an object (bones
  don't even need a real mesh - they attach directly to a Null via
  `AddBone`/`AddChildBone`, which made this far cheaper to verify than
  expected).
- Render/camera automation, including real completion signaling (not
  guessed timing) confirmed for both single-frame and multi-frame
  renders, and a scriptable `SetRenderDisplay` (a wrapped-method bug
  had made this look like a manual-only step).
- Modeler writes (a separate Command Port mechanism from Layout's).
- Node graphs: add, remove, move and wire/unwire nodes (`lw_add_node`,
  `lw_remove_node`, `lw_move_node`, `lw_connect_nodes`,
  `lw_disconnect_nodes`) - e.g.
  switch a surface's
  material to Principled BSDF. Works by saving the graph as text,
  editing it and loading it back, because the SDK's own `addNode` and
  `connect` turned out to hang or freeze Layout (see `PLAN.md` "Node
  Editor writing").

## What's remaining

One item left - everything else on the original plan is done.

### Modeler reads - confirmed dead end, not recommended

Thoroughly investigated (three independent methods, including against
NewTek's own bundled sample plug-in) and confirmed blocked: Modeler has
no `LWComRing`-equivalent, and its network Command Port only reaches
native/compiled commands, not Python-registered ones. See `PLAN.md`
"Modeler read path" for the full writeup. Independently re-confirmed
by checking a different, newer LightWave-MCP project (targeting
LightWave 2025.0.3+) - it hasn't solved this either, and Modeler's
command surface is byte-for-byte identical between that SDK and this
project's 2019.1.5 install (same 63 commands, zero additions in 6
years).

**To proceed, if ever:** only worth retrying given new information -
a NewTek support answer, or a newer LightWave version's SDK adding a
Modeler equivalent of `LWComRing`/Master plugins. A real but limited
substitute already exists: reading saved `.lwo` files directly from
disk (bypasses Modeler's Python API, only reflects saved state).

Bone chain traversal for `lw_get_hierarchy` - previously the other item
on this list - is now done. Turned out not to need a rigged object at
all: `AddBone`/`AddChildBone` attach directly to a Null, no real mesh
geometry required, which made real live testing far cheaper than
expected. See ROADMAP.md item 11 / PLAN.md "Bone chain traversal" for
the full writeup, including how the risk was staged down before any
real traversal loop was written (given this project's one documented
SDK-traversal crash, `LWChannelInfo`/`nextGroup`).

## Working method, if picking this back up

This project's real workflow, proven out over many rounds: guessing
from static SDK docs or plausible-sounding method signatures has
repeatedly been wrong (see `PLAN.md` for several confirmed dead ends).
What has reliably worked:

1. **Live-test everything** against a real running Layout/Modeler
   session - a fresh, untouched test item, not one a human has also
   touched manually in the meantime (a false "success" from that mix-up
   cost real time during the reparenting investigation).
2. **When a command's behavior is ambiguous**, reach for Utilities >
   Commands > Cmd History early - it logs the literal native command
   any UI action runs, and comparing a known-working manual action
   against a failed automated attempt has twice given a one-shot
   ground-truth answer where guessing the argument format would have
   taken many more rounds.
3. **When Layout stops responding as expected**, check in this order:
   a stale `server.py` process from an incomplete Claude Desktop
   restart (`Get-CimInstance Win32_Process -Filter "Name='python.exe'"`
   - check the `CreationDate` too, more than one `server.py` process
   isn't automatically a problem if their timestamps are days apart),
   then the documented Master Plugin activation flakiness (remove and
   re-add `lw_mcp_ring.py`, usually 1-3 tries), then - if that doesn't
   resolve it within 2-3 tries - whether Layout itself was restarted
   and setup step 1 (Command Port enable) needs redoing (check the
   title bar for `(CP: 9735)`, and whether the scene still has previous
   test items in it).
4. **A plug-in's UI selection can outlive its actual registration.**
   The Render Display dropdown (and, less obviously, the Master Plugins
   list) can keep showing a plug-in as selected/checked across a fresh
   Layout session even though the underlying class was never reloaded
   this session - it looks like it worked but silently doesn't. If a
   plug-in's effects aren't showing up despite the UI looking right,
   switch the selection away and back (or toggle off/on) rather than
   trusting the display. Relatedly: Add Plugins can report a file
   "could not be added" if that plug-in is currently active somewhere
   (e.g. the current Render Display) - switch away from it first, then
   reload, then switch back.
5. **Before assuming a real limitation needs a heavy setup to test**,
   check whether a cheaper path exists - bone chain traversal was
   framed as needing "get or build a rigged object," but two native
   commands on a plain Null (`AddBone`/`AddChildBone`) turned out to be
   enough. And before writing a real loop into risky SDK territory,
   stage the risk down with a temporary, non-looping probe (checked one
   step at a time, each wrapped separately) rather than writing the
   obvious `while` loop and hoping - the bone traversal probe found
   `LWI_BONE` existed and a single `first()`/`next()` pair was safe
   *before* any real loop got written, so there was nothing left to
   discover by the time it did.
