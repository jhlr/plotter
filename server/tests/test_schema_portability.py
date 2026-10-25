"""Guard: the tools' input schemas stay in the subset every provider's function calling accepts
(Anthropic, OpenAI, Gemini, local models through LiteLLM/Ollama): flat JSON, no refs, unions, consts or tuples."""
import asyncio
import re
from typing import Any

from penarm import server

# Keywords that at least one major provider rejects (or silently mangles) in function declarations.
FORBIDDEN = {"$ref", "$defs", "definitions", "oneOf", "allOf", "anyOf", "not", "const", "prefixItems", "discriminator",
             "if", "then", "else", "patternProperties", "dependentSchemas", "unevaluatedProperties"}


def walk(node: Any, path: str = "") -> list[str]:
    problems: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in FORBIDDEN:
                problems.append(f"{path}/{key}")
            if key == "type" and (value == "null" or isinstance(value, list)):
                problems.append(f"{path}/type={value!r}")
            problems += walk(value, f"{path}/{key}")
        if "properties" in node and isinstance(node["properties"], dict):
            for name, prop in node["properties"].items():
                if isinstance(prop, dict) and "type" not in prop and "enum" not in prop:
                    problems.append(f"{path}/properties/{name} has no type")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            problems += walk(item, f"{path}[{i}]")
    return problems


def tools() -> list[Any]:
    return asyncio.run(server.mcp.list_tools())


def test_every_tool_schema_is_portable() -> None:
    offenders = {t.name: walk(t.input_schema) for t in tools()}
    assert {k: v for k, v in offenders.items() if v} == {}


def test_tool_names_and_descriptions_are_provider_neutral() -> None:
    for t in tools():
        assert re.fullmatch(r"[a-z][a-z0-9_]{0,63}", t.name), t.name
        assert t.input_schema.get("type") == "object", t.name
        assert t.description and len(t.description) > 40, t.name
        assert "claude" not in (t.description or "").lower(), t.name  # no vendor-specific wording


def test_optional_arguments_use_defaults_not_nulls() -> None:
    for t in tools():
        for name, prop in t.input_schema.get("properties", {}).items():
            assert prop.get("type") in ("string", "number", "integer", "boolean", "array", "object"), (t.name, name)


def test_server_carries_its_own_usage_guide() -> None:
    assert "canvas_info" in server.GUIDE and "dry_run" in server.GUIDE and "claude" not in server.GUIDE.lower()
