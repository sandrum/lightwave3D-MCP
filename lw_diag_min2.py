import lwsdk
import os
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # no __file__ in this execution context
    _HERE = os.getcwd()
OUT_PATH = os.path.join(_HERE, "_diag_min2.txt")
f = open(OUT_PATH, "w")
f.write("hello from lw_diag_min2, lwsdk=%r\n" % (lwsdk,))
f.close()
