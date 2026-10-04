"""
Node-graph text handling in lw_mcp_ring.py.

Every node tool (add/remove/move/connect/disconnect/set input) works by
saving a surface's node graph as ASCII, editing the text with these helpers,
and loading it back into LightWave - so a mistake here is loaded straight
into the scene. The fixture is a real graph LightWave saved: Surface, Input,
Standard (1) and Principled BSDF (1), with the Principled wired into
Surface.Material.
"""
import pytest

NODES = ["Surface", "Input", "Standard (1)", "Principled BSDF (1)"]
WIRE = {"NodeName": "Surface", "InputName": "Material",
        "InputNodeName": "Principled BSDF (1)", "InputOutputName": "Material"}


def node_names(text):
    return [line.strip()[len('Name "'):-1] for line in text.splitlines()
            if line.startswith('    Name "')]


# --- connections ----------------------------------------------------------

def test_split_connections_reads_the_wire(ring, template_graph):
    head, connections = ring._split_connections(template_graph)
    assert connections == [WIRE]
    assert "{ Connections" not in head
    assert node_names(head) == NODES


def test_split_then_join_is_byte_identical(ring, template_graph):
    head, connections = ring._split_connections(template_graph)
    assert ring._join_connections(head, connections) == template_graph


def test_join_writes_several_wires_and_reads_them_back(ring, template_graph):
    head, connections = ring._split_connections(template_graph)
    second = {"NodeName": "Principled BSDF (1)", "InputName": "Color",
              "InputNodeName": "Standard (1)", "InputOutputName": "Material"}
    _, again = ring._split_connections(ring._join_connections(head, connections + [second]))
    assert again == [WIRE, second]


def test_no_wires_means_no_connections_block(ring, template_graph):
    # Confirmed live: loading a graph with no block clears all wiring.
    head, _ = ring._split_connections(template_graph)
    text = ring._join_connections(head, [])
    assert "{ Connections" not in text
    assert ring._split_connections(text)[1] == []


def test_malformed_connections_block_is_refused(ring, template_graph):
    bad = template_graph.replace('InputName "Material"', 'Bogus "x"')
    with pytest.raises(RuntimeError):
        ring._split_connections(bad)


def test_describe(ring):
    assert ring._describe([WIRE]) == ["Principled BSDF (1).Material -> Surface.Material"]


# --- node blocks ----------------------------------------------------------

@pytest.mark.parametrize("victim", ["Standard (1)", "Principled BSDF (1)"])
def test_drop_node_block_removes_only_that_node(ring, template_graph, victim):
    head, _ = ring._split_connections(template_graph)
    after = ring._drop_node_block(head, victim)
    assert node_names(after) == [n for n in NODES if n != victim]
    assert after.count('  Server "') == 3


def test_drop_unknown_node_is_refused(ring, template_graph):
    with pytest.raises(RuntimeError):
        ring._drop_node_block(template_graph, "Nope (1)")


def test_node_coordinates_and_moving_one_node(ring, template_graph):
    assert ring._node_coordinates(template_graph, "Surface") == [-10, -10]
    lines = template_graph.splitlines()
    i = ring._coordinates_index(lines, "Principled BSDF (1)")
    lines[i] = "    Coordinates 120 -40"
    moved = "\n".join(lines)
    assert ring._node_coordinates(moved, "Principled BSDF (1)") == [120, -40]
    assert ring._node_coordinates(moved, "Standard (1)") == [0, 0]


# --- input values ---------------------------------------------------------

def test_node_attrs_reads_principled_defaults(ring, template_graph):
    attrs = {a["name"]: a for a in ring._node_attrs(template_graph.splitlines(),
                                                     "Principled BSDF (1)")}
    assert len(attrs) == 24
    assert attrs["Color"]["type"] == "vparam3"
    assert attrs["Color"]["value"] == pytest.approx([0.502, 0.502, 0.502])
    assert attrs["Roughness"]["value"] == pytest.approx([0.1])
    assert attrs["Roughness"]["format"] == "Percent"
    assert attrs["Thin"]["type"] == "int"
    assert attrs["Refraction Index"]["value"] == pytest.approx([1.5])
    assert not [a for a in attrs.values() if a["type"] == "unsupported"]


def test_rewriting_a_value_line_changes_only_that_input(ring, template_graph):
    lines = template_graph.splitlines()
    principled = {a["name"]: a for a in ring._node_attrs(lines, "Principled BSDF (1)")}
    for name, shape, values in (("Roughness", "vparam", [0.35]), ("Color", "vparam3", [1, 0, 0])):
        line = lines[principled[name]["line"]]
        indent = line[:len(line) - len(line.lstrip())]
        lines[principled[name]["line"]] = indent + ring._format_value(shape, values)
    after = {a["name"]: a for a in ring._node_attrs(lines, "Principled BSDF (1)")}
    assert after["Roughness"]["value"] == pytest.approx([0.35])
    assert after["Color"]["value"] == pytest.approx([1.0, 0.0, 0.0])
    # Standard (1) has its own "Color" input - it must be untouched.
    standard = {a["name"]: a for a in ring._node_attrs(lines, "Standard (1)")}
    assert standard["Color"]["value"] == pytest.approx([0.7843137] * 3)


def test_format_value(ring):
    assert ring._format_value("int", [3]) == "3"
    assert ring._format_value("vparam3", [1, 0, 0.5]) == "1 0 0.5"


# --- animated inputs ------------------------------------------------------

def test_input_envelope_matching(ring):
    channels = {"Roughness": [1], "Color.R": [2], "Color.G": [3], "Specular Tint": [4]}
    assert sorted(ring._input_envelope(channels, "Roughness")) == ["Roughness"]
    assert sorted(ring._input_envelope(channels, "Color")) == ["Color.G", "Color.R"]
    # "Specular" must not pick up "Specular Tint"'s envelope.
    assert ring._input_envelope(channels, "Specular") == {}
    assert ring._input_envelope(channels, "Metallic") == {}
