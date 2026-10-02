"""
lw_diag_api.py

One-shot diagnostic: introspect the live lwsdk module to find real class
names/methods for item transforms, selection, surfaces, cameras, lights -
needed to extend lw_mcp_ring.py's read path. Writes findings to
_diag_api.txt. Safer than guessing from static docs, which have already
been shown to be out of sync with this build (LWMessageFuncs.info() and
IMaster.__init__ argument-count bugs found earlier).
"""
import os
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # no __file__ in this execution context
    _HERE = os.getcwd()
OUT_PATH = os.path.join(_HERE, "_diag_api.txt")

lines = []

try:
    import lwsdk
    lines.append("lwsdk imported ok")
except Exception as exc:
    lines.append("lwsdk import FAILED: %r" % (exc,))
    lwsdk = None

if lwsdk is not None:
    names = dir(lwsdk)
    lines.append("total names in lwsdk: %d" % len(names))

    interesting_substrings = [
        "Channel", "Surface", "Camera", "Light", "Item", "Select",
        "State", "Transform", "Scene", "Bound",
    ]
    matches = sorted(set(
        n for n in names
        if any(s.lower() in n.lower() for s in interesting_substrings)
    ))
    lines.append("MATCHING NAMES (%d):" % len(matches))
    for n in matches:
        lines.append("  %s" % n)

    lines.append("")
    lines.append("DETAIL PROBES:")

    def probe(expr):
        lines.append("--- %s ---" % expr)
        try:
            obj = eval(expr)
            lines.append("  repr: %r" % (obj,))
            d = [m for m in dir(obj) if not m.startswith("_")]
            lines.append("  dir (%d): %s" % (len(d), ", ".join(d)))
        except Exception as exc:
            lines.append("  FAILED: %r" % (exc,))

    for expr in [
        "lwsdk.LWItemInfo()",
        "lwsdk.LWSceneInfo()",
        "lwsdk.LWChannelInfo()",
        "lwsdk.LWStateQueryFuncs()",
        "lwsdk.LWSurfaceFuncs()",
        "lwsdk.LWCameraInfo()",
        "lwsdk.LWLightInfo()",
        "lwsdk.LWObjectInfo()",
        "lwsdk.LWObjectFuncs()",
    ]:
        probe(expr)

with open(OUT_PATH, "w") as f:
    f.write("\n".join(lines) + "\n")

try:
    if lwsdk is not None:
        lwsdk.LWMessageFuncs().info("MCP API diag written", None)
except Exception:
    pass
