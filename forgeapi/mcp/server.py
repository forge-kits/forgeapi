"""forge-kits MCP Server.

Start via:
    forgeapi-mcp

Or register via the CLI:
    forgeapi mcp:install           # local scope
    forgeapi mcp:install --global  # all projects
"""

from mcp.server.mcpserver import MCPServer

from .docs import get_docs
from .examples import get_example
from .generators import generate_controller, generate_schema
from .scanner import scan_project, project_info

mcp = MCPServer(
    "forge-kits",
    instructions="""\
forge-kits CLI and API toolkit for FastAPI.

SESSION START — do all three before writing any code:
1. scan_project('<absolute path>') — read what already exists
2. get_docs('cheatsheet') — quick-reference for controllers, auth, schemas, queries
3. get_docs('workflow') — mandatory rules (wrong commands here break the project)

FETCH DOCS ON DEMAND — call get_docs() as soon as the topic comes up, before answering:
- migrations / db schema changes → get_docs('cli')
- auth guards / login / strategies → get_docs('auth')
- permissions / roles / RBAC → get_docs('permissions')
- policies / ownership checks → get_docs('policies')
- caching → get_docs('cache')
- file upload / storage / S3 → get_docs('storage')
- scheduler / cron jobs → get_docs('scheduler')
- background jobs / queue → get_docs('queue')
- WebSocket / SSE / real-time → get_docs('broadcasting')
- query scopes / filters → get_docs('scopes')
- model observers / hooks → get_docs('observers')
- Tortoise ORM relations / advanced queries → get_docs('tortoise') or get_docs('tortoise_advanced')
- middleware / CORS / rate limit → get_docs('middleware')
- config/ files / settings → get_docs('config')
- controller routing / discovery → get_docs('controllers')
- Pydantic schemas / response shapes → get_docs('schemas')

All available topics: cheatsheet, workflow, core, cli, controllers, broadcasting,
auth, permissions, policies, schemas, middleware, config, models,
cache, storage, scheduler, queue, scopes, observers, support, tortoise, tortoise_advanced.
""",
)

# Register all tools
mcp.tool()(get_docs)
mcp.tool()(get_example)
mcp.tool()(generate_controller)
mcp.tool()(generate_schema)
mcp.tool()(scan_project)
mcp.tool()(project_info)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
