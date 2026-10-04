"""
Shared test setup.

These tests run without LightWave. They cover the logic that never talks to
it - node-graph text rewriting, .env loading, the server tools' input checks
and the command sequences they send - so a change that breaks those is caught
before anyone restarts Layout. What LightWave itself does with a command still
needs checking live (see PLAN.md); these tests don't replace that.

Two stand-ins make that possible:

- a fake `lwsdk` module, installed before lw_mcp_ring.py is imported, with
  just enough for its module-level code (the master-plugin class and its
  registration) to load;
- `fake_layout`, which replaces server.py's connection to Layout with a
  recorder, so a test can check exactly which commands a tool sends - or that
  it sends none.

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


def _install_fake_lwsdk():
    if "lwsdk" in sys.modules:
        return
    fake = types.ModuleType("lwsdk")

    class IMaster(object):
        def __init__(self, *args, **kwargs):
            pass

    fake.IMaster = IMaster
    fake.MasterFactory = lambda name, cls: (name, cls)
    fake.SRVTAG_USERNAME = 1
    fake.LANGID_USENGLISH = 2
    fake.LWMAST_LAYOUT = 0
    sys.modules["lwsdk"] = fake


_install_fake_lwsdk()


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
def template_graph():
    """The node graph LightWave saved for CONNECTOR with a Principled BSDF
    wired into Surface.Material - the real file used throughout the node
    investigation, kept as a fixture."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "principled_wired.txt")
    with open(path) as f:
        return f.read()
