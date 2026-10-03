"""
lw_enable_modeler_command_port.py

Enables Modeler's Command Port, mirroring lw_enable_command_port.py for
Layout - but Modeler uses a completely different mechanism. There's no
lwsdk.LWCommandPort().enable() equivalent; instead you go through
Modeler's ModCommand execution system and look up/execute a native
command called "ENABLECOMMANDPORT". Based on NewTek's own bundled sample:
support/plugins/scripts/Python/Modeler/CommandSequence/
enable_command_port_cs_ss.py (the "_ss" = single-shot CommandSequence
format).

Uses port 9736 (Layout's Command Port uses 9735 - see
lw_enable_command_port.py) so both apps can run and be controlled at the
same time.

IMPORTANT (confirmed live): unlike Layout's Generic single-shot scripts,
Modeler treats this as a "Modeling Command" plug-in - loading it via Add
Plugins only REGISTERS it. It must then be invoked separately via
Utilities > Additional > lw_enable_modeler_command_port (alphabetical in
that big command list) to actually run.

ALSO CONFIRMED LIVE: mod.execute()'s reported result code is unreliable
- it returned 0 ("failure" per NewTek's own sample comment) both when
the port was fresh/never bound AND when the port was already
successfully bound and listening (verified via a UDP bind-conflict test:
binding 0.0.0.0:9736 from a second socket failed with "address already
in use" immediately after this script ran, proving Modeler really was
listening despite the "failure" result). Don't trust the return code -
check the title bar for "(CP: 9736)" or do a bind test instead. This
joins LWMessageFuncs.info()'s arg count and IMaster.__init__'s arg count
as confirmed real bugs/inconsistencies in this SDK build's Python
bindings.

Load via: Modeler > Utilities > Plugins > Add Plugins >
lw_enable_modeler_command_port.py, then Utilities > Additional >
lw_enable_modeler_command_port to actually run it. Writes its result to
_modeler_enable_result.txt next to this file, since print() output
isn't reliably visible in this environment (same lesson learned from the
Layout side - see PLAN.md).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # in case LightWave hasn't put this folder on sys.path
    sys.path.insert(0, _HERE)
import lw_mcp_config  # noqa: E402 - shared ports/exchange folder, see .env.example

OUT_PATH = lw_mcp_config.exchange_path("_modeler_enable_result.txt")

PORT = lw_mcp_config.MODELER_PORT

lines = ["stage 0: script started"]

try:
    import lwsdk
    lines.append("stage 1: lwsdk imported ok")
except ImportError:
    lines.append("stage 1 FAILED: lwsdk not importable - not running inside LightWave?")
    lwsdk = None

if lwsdk is not None:
    try:
        mod = lwsdk.ModCommand()
        lines.append("stage 2: ModCommand() created, valid=%r" % (mod.valid(),))
    except Exception as exc:
        lines.append("stage 2 FAILED: %r" % (exc,))
        mod = None

    if mod is not None and mod.valid():
        try:
            cs_options = lwsdk.marshall_dynavalues((PORT,))
            cs_cpenable = mod.lookup("ENABLECOMMANDPORT")
            lines.append("stage 3: lookup(ENABLECOMMANDPORT) = %r" % (cs_cpenable,))
            if cs_cpenable:
                result, dyna_value = mod.execute(cs_cpenable, cs_options, lwsdk.OPSEL_USER)
                lines.append("stage 4: execute result=%r (1=success, 0=failure), port=%d" % (result, PORT))
            else:
                lines.append("stage 3 FAILED: ENABLECOMMANDPORT command not found")
        except Exception as exc:
            lines.append("stage 3/4 FAILED: %r" % (exc,))

with open(OUT_PATH, "w") as f:
    f.write("\n".join(lines) + "\n")
