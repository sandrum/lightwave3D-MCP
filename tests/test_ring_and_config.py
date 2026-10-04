"""
The Layout plug-in's query handling, the shared .env settings, and the
weight-mapped test asset.
"""
import json
import os
import struct
import sys

import pytest


# --- lw_mcp_ring.py: query dispatch ---------------------------------------

def read_reply(ring):
    with open(ring.RESPONSE_PATH) as f:
        return json.load(f)


def test_ping_answers_pong(ring):
    ring._handle_query("ping")
    assert read_reply(ring) == {"result": "pong"}


def test_empty_query_is_a_ping(ring):
    ring._handle_query("")
    assert read_reply(ring) == {"result": "pong"}


def test_unknown_command_is_reported_not_raised(ring):
    ring._handle_query("no_such_command whatever")
    assert read_reply(ring) == {"error": "unknown command: no_such_command"}


def test_reply_file_lives_in_the_exchange_folder(ring):
    import lw_mcp_config
    assert os.path.dirname(ring.RESPONSE_PATH) == lw_mcp_config.EXCHANGE_DIR


def test_topic_regex_takes_the_first_brace_pair(ring):
    # The ring regex was once greedy and swallowed JSON in the payload.
    m = ring._TOPIC_RE.match('{MCP} set_surface X|{"diffuse": 0.5}')
    assert m.group(1) == "MCP"
    assert m.group(2) == 'set_surface X|{"diffuse": 0.5}'


# --- lw_mcp_config.py: .env loading ---------------------------------------

@pytest.fixture
def config(monkeypatch, tmp_path):
    import lw_mcp_config
    for key in lw_mcp_config.DEFAULTS:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    monkeypatch.setattr(lw_mcp_config, "ENV_PATH", str(env_file))
    return lw_mcp_config, env_file


def test_defaults_without_env_file(config):
    cfg, _ = config
    settings = cfg.load()
    assert settings["LW_MCP_HOST"] == "localhost"
    assert settings["LW_MCP_LAYOUT_PORT"] == "9735"
    assert settings["LW_MCP_MODELER_PORT"] == "9736"


def test_env_file_format(config):
    cfg, env_file = config
    env_file.write_text(
        "# a comment\n"
        "\n"
        "LW_MCP_LAYOUT_PORT =  9800 \n"
        'LW_MCP_HOST="127.0.0.1"\n'
        "LW_MCP_MODELER_PORT=\n"          # empty means "use the default"
    )
    settings = cfg.load()
    assert settings["LW_MCP_LAYOUT_PORT"] == "9800"
    assert settings["LW_MCP_HOST"] == "127.0.0.1"
    assert settings["LW_MCP_MODELER_PORT"] == "9736"


def test_environment_variable_beats_env_file(config, monkeypatch):
    cfg, env_file = config
    env_file.write_text("LW_MCP_LAYOUT_PORT=9800\n")
    monkeypatch.setenv("LW_MCP_LAYOUT_PORT", "9900")
    assert cfg.load()["LW_MCP_LAYOUT_PORT"] == "9900"


def test_bad_port_names_the_setting(config):
    cfg, _ = config
    with pytest.raises(ValueError, match="LW_MCP_MODELER_PORT"):
        cfg._port({"LW_MCP_MODELER_PORT": "abc"}, "LW_MCP_MODELER_PORT")


def test_env_example_lists_every_setting():
    import lw_mcp_config
    root = os.path.dirname(os.path.abspath(lw_mcp_config.__file__))
    example = open(os.path.join(root, ".env.example")).read()
    for key in lw_mcp_config.DEFAULTS:
        assert key + "=" in example


# --- test_assets/make_weight_test.py --------------------------------------

def test_weight_test_object_generates_and_parses(tmp_path):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(root, "test_assets"))
    try:
        import make_weight_test
    finally:
        sys.path.pop(0)
    data, n_points, n_polys = make_weight_test.build()
    assert (n_points, n_polys) == (44, 42)
    assert data[:4] == b"FORM" and data[8:12] == b"LWO2"
    assert struct.unpack(">I", data[4:8])[0] == len(data) - 8

    points, maps, i = [], {}, 12
    while i < len(data):
        tag, size = data[i:i + 4], struct.unpack(">I", data[i + 4:i + 8])[0]
        body = data[i + 8:i + 8 + size]
        if tag == b"PNTS":
            points = [struct.unpack(">3f", body[k:k + 12]) for k in range(0, size, 12)]
        elif tag == b"VMAP":
            end = body.index(b"\x00", 6)
            name = body[6:end].decode()
            start = end + 1 + ((end + 1 - 6) % 2)
            maps[name] = {struct.unpack(">H", body[k:k + 2])[0]: struct.unpack(">f", body[k + 2:k + 6])[0]
                          for k in range(start, size, 6)}
        i += 8 + size + (size % 2)

    assert sorted(maps) == ["Lower", "Upper"]
    for index, (_x, y, _z) in enumerate(points):
        assert maps["Upper"][index] == pytest.approx(y)
        assert maps["Lower"][index] == pytest.approx(1 - y)


def test_committed_weight_test_object_matches_the_generator():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(root, "test_assets"))
    try:
        import make_weight_test
    finally:
        sys.path.pop(0)
    with open(os.path.join(root, "test_assets", "WeightTest.lwo"), "rb") as f:
        assert f.read() == make_weight_test.build()[0]
