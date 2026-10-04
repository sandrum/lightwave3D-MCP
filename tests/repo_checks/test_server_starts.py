"""
Start server.py the way Claude Desktop does - as a subprocess speaking MCP
over stdio - then initialize a session and list its tools. Nothing here
contacts LightWave (listing tools doesn't), so it runs anywhere.

The unit tests import server.py and call its functions directly; this is
the check that the server process itself starts and answers, under
whichever mcp version is installed (CI runs it for both 1.x and 2.x).
"""
import asyncio
import os
import sys

from conftest import ROOT


async def _list_tools():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable,
                                   args=[os.path.join(ROOT, "server.py")], cwd=ROOT)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            # mcp 2.x renamed serverInfo to server_info.
            server_info = getattr(info, "server_info", None) or info.serverInfo
            tools = (await session.list_tools()).tools
            return server_info.name, {tool.name for tool in tools}


def test_server_starts_and_lists_its_tools():
    name, tools = asyncio.run(asyncio.wait_for(_list_tools(), timeout=60))
    assert name == "lightwave"
    for expected in ("lw_ping", "lw_get_scene_info", "lw_connect_nodes", "lw_set_node_key"):
        assert expected in tools
    assert "lw_set_fog" not in tools  # withdrawn - see PLAN.md
