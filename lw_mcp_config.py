"""
lw_mcp_config.py

Shared settings for every part of LightwaveMCP - server.py (Claude's
side) and the scripts loaded into LightWave (lw_enable_command_port.py,
lw_mcp_ring.py, lw_mcp_render_monitor.py, lw_enable_modeler_command_port.py,
lw_mcp_modeler_query.py) - so both sides agree on ports and on the folder
they exchange reply files through.

Values come from, highest priority first:
  1. real environment variables of the same name,
  2. a `.env` file next to this module (git-ignored - copy
     `.env.example` to start one),
  3. the defaults below, which match the original hard-coded values.

Not a LightWave plug-in itself: it's imported by the ones that are.
Python 2 and 3 compatible, since LightWave's embedded Python is older.
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(_HERE, ".env")

DEFAULTS = {
    "LW_MCP_HOST": "localhost",
    "LW_MCP_LAYOUT_PORT": "9735",
    "LW_MCP_MODELER_PORT": "9736",
    "LW_MCP_EXCHANGE_DIR": "",
}


def _read_env_file(path):
    """Parse KEY=VALUE lines; blank lines and # comments are skipped, one
    pair of surrounding quotes is stripped from a value, and an empty
    value counts as unset (so the default applies)."""
    values = {}
    if not os.path.exists(path):
        return values
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if value:
                values[key] = value
    return values


def load():
    settings = dict(DEFAULTS)
    settings.update(_read_env_file(ENV_PATH))
    for key in DEFAULTS:
        if os.environ.get(key):
            settings[key] = os.environ[key]
    return settings


def _port(settings, key):
    try:
        return int(settings[key])
    except ValueError:
        raise ValueError("%s must be a port number, got %r (check %s)"
                         % (key, settings[key], ENV_PATH))


SETTINGS = load()
HOST = SETTINGS["LW_MCP_HOST"]
LAYOUT_PORT = _port(SETTINGS, "LW_MCP_LAYOUT_PORT")
MODELER_PORT = _port(SETTINGS, "LW_MCP_MODELER_PORT")

_exchange = SETTINGS["LW_MCP_EXCHANGE_DIR"].strip()
EXCHANGE_DIR = (os.path.abspath(os.path.expanduser(os.path.expandvars(_exchange)))
                if _exchange else _HERE)
if not os.path.isdir(EXCHANGE_DIR):
    os.makedirs(EXCHANGE_DIR)


def exchange_path(name):
    """Full path of a reply/status/debug file in the shared exchange folder."""
    return os.path.join(EXCHANGE_DIR, name)
