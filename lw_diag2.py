import lwsdk
lwsdk.LWMessageFuncs().info("DIAG2 SCRIPT RAN", None)

import os
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # no __file__ in this execution context
    _HERE = os.getcwd()
OUT_PATH = os.path.join(_HERE, "_diag2.txt")
with open(OUT_PATH, "w") as f:
    f.write("diag2 ran\n")
