from __future__ import annotations

import re


def _pluralize(s: str) -> str:
    if s.endswith("y") and len(s) >= 2 and s[-2] not in "aeiou":
        return s[:-1] + "ies"
    if s.endswith("s"):
        return s
    return s + "s"


def generate_controller(name: str, routes: list[str]) -> str:
    """Generate a forge-kits Controller class.

    Args:
        name:   Resource name in PascalCase, e.g. "Post", "AdminUser".
                Must start with a letter and contain only letters/digits.
        routes: List of route descriptors in "METHOD /path" format.
                Supported methods: GET, POST, PUT, PATCH, DELETE.
                Examples: ["GET /", "POST /", "GET /{id}", "PATCH /{id}", "DELETE /{id}"]

    Returns:
        Python source code for the controller file.
    """
    if not re.match(r'^[A-Za-z][A-Za-z0-9]*$', name):
        return "Error: name must start with a letter and contain only letters and digits."

    words = re.findall(r'[A-Z][a-z0-9]*', name)

    if len(words) >= 2:
        namespace = words[0].lower()
        resource  = "-".join(w.lower() for w in words[1:])
        prefix    = f"/{namespace}/{_pluralize(resource)}"
        tags      = [f"{namespace}/{_pluralize(resource)}"]
    else:
        slug   = words[0].lower() if words else name.lower()
        prefix = f"/{_pluralize(slug)}"
        tags   = [_pluralize(slug)]

    method_map = {"GET": "get", "POST": "post", "PUT": "put", "PATCH": "patch", "DELETE": "delete"}

    route_defs: list[dict] = []
    for r in routes:
        parts = r.strip().split(None, 1)
        if len(parts) != 2:
            continue
        http_method = parts[0].upper()
        path = parts[1]
        if http_method not in method_map:
            continue

        path_params = re.findall(r'\{(\w+)\}', path)

        if path == "/":
            fn_name = {"GET": "index", "POST": "create"}.get(http_method, http_method.lower())
        else:
            slugs  = [p.strip("{}").replace("-", "_") for p in path.strip("/").split("/") if p]
            param  = slugs[-1] if slugs else "item"
            fn_name = {
                "GET":    f"show_{param}",
                "PUT":    f"update_{param}",
                "PATCH":  f"update_{param}",
                "DELETE": f"destroy_{param}",
            }.get(http_method, f"{http_method.lower()}_{param}")

        route_defs.append({
            "decorator":   method_map[http_method],
            "path":        path,
            "fn_name":     fn_name,
            "http_method": http_method,
            "path_params": path_params,
            "status_code": 201 if http_method == "POST" else (204 if http_method == "DELETE" else None),
        })

    lines = [
        "from fastapi import HTTPException, Request",
        "from forgeapi.controllers import Controller, route",
        "from forgeapi.auth import CurrentUser, OptionalUser",
        "from forgeapi.pagination import Pagination",
        "",
        "",
        f"class {name}Controller(Controller):",
        f'    prefix = "{prefix}"',
        f'    tags   = {tags!r}',
    ]

    if not route_defs:
        lines += [
            "",
            '    @route.get("/")',
            "    async def index(self, pagination: Pagination) -> dict:",
            "        pass",
        ]
    else:
        for rd in route_defs:
            lines.append("")
            sc = f", status_code={rd['status_code']}" if rd["status_code"] else ""
            lines.append(f'    @route.{rd["decorator"]}("{rd["path"]}"{sc})')

            sig = ["self"] + [f"{p}: int" for p in rd["path_params"]]
            if rd["http_method"] in ("POST", "PUT", "PATCH"):
                payload = name + ("Create" if rd["http_method"] == "POST" else "Update") + "Payload"
                sig.append(f"payload: {payload}")
            if rd["http_method"] != "GET":
                sig.append("user: CurrentUser")
            elif rd["path"] == "/" and rd["http_method"] == "GET":
                sig.append("request: Request")

            ret = "" if rd["http_method"] == "DELETE" else " -> dict"
            lines.append(f"    async def {rd['fn_name']}({', '.join(sig)}){ret}:")
            lines.append("        pass")

    return "\n".join(lines) + "\n"


def generate_event(name: str, fields: list[str]) -> str:
    """Generate an Event class and its listener file.

    Args:
        name:   Event name in PascalCase without the "Event" suffix,
                e.g. "UserRegistered", "OrderShipped".
        fields: List of field definitions in "name:type" format,
                e.g. ["user_id:int", "email:str", "plan:str"].
                Supported types: int, str, float, bool, dict, list.

    Returns:
        Python source containing the Event subclass and a companion listener.
    """
    if not re.match(r'^[A-Za-z][A-Za-z0-9]*$', name):
        return "Error: name must start with a letter and contain only letters and digits."

    parsed: list[tuple[str, str]] = []
    for f in fields:
        fname, ftype = (f.split(":", 1) if ":" in f else (f, "str"))
        fname, ftype = fname.strip(), ftype.strip()
        if re.match(r'^\w+$', fname):
            parsed.append((fname, ftype))

    snake = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

    event_lines = [
        f"# app/events/{snake}_event.py",
        "from forgeapi import Event",
        "",
        "",
        f"class {name}Event(Event):",
        "    background = True",
        "    redis      = False",
        "",
    ]

    if parsed:
        init_args = ", ".join(f"{fn}: {ft}" for fn, ft in parsed)
        event_lines.append(f"    def __init__(self, {init_args}) -> None:")
        for fn, _ in parsed:
            event_lines.append(f"        self.{fn} = {fn}")
    else:
        event_lines += ["    def __init__(self) -> None:", "        pass"]

    listener_lines = [
        "",
        "",
        f"# app/listeners/{snake}_listener.py",
        "from forgeapi import listen",
        f"from app.events.{snake}_event import {name}Event",
        "",
        "",
        f"@listen({name}Event)",
        f"async def handle_{snake}(event: {name}Event) -> None:",
        "    pass",
    ]

    dispatch_args = ", ".join(f"{fn}=..." for fn, _ in parsed)
    dispatch_lines = [
        "",
        "",
        f"# await {name}Event({dispatch_args}).dispatch()",
    ]

    return "\n".join(event_lines + listener_lines + dispatch_lines) + "\n"


def generate_schema(name: str, fields: list[str], mode: str = "all") -> str:
    """Generate Pydantic schema classes for forge-kits.

    Args:
        name:   Resource name in PascalCase, e.g. "Post", "UserProfile".
        fields: Field definitions in "name:type" or "name:type=default" format.
                Examples: ["title:str", "body:str", "views:int=0", "tags:list[str]=[]"].
        mode:   "all" | "response" | "create" | "update" | "crud"
                "all"/"crud" → all three classes; others → single class.

    Returns:
        Python source code with the requested schema classes.
    """
    if not re.match(r'^[A-Za-z][A-Za-z0-9]*$', name):
        return "Error: name must start with a letter and contain only letters and digits."

    parsed: list[tuple[str, str, str | None]] = []
    for f in fields:
        default = None
        if "=" in f:
            left, default = f.rsplit("=", 1)
            default = default.strip()
        else:
            left = f
        fname, ftype = (left.split(":", 1) if ":" in left else (left, "str"))
        fname, ftype = fname.strip(), ftype.strip()
        if re.match(r'^\w+$', fname):
            parsed.append((fname, ftype, default))

    mode = mode.lower().strip()
    gen_response = mode in ("all", "crud", "response")
    gen_create   = mode in ("all", "crud", "create")
    gen_update   = mode in ("all", "crud", "update")

    if not any([gen_response, gen_create, gen_update]):
        return f"Error: unknown mode '{mode}'. Use: all, response, create, update, crud."

    lines = ["from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema", ""]

    if gen_response:
        lines += [
            "",
            f"class {name}Response(BaseSchema):",
            "    # Inherits: id, created_at, updated_at — model_config from_attributes=True",
        ]
        lines += (
            [f"    {fn}: {ft}" + (f" = {d}" if d else "") for fn, ft, d in parsed]
            or ["    pass"]
        )

    if gen_create:
        lines += ["", f"class {name}CreatePayload(BaseCreateSchema):"]
        lines += (
            [f"    {fn}: {ft}" + (f" = {d}" if d else "") for fn, ft, d in parsed]
            or ["    pass"]
        )

    if gen_update:
        lines += [
            "",
            f"class {name}UpdatePayload(BaseUpdateSchema):",
            "    # All fields Optional — safe for partial PATCH",
        ]
        lines += (
            [f"    {fn}: {ft} | None = None" for fn, ft, _ in parsed]
            or ["    pass"]
        )

    return "\n".join(lines) + "\n"
