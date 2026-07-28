"""forge-kits MCP Server.

Start via:
    forgeapi-mcp

Or register via the CLI:
    forgeapi mcp:install           # local scope
    forgeapi mcp:install --global  # all projects
"""

from mcp.server.fastmcp import FastMCP

from .docs import get_docs
from .examples import get_example
from .generators import generate_controller, generate_event, generate_schema
from .scanner import scan_project, project_info

mcp = FastMCP(
    "forge-kits",
    instructions="""\
forge-kits CLI and API toolkit for FastAPI.

RULES — must follow for every forge-kits project:
- Dev server: `forgeapi runserver --reload` — NEVER uvicorn directly
- Migrations: `forgeapi db:*` — NEVER aerich, NEVER pip install aerich
- Code generation: `forgeapi make:*` — prefer CLI over writing files manually
- Config lives in config/<section>.py files — there is NO forgeapi.toml

SESSION START — always do this first:
1. Call scan_project('<absolute path to user project>') — detects root automatically
   by walking up until it finds a config/ directory. Pass the project folder,
   NOT the forge-kits package directory.
2. Call get_docs('cheatsheet') — covers 80% of tasks.

For advanced topics call get_docs with: workflow, core, controllers, events,
auth, permissions, policies, schemas, middleware, cli, config, models,
cache, storage, scheduler, queue, scopes, observers, support, tortoise, tortoise_advanced.
""",
)

# Register all tools
mcp.tool()(get_docs)
mcp.tool()(get_example)
mcp.tool()(generate_controller)
mcp.tool()(generate_event)
mcp.tool()(generate_schema)
mcp.tool()(scan_project)
mcp.tool()(project_info)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
