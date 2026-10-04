"""
The plug-in's node tools, run end to end against the lwsdk stand-in
(tests/fake_lwsdk.py): each one checks names against the graph, saves it,
rewrites the text, loads it back, saves again and reports what it finds.

The surface starts as the real graph LightWave saved for CONNECTOR: Surface,
Input, Standard (1) and Principled BSDF (1), with the Principled wired into
Surface.Material. `surface.loads` counts graph loads, so a refused call can
be checked to have changed nothing.
"""
import os

import pytest

import fake_lwsdk

PRINCIPLED_WIRE = "Principled BSDF (1).Material -> Surface.Material"


@pytest.fixture
def surface(fake_lwsdk_scene, template_graph):
    return fake_lwsdk_scene.add_surface("CONNECTOR", template_graph)


def node_list(ring, surface):
    return [name for name, _type in fake_lwsdk._nodes(surface)]


@pytest.fixture(autouse=True)
def scratch_file_is_always_cleaned_up(ring):
    yield
    import lw_mcp_config
    assert not os.path.exists(lw_mcp_config.exchange_path(ring._REWIRE_SCRATCH))


# --- connect / disconnect -------------------------------------------------

def test_connect_replaces_what_fed_the_input(ring, surface):
    result = ring._rewire_nodes("CONNECTOR", "Surface", "Material", "Standard (1)", "")
    assert result["connected"] is True
    assert result["before"] == [PRINCIPLED_WIRE]
    assert result["connections"] == ["Standard (1).Material -> Surface.Material"]
    assert surface.loads == 1


def test_connect_adds_alongside_other_wires(ring, surface):
    result = ring._rewire_nodes("CONNECTOR", "Principled BSDF (1)", "Roughness", "Input", "Item ID")
    assert result["connected"] is True
    assert result["connections"] == [PRINCIPLED_WIRE,
                                     "Input.Item ID -> Principled BSDF (1).Roughness"]


@pytest.mark.parametrize("to_node, input_name, from_node, output_name, expected", [
    ("Surface", "Material", "Nope (1)", "", "node not found"),
    ("Nope (1)", "Material", "Standard (1)", "", "node not found"),
    ("Surface", "Sparkle", "Standard (1)", "", "input not found"),
    ("Surface", "Material", "Standard (1)", "Sparkle", "output not found"),
])
def test_connect_refuses_unknown_names_without_loading(ring, surface, to_node, input_name,
                                                       from_node, output_name, expected):
    result = ring._rewire_nodes("CONNECTOR", to_node, input_name, from_node, output_name)
    assert expected in result["error"]
    assert surface.loads == 0


def test_connect_refuses_quotes_in_names(ring, surface):
    assert "error" in ring._rewire_nodes("CONNECTOR", "Surface", 'Mat"erial', "Standard (1)", "")
    assert surface.loads == 0


def test_disconnect(ring, surface):
    result = ring._rewire_nodes("CONNECTOR", "Surface", "Material", None, None)
    assert result["disconnected"] is True
    assert result["connections"] == []


def test_disconnect_with_nothing_connected_is_refused(ring, surface):
    ring._rewire_nodes("CONNECTOR", "Surface", "Material", None, None)
    loads = surface.loads
    result = ring._rewire_nodes("CONNECTOR", "Surface", "Material", None, None)
    assert "nothing connected" in result["error"]
    assert surface.loads == loads


def test_unknown_surface(ring, surface):
    assert "surface not found" in ring._rewire_nodes("NOPE", "Surface", "Material",
                                                     "Standard (1)", "")["error"]


# --- add / remove / move --------------------------------------------------

def test_add_node_takes_the_next_free_number(ring, surface):
    result = ring._add_node("CONNECTOR", "Standard", 120, -40)
    assert result["node_name"] == "Standard (2)"
    assert result["server_user_name"] == "Standard"
    assert node_list(ring, surface)[-1] == "Standard (2)"
    assert ring._node_coordinates(surface.text, "Standard (2)") == [120, -40]


def test_add_first_node_of_a_type(ring, fake_lwsdk_scene, template_graph):
    head, _ = ring._split_connections(template_graph)
    surface = fake_lwsdk_scene.add_surface("CONNECTOR", ring._drop_node_block(head, "Standard (1)"))
    assert ring._add_node("CONNECTOR", "Standard")["node_name"] == "Standard (1)"
    assert surface.loads == 1


def test_add_node_refuses_quotes(ring, surface):
    assert "error" in ring._add_node("CONNECTOR", 'Bad"Type')
    assert surface.loads == 0


def test_remove_node_takes_its_wires_with_it(ring, surface):
    result = ring._remove_node("CONNECTOR", "Principled BSDF (1)")
    assert result["removed"] is True
    assert result["wires_removed"] == [PRINCIPLED_WIRE]
    assert result["connections"] == []
    assert "Principled BSDF (1)" not in node_list(ring, surface)


def test_remove_unwired_node_keeps_other_wires(ring, surface):
    result = ring._remove_node("CONNECTOR", "Standard (1)")
    assert result["wires_removed"] == []
    assert result["connections"] == [PRINCIPLED_WIRE]


@pytest.mark.parametrize("node", ["Surface", "Input"])
def test_built_in_nodes_cannot_be_removed(ring, surface, node):
    assert "built into every surface" in ring._remove_node("CONNECTOR", node)["error"]
    assert surface.loads == 0


def test_move_node(ring, surface):
    result = ring._move_node("CONNECTOR", "Principled BSDF (1)", 200, 0)
    assert result["before"] == [0, 0]
    assert result["coordinates"] == [200, 0]
    assert result["moved"] is True


# --- input values ---------------------------------------------------------

def test_get_node_values(ring, surface):
    result = ring._get_node_values("CONNECTOR", "Principled BSDF (1)")
    inputs = {i["name"]: i for i in result["inputs"]}
    assert len(inputs) == 24
    assert inputs["Roughness"]["value"] == pytest.approx([0.1])
    assert not any(i["enveloped"] for i in inputs.values())
    assert surface.loads == 0          # reading never loads anything


def test_get_node_values_reports_an_envelope(ring, surface):
    surface.envelopes = {"Principled BSDF (1)": {"Roughness": [(0.0, 0.1, 0), (1.0, 0.5, 0)]}}
    inputs = {i["name"]: i for i in ring._get_node_values("CONNECTOR", "Principled BSDF (1)")["inputs"]}
    assert inputs["Roughness"]["enveloped"] is True
    keys = inputs["Roughness"]["envelope"]["Roughness"]
    assert [k["frame"] for k in keys] == [0.0, 30.0]
    assert [k["value"] for k in keys] == [0.1, 0.5]
    assert inputs["Metallic"]["enveloped"] is False


@pytest.mark.parametrize("input_name, values", [("Roughness", [0.35]), ("Color", [1, 0, 0])])
def test_set_node_input(ring, surface, input_name, values):
    result = ring._set_node_input("CONNECTOR", "Principled BSDF (1)", input_name, values)
    assert result["set"] is True
    assert result["value"] == pytest.approx(values)
    assert "warning" not in result


def test_set_node_input_leaves_other_nodes_alone(ring, surface):
    ring._set_node_input("CONNECTOR", "Principled BSDF (1)", "Color", [1, 0, 0])
    standard = {i["name"]: i for i in ring._get_node_values("CONNECTOR", "Standard (1)")["inputs"]}
    assert standard["Color"]["value"] == pytest.approx([0.7843137] * 3)


@pytest.mark.parametrize("input_name, values, expected", [
    ("Color", [0.5], "takes 3 number(s)"),
    ("Thin", [0.5], "whole number"),
    ("Sparkle", [1], "no stored value"),
])
def test_set_node_input_refuses_bad_values(ring, surface, input_name, values, expected):
    result = ring._set_node_input("CONNECTOR", "Principled BSDF (1)", input_name, values)
    assert expected in result["error"]
    assert surface.loads == 0


def test_set_node_input_refuses_an_animated_input(ring, surface):
    surface.envelopes = {"Principled BSDF (1)": {"Roughness": [(0.0, 0.1, 0)]}}
    result = ring._set_node_input("CONNECTOR", "Principled BSDF (1)", "Roughness", [0.3])
    assert "animated" in result["error"]
    assert surface.loads == 0


def test_set_node_input_warns_when_a_wire_overrides_it(ring, surface):
    ring._rewire_nodes("CONNECTOR", "Principled BSDF (1)", "Roughness", "Input", "Item ID")
    result = ring._set_node_input("CONNECTOR", "Principled BSDF (1)", "Roughness", [0.3])
    assert result["set"] is True
    assert "wire feeds this input" in result["warning"]
