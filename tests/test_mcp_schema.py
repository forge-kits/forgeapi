"""MCP side of the schema rework: generate_schema tool and the project scanner."""
import pytest

from forgeapi.mcp.generators import generate_controller, generate_schema
from forgeapi.mcp.scanner import _scan_schemas


def _exec(src: str) -> dict:
    ns: dict = {}
    exec(compile(src, "schemas.py", "exec"), ns)
    return ns


def test_generate_schema_all_is_valid_python_with_derived_update():
    ns = _exec(generate_schema("Post", ["title:str", "views:int=0"]))
    assert ns["PostCreate"](title="t").views == 0
    assert ns["PostUpdate"]().model_dump(exclude_unset=True) == {}
    assert {"PostCreate", "PostUpdate", "PostResponse"} <= set(ns)
    assert "Payload" not in generate_schema("Post", ["title:str"])


@pytest.mark.parametrize("mode,present,absent", [
    ("response", {"PostResponse"}, {"PostCreate", "PostUpdate"}),
    ("create", {"PostCreate"}, {"PostUpdate", "PostResponse"}),
    ("update", {"PostCreate", "PostUpdate"}, {"PostResponse"}),   # Update is derived from Create
])
def test_generate_schema_modes(mode, present, absent):
    ns = _exec(generate_schema("Post", ["title:str"], mode))
    assert present <= set(ns) and not (absent & set(ns))


def test_generate_controller_uses_new_schema_names():
    src = generate_controller("Post", ["POST /", "PATCH /{id}"])
    assert "payload: PostCreate" in src and "payload: PostUpdate" in src
    assert "Payload" not in src


def test_scanner_lists_partial_schema_assignments(tmp_path):
    f = tmp_path / "post.py"
    f.write_text(
        "from forgeapi import BaseSchema, Schema\n"
        "class PostCreate(Schema):\n    title: str\n"
        'PostUpdate = PostCreate.partial("PostUpdate")\n'
        "class PostResponse(BaseSchema):\n    title: str\n"
    )
    out = "\n".join(_scan_schemas([f], tmp_path))
    assert "PostCreate(Schema)" in out
    assert "PostUpdate = PostCreate.partial()" in out
    assert "PostResponse(BaseSchema)" in out
