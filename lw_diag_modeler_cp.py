"""
lw_diag_modeler_cp.py

Diagnose why ENABLECOMMANDPORT reported failure (result=0) for Modeler.
1. Check if port 9736 is actually bound anyway (maybe "failure" just
   means "already enabled" or similar, not a real failure).
2. Retry with the exact same port NewTek's own sample uses (10101), to
   isolate whether this is port-specific or a general execute() problem.
3. Dump the full dyna_value return for more detail than just the result
   code.
"""
import os
import socket

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # no __file__ in this execution context
    _HERE = os.getcwd()
OUT_PATH = os.path.join(_HERE, "_diag_modeler_cp.txt")
lines = []

# 1. bind test on 9736
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.bind(("0.0.0.0", 9736))
    lines.append("bind 9736: SUCCEEDED (port was free - Modeler is NOT listening on 9736)")
    s.close()
except Exception as exc:
    lines.append("bind 9736: FAILED (%r) - something IS using this port already" % (exc,))

import lwsdk

mod = lwsdk.ModCommand()
lines.append("ModCommand valid=%r" % (mod.valid(),))

cs_cpenable = mod.lookup("ENABLECOMMANDPORT")
lines.append("lookup(ENABLECOMMANDPORT)=%r" % (cs_cpenable,))

# 2. retry with NewTek's own sample port
for test_port in (10101, 9736):
    try:
        cs_options = lwsdk.marshall_dynavalues((test_port,))
        result, dyna_value = mod.execute(cs_cpenable, cs_options, lwsdk.OPSEL_USER)
        lines.append("execute port=%d -> result=%r dyna_value=%r" % (test_port, result, dyna_value))
    except Exception as exc:
        lines.append("execute port=%d FAILED: %r" % (test_port, exc))

# 3. bind test again after retries, for both ports
for test_port in (10101, 9736):
    s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s2.bind(("0.0.0.0", test_port))
        lines.append("post-retry bind %d: SUCCEEDED (still free)" % test_port)
        s2.close()
    except Exception as exc:
        lines.append("post-retry bind %d: FAILED (%r) - now in use" % (test_port, exc))

with open(OUT_PATH, "w") as f:
    f.write("\n".join(lines) + "\n")
