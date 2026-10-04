"""
server.py's MCP tools, with Layout replaced by a recorder (`fake_layout`)
and the read path by canned replies (`fake_query`).

Two kinds of check:
- refusals: input LightWave would answer with a modal error dialog (which
  blocks Layout until someone clicks OK) must be refused before anything is
  sent - so these assert fake_layout.calls stays empty;
- command sequences: the exact commands a tool sends, in the form Cmd
  History shows them, as confirmed live (see PLAN.md).
"""
import asyncio
import inspect
import json

import pytest


def reply(result_json):
    return json.loads(result_json)


# --- registration ---------------------------------------------------------

def test_every_tool_function_is_registered_except_the_withdrawn_ones(server):
    registered = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    defined = {name for name, obj in vars(server).items()
               if inspect.isfunction(obj) and obj.__module__ == "server"
               and (name.startswith("lw_") or name.startswith("modeler_"))}
    # lw_set_fog is kept for reference but withdrawn: the Fog* commands are
    # no-ops in LightWave 2019 (PLAN.md "Fog commands have no effect").
    assert defined - registered == {"lw_set_fog"}


def test_mtime_of_a_missing_file_is_none(server, tmp_path):
    # The reply file briefly doesn't exist while the plug-in replaces it.
    assert server._mtime(str(tmp_path / "nope.json")) is None


# --- bones ----------------------------------------------------------------

def test_set_bone_mode_selects_then_sets(server, fake_layout, fake_query):
    fake_query.replies["ids"] = {"WeightTest": "10000000"}
    fake_query.replies["get_bone_mode"] = {"result": {"bone_mode": "full_morphed_positions"}}
    result = reply(server.lw_set_bone_mode("WeightTest", "full_morphed_positions"))
    assert fake_layout.calls == ["SelectItem 10000000", "BoneMode 1"]
    assert result["state"]["bone_mode"] == "full_morphed_positions"


def test_set_bone_mode_refuses_unknown_mode(server, fake_layout, fake_query):
    assert "error" in reply(server.lw_set_bone_mode("WeightTest", "sideways"))
    assert fake_layout.calls == []


def test_set_bone_type(server, fake_layout, fake_query):
    server.lw_set_bone("40010000", bone_type="joint")
    assert fake_layout.calls == ["SelectItem 40010000", "BoneType 1"]


def test_set_bone_refuses_unknown_type(server, fake_layout, fake_query):
    assert "error" in reply(server.lw_set_bone("40010000", bone_type="elbow"))
    assert fake_layout.calls == []


# --- lights ---------------------------------------------------------------

@pytest.mark.parametrize("value", [2, -1])
def test_light_falloff_only_takes_0_or_1(server, fake_layout, fake_query, value):
    # LightWave 2019's Intensity Falloff is Off / Inv Distance^2 only.
    assert "error" in reply(server.lw_set_light("Light", falloff_type=value))
    assert fake_layout.calls == []


def test_light_falloff_is_sent_after_selecting_the_light(server, fake_layout, fake_query):
    fake_query.replies["ids"] = {"Light": "20000000"}
    server.lw_set_light("Light", falloff_type=1)
    assert fake_layout.calls == ["SelectItem 20000000", "LightFalloffType 1"]


# --- render settings ------------------------------------------------------

def test_gpu_noise_filter_is_refused(server, fake_layout, fake_query):
    # NoiseFilter 2 pops a modal "no supported GPU" dialog on machines
    # without one.
    assert "error" in reply(server.lw_set_render_options(noise_filter="gpu"))
    assert fake_layout.calls == []


def test_render_options_send_the_confirmed_commands(server, fake_layout, fake_query):
    server.lw_set_render_options(raytrace_reflection=False, polygon_intersection="watertight",
                                 noise_filter="cpu", ray_recursion_limit=12)
    assert fake_layout.calls == ["RayTraceReflection 0", "RayRecursionLimit 12",
                                 "RenderAlgorithm 1", "NoiseFilter 1"]


def test_antialiasing_toggles_adaptive_only_when_it_differs(server, fake_layout, fake_query):
    fake_query.replies["ids"] = {"Camera": "30000000"}
    fake_query.replies["get_antialiasing"] = {"result": {"adaptive_sampling": 1}}
    server.lw_set_antialiasing("Camera", adaptive_sampling=True, min_samples=2)
    assert fake_layout.calls == ["SelectItem 30000000", "MinAntialiasing 2"]

    fake_layout.calls[:] = []
    server.lw_set_antialiasing("Camera", adaptive_sampling=False)
    assert fake_layout.calls == ["SelectItem 30000000", "AdaptiveSampling"]


# --- colour space ---------------------------------------------------------

AVAILABLE = {"result": {"available": {"rgb": ["Linear", "sRGB", "rec709", "Cineon", "ciexyz"],
                                      "alpha": ["Linear", "sRGB", "rec709"]}}}


def test_colour_space_names_are_matched_case_insensitively(server, fake_layout, fake_query):
    fake_query.replies["get_color_space"] = AVAILABLE
    server.lw_set_color_space(final_render="srgb", auto_sense=True)
    assert fake_layout.calls == ["ColorSpaceOutput sRGB", "ColorSpaceAutoSense 1"]


def test_unknown_colour_space_is_refused(server, fake_layout, fake_query):
    fake_query.replies["get_color_space"] = AVAILABLE
    assert "error" in reply(server.lw_set_color_space(final_render="bogus"))
    assert fake_layout.calls == []


def test_alpha_slot_only_takes_alpha_spaces(server, fake_layout, fake_query):
    fake_query.replies["get_color_space"] = AVAILABLE
    assert "error" in reply(server.lw_set_color_space(alpha="Cineon"))
    assert fake_layout.calls == []


# --- per-object GI --------------------------------------------------------

def gi_state(enabled=True, mode="global"):
    return {"result": {"gi_enabled": enabled, "gi_mode_name": mode}}


def test_object_gi_refused_when_gi_is_off(server, fake_layout, fake_query):
    fake_query.replies["ids"] = {"connector_01": "10000001"}
    fake_query.replies["get_object_gi"] = gi_state(enabled=False)
    assert "error" in reply(server.lw_set_object_gi("connector_01", mode="interpolated",
                                                    angular_tolerance=40))
    assert fake_layout.calls == []


def test_object_gi_refused_in_the_wrong_mode(server, fake_layout, fake_query):
    fake_query.replies["ids"] = {"connector_01": "10000001"}
    fake_query.replies["get_object_gi"] = gi_state(mode="global")
    assert "error" in reply(server.lw_set_object_gi("connector_01", angular_tolerance=40))
    assert "error" in reply(server.lw_set_object_gi("connector_01", mode="interpolated",
                                                    brute_force_rays=4))
    assert fake_layout.calls == []


def test_object_gi_sends_degrees_unconverted(server, fake_layout, fake_query):
    # Cmd History logs 1 - cos(angle), but the command takes plain degrees.
    fake_query.replies["ids"] = {"connector_01": "10000001"}
    fake_query.replies["get_object_gi"] = gi_state()
    server.lw_set_object_gi("connector_01", mode="interpolated", angular_tolerance=35,
                            primary_rays=200)
    assert fake_layout.calls == ["SelectItem 10000001", "ObjGIUseGlobal 2",
                                 "ObjGIRadiosityTolerance 35", "ObjGIRaysPerEvaluation 200"]


# --- node tools: argument packing -----------------------------------------

def test_connect_nodes_passes_names_to_the_plug_in(server, fake_query):
    server.lw_connect_nodes(from_node="Standard (1)", input_name="Material")
    assert fake_query.asked[-1] == ("connect_nodes",
                                    "CONNECTOR|Standard (1)|Surface|Material|")


def test_set_node_input_encodes_lists_as_json(server, fake_query):
    server.lw_set_node_input("Principled BSDF (1)", "Color", [1, 0, 0])
    assert fake_query.asked[-1] == ("set_node_input",
                                    "CONNECTOR|Principled BSDF (1)|Color|[1, 0, 0]")


def test_node_key_tools_pass_their_arguments_to_the_plug_in(server, fake_query):
    server.lw_set_node_key("Principled BSDF (1)", "Roughness", 30, 0.7)
    assert fake_query.asked[-1] == ("set_node_key", "CONNECTOR|Principled BSDF (1)|Roughness|30|0.7")
    server.lw_delete_node_key("Principled BSDF (1)", "Roughness", 15)
    assert fake_query.asked[-1] == ("delete_node_key", "CONNECTOR|Principled BSDF (1)|Roughness|15")

