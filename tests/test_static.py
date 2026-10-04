"""
Static checks on the source, for code the other tests can't run because it
needs a live LightWave (anything that calls the SDK).

The main one: every private module-level name a file uses (`_something`) is
defined in that file. An edit once deleted two constants that only
LightWave-calling functions used; the plug-in then failed at runtime inside
Layout, with nothing to catch it beforehand.
"""
import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["server.py", "lw_mcp_ring.py", "lw_mcp_config.py", "lw_mcp_render_monitor.py"]


def parse(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return ast.parse(f.read(), name)


def top_level_names(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
    return names


@pytest.mark.parametrize("name", FILES)
def test_every_private_name_used_is_defined(name):
    tree = parse(name)
    defined = top_level_names(tree)
    used = {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
            and n.id.startswith("_") and not n.id.startswith("__")}
    assert used - defined == set()


@pytest.mark.parametrize("name", FILES + ["lw_enable_command_port.py",
                                          "lw_enable_modeler_command_port.py"])
def test_files_compile(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        compile(f.read(), name, "exec")


def test_no_personal_paths_in_tracked_text():
    # The repo is public; README/PLAN/etc. once carried absolute paths
    # from one machine.
    import subprocess
    try:
        files = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    needle = "\\" + "users" + "\\"   # built up so this file doesn't match itself
    offenders = []
    for rel in files:
        if not rel.endswith((".py", ".md", ".txt", ".lws", ".json", ".example", ".yml")):
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
            for number, line in enumerate(f, 1):
                lowered = line.lower()
                if needle in lowered and "<you>" not in lowered:
                    offenders.append("%s:%d" % (rel, number))
    assert offenders == []
