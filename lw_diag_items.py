"""
lw_diag_items.py (v2 - defensive)

One-shot diagnostic Generic plug-in. Writes next to this script at
every stage, so we can tell exactly how far execution gets even if
something later throws. (Originally a hard-coded absolute path, in case
__file__ wasn't set when Layout loads a script plug-in; lw_mcp_ring.py
has since relied on __file__ throughout, and the current working
directory is the fallback if it's ever missing.)
"""
import os
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # no __file__ in this execution context
    _HERE = os.getcwd()
OUT_PATH = os.path.join(_HERE, "_diag_items.txt")

with open(OUT_PATH, "w") as f:
    f.write("stage 0: script started\n")

import time
with open(OUT_PATH, "a") as f:
    f.write("stage 1: time imported, now=%s\n" % time.ctime())

try:
    import lwsdk
    with open(OUT_PATH, "a") as f:
        f.write("stage 2: lwsdk imported ok\n")
except Exception as exc:
    with open(OUT_PATH, "a") as f:
        f.write("stage 2 FAILED: %r\n" % (exc,))
    raise

try:
    ii = lwsdk.LWItemInfo()
    with open(OUT_PATH, "a") as f:
        f.write("stage 3: LWItemInfo() ok: %r\n" % (ii,))
except Exception as exc:
    with open(OUT_PATH, "a") as f:
        f.write("stage 3 FAILED: %r\n" % (exc,))
    raise

lines = []
for label, item_type in (
    ("OBJECT", lwsdk.LWI_OBJECT),
    ("LIGHT", lwsdk.LWI_LIGHT),
    ("CAMERA", lwsdk.LWI_CAMERA),
):
    try:
        it = ii.first(item_type, lwsdk.LWITEM_NULL)
        while it != lwsdk.LWITEM_NULL:
            lines.append("%s: %s" % (label, ii.name(it)))
            it = ii.next(it)
    except Exception as exc:
        lines.append("%s: ERROR %r" % (label, exc))

with open(OUT_PATH, "a") as f:
    f.write("stage 4: enumeration done\n")
    f.write("\n".join(lines) + "\n")
    f.write("DONE\n")
