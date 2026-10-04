"""
make_weight_test.py

Writes WeightTest.lwo, a small test object for the bone/weight-map tools:
a 0.2 x 1.0 x 0.2 m column standing on the origin, split into SEGMENTS
rings along Y, with two weight maps -

  "Upper"  0 at the bottom (y = 0) rising linearly to 1 at the top (y = 1)
  "Lower"  the reverse: 1 at the bottom, 0 at the top

- and one surface, "WeightTest". None of the objects shipped with
LightWave 2019.1.5 has a weight map, so this provides one that's the same
every time it's generated.

Plain Python 3, no dependencies. Writes LightWave's LWO2 format directly
(an IFF "FORM ... LWO2" file: TAGS, LAYR, PNTS, BBOX, VMAP, POLS, PTAG and
SURF chunks).

Usage:  python make_weight_test.py [output.lwo]
"""
import os
import struct
import sys

SEGMENTS = 10
HALF_WIDTH = 0.1
HEIGHT = 1.0
SURFACE = "WeightTest"


def _s0(text):
    """LWO null-terminated string, padded to an even length."""
    data = text.encode("ascii") + b"\x00"
    return data + (b"\x00" if len(data) % 2 else b"")


def _vx(index):
    """LWO variable-length index: 2 bytes below 0xFF00, else 4."""
    if index < 0xFF00:
        return struct.pack(">H", index)
    return struct.pack(">I", index | 0xFF000000)


def _chunk(tag, data):
    out = tag + struct.pack(">I", len(data)) + data
    return out + (b"\x00" if len(data) % 2 else b"")


def build():
    # Points: one ring of 4 corners per level, bottom to top. Viewed from
    # +Y the corners go counter-clockwise: (-x,-z), (+x,-z), (+x,+z), (-x,+z).
    corners = [(-HALF_WIDTH, -HALF_WIDTH), (HALF_WIDTH, -HALF_WIDTH),
               (HALF_WIDTH, HALF_WIDTH), (-HALF_WIDTH, HALF_WIDTH)]
    points = []
    for level in range(SEGMENTS + 1):
        y = HEIGHT * level / SEGMENTS
        for x, z in corners:
            points.append((x, y, z))

    def idx(level, corner):
        return level * 4 + corner % 4

    # Polygons. LightWave treats a polygon's front as the side from which
    # its vertices run clockwise.
    polygons = []
    for level in range(SEGMENTS):
        for c in range(4):
            polygons.append([idx(level, c), idx(level + 1, c),
                             idx(level + 1, c + 1), idx(level, c + 1)])
    polygons.append([idx(0, 0), idx(0, 1), idx(0, 2), idx(0, 3)])            # bottom cap
    top = SEGMENTS
    polygons.append([idx(top, 3), idx(top, 2), idx(top, 1), idx(top, 0)])    # top cap

    chunks = [_chunk(b"TAGS", _s0(SURFACE))]
    chunks.append(_chunk(b"LAYR", struct.pack(">HH3f", 0, 0, 0.0, 0.0, 0.0) + _s0("")))
    chunks.append(_chunk(b"PNTS", b"".join(struct.pack(">3f", *p) for p in points)))
    xs, ys, zs = zip(*points)
    chunks.append(_chunk(b"BBOX", struct.pack(">6f", min(xs), min(ys), min(zs),
                                              max(xs), max(ys), max(zs))))
    for name, weight in (("Upper", lambda y: y / HEIGHT),
                         ("Lower", lambda y: 1.0 - y / HEIGHT)):
        body = b"WGHT" + struct.pack(">H", 1) + _s0(name)
        body += b"".join(_vx(i) + struct.pack(">f", weight(p[1])) for i, p in enumerate(points))
        chunks.append(_chunk(b"VMAP", body))
    pols = b"FACE"
    for poly in polygons:
        pols += struct.pack(">H", len(poly)) + b"".join(_vx(i) for i in poly)
    chunks.append(_chunk(b"POLS", pols))
    chunks.append(_chunk(b"PTAG", b"SURF" + b"".join(
        _vx(i) + struct.pack(">H", 0) for i in range(len(polygons)))))
    # Surface: a light grey, plus the source surface name (empty).
    colr = struct.pack(">H", 14) + struct.pack(">3f", 0.7, 0.7, 0.7) + _vx(0)
    diff = struct.pack(">H", 6) + struct.pack(">f", 1.0) + _vx(0)
    chunks.append(_chunk(b"SURF", _s0(SURFACE) + _s0("") + b"COLR" + colr + b"DIFF" + diff))

    body = b"LWO2" + b"".join(chunks)
    return b"FORM" + struct.pack(">I", len(body)) + body, len(points), len(polygons)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "WeightTest.lwo")
    data, n_points, n_polys = build()
    with open(out, "wb") as f:
        f.write(data)
    print("wrote %s: %d points, %d polygons, weight maps Upper/Lower, %d bytes"
          % (out, n_points, n_polys, len(data)))


if __name__ == "__main__":
    main()
