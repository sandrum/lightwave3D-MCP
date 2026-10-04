"""
A stand-in for LightWave's `lwsdk` module, covering exactly the SDK calls the
plug-in's node tools make (lw_mcp_ring.py's _rewire_nodes, _add_node,
_remove_node, _move_node, _get_node_values, _set_node_input) - plus the few
names its module-level code needs to load.

It is deliberately simple and does not try to imitate LightWave: a surface's
node editor just holds the graph as ASCII text. `save` writes that text and
`load` replaces it, so a tool's whole flow - check names, save, rewrite the
text, load, save again and report - runs for real against it. Node names and
types are read from the text; each node type's sockets come from the small
tables below. Animation channels are whatever a test puts in
`Surface.envelopes`.

Use reset() to start each test from a clean scene, and add_surface() to put a
graph in it.
"""
import re

# --- module-level names lw_mcp_ring.py needs at import --------------------


class IMaster(object):
    def __init__(self, *args, **kwargs):
        pass


def MasterFactory(name, cls):
    return (name, cls)


SRVTAG_USERNAME = 1
LANGID_USENGLISH = 2
LWMAST_LAYOUT = 0

LWIO_ASCII = 0
# LightWave's real tag numbers (confirmed live: VALUE 0, TIME 1, SHAPE 2).
LWKEY_VALUE, LWKEY_TIME, LWKEY_SHAPE = 0, 1, 2
_KEY_FIELD = {LWKEY_TIME: 0, LWKEY_VALUE: 1, LWKEY_SHAPE: 2}

# --- sockets per node type ------------------------------------------------
# The root "Surface" node lists an unnamed entry at index 0, as the real one
# does (see PLAN.md, Node Editor writing step 2).

INPUTS = {
    "Surface": [None, "Material", "Normal", "Bump", "Displacement", "Clip"],
    "Input": [],
    "Standard": ["Color", "Diffuse", "Bump"],
    "Principled BSDF": ["Color", "Roughness", "Metallic", "Normal", "Bump"],
}
OUTPUTS = {
    "Surface": [],
    "Input": ["Item ID"],
    "Standard": ["Material"],
    "Principled BSDF": ["Material"],
}

# --- scene state ----------------------------------------------------------


class Surface(object):
    def __init__(self, name, text):
        self.name = name
        self.text = text
        self.envelopes = {}      # {node_name: {channel_name: [(time, value, shape), ...]}}
        # keys are kept sorted by time; a key's ID is its index
        self.loads = 0           # how many times a graph was loaded into it


_surfaces = {}


def reset():
    _surfaces.clear()


def add_surface(name, text):
    surface = Surface(name, text)
    _surfaces[name] = surface
    return surface


def _nodes(surface):
    """[(name, type)] in file order, read from the graph text."""
    nodes, server = [], None
    for line in surface.text.splitlines():
        m = re.match(r'^  Server "([^"]*)"$', line)
        if m:
            server = m.group(1)
        m = re.match(r'^    Name "([^"]*)"$', line)
        if m and server is not None:
            nodes.append((m.group(1), server))
            server = None
    return nodes


class _Node(object):
    def __init__(self, surface, name, server):
        self.surface, self.name, self.server = surface, name, server


class _Socket(object):
    def __init__(self, node, index, name):
        self.node, self.index, self.name = node, index, name


# --- SDK classes ----------------------------------------------------------


class LWSurfaceFuncs(object):
    def byName(self, name, obj):
        return [name] if name in _surfaces else []

    def getNodeEditor(self, surf):
        return _surfaces[surf]

    def chanGrp(self, surf):
        return ("top", surf)


class LWNodeEditorFuncs(object):
    def numberOfNodes(self, editor):
        return len(_nodes(editor))

    def nodeByIndex(self, editor, index):
        name, server = _nodes(editor)[index]
        return _Node(editor, name, server)

    def getRootNodeID(self, editor):
        for name, server in _nodes(editor):
            if server == "Surface":
                return _Node(editor, name, server)
        return None

    def save(self, editor, state):
        state.buffer = editor.text

    def load(self, editor, state):
        editor.text = state.buffer
        editor.loads += 1


class LWNodeFuncs(object):
    def nodeName(self, node):
        return node.name

    def serverUserName(self, node):
        return node.server


class LWNodeInputFuncs(object):
    def numInputs(self, node):
        return len(INPUTS.get(node.server, []))

    def byIndex(self, node, index):
        return _Socket(node, index, INPUTS[node.server][index])

    def name(self, socket):
        return socket.name


class LWNodeOutputFuncs(object):
    def first(self, node):
        names = OUTPUTS.get(node.server, [])
        return _Socket(node, 0, names[0]) if names else None

    def next(self, socket):
        names = OUTPUTS.get(socket.node.server, [])
        i = socket.index + 1
        return _Socket(socket.node, i, names[i]) if i < len(names) else None

    def name(self, socket):
        return socket.name


class _FileState(object):
    def __init__(self, path):
        self.path = path
        self.buffer = None


class LWFileIOFuncs(object):
    def openSave(self, path, mode):
        return _FileState(path)

    def closeSave(self, state):
        with open(state.path, "w") as f:
            f.write(state.buffer)

    def openLoad(self, path, mode):
        state = _FileState(path)
        with open(path) as f:
            state.buffer = f.read()
        return state

    def closeLoad(self, state):
        pass


class LWChannelInfo(object):
    """Groups: ("top", surf) -> ("nodes", surf) -> ("node", surf, node_name);
    channels: ("chan", surf, node_name, channel_name)."""

    def nextGroup(self, parent, previous):
        kind, surf = parent[0], parent[1]
        if kind == "top":
            children = [("nodes", surf)]
        elif kind == "nodes":
            children = [("node", surf, name) for name in sorted(_surfaces[surf].envelopes)]
        else:
            children = []
        index = 0 if previous is None else children.index(previous) + 1
        return children[index] if index < len(children) else None

    def groupName(self, group):
        return group[2] if group[0] == "node" else group[0]

    def nextChannel(self, group, previous):
        surf, node = group[1], group[2]
        names = sorted(_surfaces[surf].envelopes.get(node, {}))
        index = 0 if previous is None else names.index(previous[3]) + 1
        return ("chan", surf, node, names[index]) if index < len(names) else None

    def channelName(self, chan):
        return chan[3]

    def channelEnvelope(self, chan):
        return _surfaces[chan[1]].envelopes[chan[2]][chan[3]]


class LWEnvelopeFuncs(object):
    def nextKey(self, env, previous):
        index = 0 if previous is None else previous + 1
        return index if index < len(env) else None

    def keyGet(self, env, key, tag):
        return 1, env[key][_KEY_FIELD[tag]]

    def findKey(self, env, time):
        for index, key in enumerate(env):
            if abs(key[0] - time) < 1e-6:
                return index
        return None

    def keySet(self, env, key, tag, value):
        entry = list(env[key])
        entry[_KEY_FIELD[tag]] = value
        env[key] = tuple(entry)
        env.sort(key=lambda k: k[0])
        return 1

    def createKey(self, env, time, value):
        env.append((time, value, 0))
        env.sort(key=lambda k: k[0])
        return self.findKey(env, time)

    def destroyKey(self, env, key):
        del env[key]


class LWSceneInfo(object):
    framesPerSecond = 30.0
