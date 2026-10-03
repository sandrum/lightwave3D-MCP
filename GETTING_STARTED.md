# Getting started

How to install and set up the Claude <-> LightWave 2019 connector. Once
it's running, see [USAGE.md](USAGE.md) for the tools and how they behave.

## Prerequisites

- LightWave 3D 2019.1.5 (Layout, and optionally Modeler)
- Python 3.x
- Claude Desktop
- Windows (developed and tested) or macOS (expected to work, untested -
  see below)

## Platform support

Everything here was developed and tested on **Windows**. **macOS** is
expected to work but has **not been tested**: LightWave 2019 runs on
both, `server.py` is plain Python talking to LightWave over the network
on `localhost`, every path is built with Python's portable path
functions, and the bundled `lwcommandport` client handles macOS itself
(its only Windows-specific code - registry lookup for *launching*
LightWave - isn't used here). The open question is whether macOS
LightWave exposes every SDK call the LightWave-side scripts use in the
same way. If you try it on a Mac, an issue reporting how it went is very
welcome. Where the steps differ by platform, both are shown.

## Configuration (optional)

Everything works out of the box with the defaults below. To change them,
copy `.env.example` to `.env` in the repo folder and edit it - `.env` is
git-ignored, so your values stay on your machine. From the repo folder:

Windows (Command Prompt or PowerShell):

```
copy .env.example .env
```

macOS (Terminal), or Git Bash on Windows:

```
cp .env.example .env
```

| Setting | Default | What it is |
| --- | --- | --- |
| `LW_MCP_HOST` | `localhost` | Machine LightWave runs on, as seen from `server.py`. |
| `LW_MCP_LAYOUT_PORT` | `9735` | Layout's Command Port. |
| `LW_MCP_MODELER_PORT` | `9736` | Modeler's Command Port (must differ from Layout's). |
| `LW_MCP_EXCHANGE_DIR` | *(the repo folder)* | Where `server.py` and the LightWave scripts exchange reply/status/debug files. |

For example, to move the ports and keep the exchange files out of the
repo folder:

```
LW_MCP_LAYOUT_PORT=9835
LW_MCP_MODELER_PORT=9836
# Windows:
LW_MCP_EXCHANGE_DIR=%TEMP%\lightwave_mcp
# macOS (use this line instead of the one above):
# LW_MCP_EXCHANGE_DIR=~/lightwave_mcp
```

Both sides read the same file through `lw_mcp_config.py`: `server.py`
and every script you load into LightWave. A real environment variable
of the same name overrides `.env`. After changing a value, restart
Claude Desktop **and** reload the LightWave scripts (or restart Layout).
The ports and folders shown in the steps below are the defaults.

**`.env` file format**

- One setting per line, as `KEY=value`. Spaces around the `=` are
  ignored.
- Lines starting with `#` are comments; blank lines are ignored.
- Quotes are optional: `LW_MCP_HOST="127.0.0.1"` and
  `LW_MCP_HOST=127.0.0.1` mean the same thing.
- Any setting you leave out (or leave empty) keeps its default, so your
  `.env` only needs the lines you want to change.
- In `LW_MCP_EXCHANGE_DIR`, `~` (your home folder) and environment
  variables - `%TEMP%` style on Windows, `$TMPDIR` style on macOS - are
  expanded, and the folder is created if it doesn't exist.

**Where it has to be.** `.env` is read from the folder that contains
`lw_mcp_config.py` - the repo folder. So load the LightWave scripts
(`lw_enable_command_port.py`, `lw_mcp_ring.py`, ...) straight from the
repo folder: a copy of a script placed somewhere else won't find
`lw_mcp_config.py` or your `.env`.

**If a value is wrong.** A setting that can't be used - for example a
port that isn't a number - stops `server.py` or the LightWave script
with an error naming the setting and the `.env` file it came from, e.g.
`LW_MCP_MODELER_PORT must be a port number, got 'abc' (check
C:\path\to\LightwaveMCP\.env)`. A port that LightWave can't use shows
up as `lw_enable_command_port.py` reporting "FAILED to enable" instead
of the `(CP: ...)` title bar.

## Quick Start

**1. Enable the Command Port (once per Layout session)**

Utilities → Plugins → Add Plugins → select `lw_enable_command_port.py`.
It runs automatically on load (it's a "single-shot" plug-in) - the title
bar should change to show `(CP: 9735)` (or your `LW_MCP_LAYOUT_PORT`).

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
bar should change to show `(CP: 9736)` (or your `LW_MCP_MODELER_PORT`). Note: the script may report
"failure" internally (a real bug in this SDK build's `ModCommand.
execute()` return code, not an actual failure) - trust the title bar,
not any printed result.

**5. Install the MCP server's dependency**

```
pip install "mcp[cli]" --break-system-packages
```

On macOS, use `pip3` if `pip` isn't found.

**6. Point Claude Desktop at `server.py`**

Open Claude Desktop's config file - Settings → Developer → Edit Config
opens it directly. It lives at:

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add the `lightwave` server, using the absolute path of your own clone of
this repo.

Windows (JSON needs each backslash doubled, or use forward slashes):

```json
{
  "mcpServers": {
    "lightwave": {
      "command": "python",
      "args": ["C:\\path\\to\\LightwaveMCP\\server.py"]
    }
  }
}
```

macOS (`python3`, since macOS has no `python` command by default):

```json
{
  "mcpServers": {
    "lightwave": {
      "command": "python3",
      "args": ["/path/to/LightwaveMCP/server.py"]
    }
  }
}
```

If Claude Desktop can't start the server, give the full path to your
Python instead of `python`/`python3` (`where python` on Windows,
`which python3` on macOS).

Restart Claude Desktop.

**7. Test**

With Layout running and steps 1-2 done, ask Claude to create a Null
item, then ask it to ping LightWave or get scene info. Check Layout -
the Null should appear immediately, and the ping/scene-info replies
should reflect the live scene.

If you ever see writes silently stop working (success responses but
nothing appears in Layout), suspect a hung or duplicate Layout process
first - more than one Layout process can end up running
simultaneously (seen on Windows as several `Layout.exe` entries in Task
Manager), with the MCP query listener bound to a stale one while
the visible window is a different, disconnected process. Check the
Scene Editor (Utilities → Editors → Scene Editor) against query
responses to catch this; a clean restart of all Layout processes
reliably fixes it.

## Next

See [USAGE.md](USAGE.md) for every tool, an example workflow, and the
detailed notes on what each one does in practice.
