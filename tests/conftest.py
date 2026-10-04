"""
Shared test setup.

tests/unit/ holds the unit tests: business logic run against stand-ins, never
against LightWave or any other real endpoint. tests/repo_checks/ holds checks
on the repository itself (static analysis, docs and fixtures in sync, no
local paths) - useful, but not unit tests.

What LightWave itself does with a command still needs checking live (see
PLAN.md); these tests don't replace that.

Stand-ins:

- tests/fake_lwsdk.py replaces LightWave's `lwsdk` module, so lw_mcp_ring.py
  imports and its node tools run end to end (`fake_lwsdk` fixture);
- `fake_layout` replaces server.py's connection to Layout with a recorder,
  so a test can check exactly which commands a tool sends - or that it sends
  none;
- `fake_query` replaces server.py's read path with canned replies.

The exchange folder is pointed at a temporary directory, so tests never write
reply files into the repo.
"""
import os
import sys
import tempfile
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Keep reply/debug files out of the repo - must be set before lw_mcp_config
# is first imported.
os.environ.setdefault("LW_MCP_EXCHANGE_DIR", tempfile.mkdtemp(prefix="lw_mcp_tests_"))


TESTS = os.path.dirname(os.path.abspath(__file__))
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)

import fake_lwsdk  # noqa: E402

sys.modules.setdefault("lwsdk", fake_lwsdk)


class FakeLayout(object):
    """Records every command a tool sends instead of sending it.

    `calls` is a list of strings in the same form Cmd History shows, e.g.
    "SelectItem 10000000" or "BoneMode 1"."""

    def __init__(self):
        self.calls = []

    def _send_command(self, command, args=None):
        args = list(args or [])
        self.calls.append(" ".join([command] + [str(a) for a in args]))

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def method(*args):
            self._send_command(name, args)
        return method


@pytest.fixture
def server():
    import server as server_module
    return server_module


@pytest.fixture
def fake_layout(server, monkeypatch):
    layout = FakeLayout()
    monkeypatch.setattr(server, "_layout", lambda: layout)
    monkeypatch.setattr(server.time, "sleep", lambda seconds: None)
    return layout


@pytest.fixture
def fake_query(server, monkeypatch):
    """Replace server._query (the read path) with canned replies.

    Tests fill `replies` with {command: reply_dict}; anything not listed
    answers like a timed-out listener would. Every query made is recorded in
    `asked`."""
    state = types.SimpleNamespace(replies={}, asked=[])

    def _query(command, arg="", timeout=5.0):
        state.asked.append((command, arg))
        if command == "get_item_id":
            return {"result": {"name": arg, "id": state.replies.get("ids", {}).get(arg)}}
        if command in state.replies:
            return state.replies[command]
        return {"error": "timed out"}

    monkeypatch.setattr(server, "_query", _query)
    return state


@pytest.fixture
def ring():
    import lw_mcp_ring
    return lw_mcp_ring


@pytest.fixture
def fake_lwsdk_scene():
    """A clean stand-in scene; tests add surfaces with add_surface()."""
    fake_lwsdk.reset()
    yield fake_lwsdk
    fake_lwsdk.reset()


@pytest.fixture
def template_graph():
    """The node graph LightWave saved for CONNECTOR with a Principled BSDF
    wired into Surface.Material - the real file used throughout the node
    investigation, kept as a fixture."""
    path = os.path.join(TESTS, "data", "principled_wired.txt")
    with open(path) as f:
        return f.read()
