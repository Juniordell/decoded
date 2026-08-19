"""Convert Pydantic models to Anthropic tool schemas for Batch API use.

Instructor does this automatically for real-time calls. Batch API requires
raw requests, so we build the tool definitions ourselves.
"""

from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel


def pydantic_to_tool(model: Type[BaseModel], tool_name: str | None = None) -> dict[str, Any]:
    """
    Build an Anthropic tool definition from a Pydantic model.

    The model's JSON schema becomes the tool's input_schema. The LLM is then
    forced to call this tool, which means its output conforms to the schema.
    """
    schema = model.model_json_schema()

    # Anthropic requires "object" type at the top level with properties
    name = tool_name or f"emit_{model.__name__.lower()}"

    return {
        "name": name,
        "description": (
            f"Emit the structured {model.__name__} result. "
            "You must call this tool with the complete result."
        ),
        "input_schema": {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
            # Pydantic puts nested models in $defs — Anthropic accepts them inline
            **({"$defs": schema["$defs"]} if "$defs" in schema else {}),
        },
    }


def parse_tool_response(
    content_blocks: list[dict],
    model: Type[BaseModel],
    tool_name: str,
) -> BaseModel:
    """
    Extract the tool_use block from an Anthropic response and validate it
    against the Pydantic model.
    """
    for block in content_blocks:
        block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if block_type != "tool_use":
            continue

        block_name = block.get("name") if isinstance(block, dict) else getattr(block, "name", None)
        if block_name != tool_name:
            continue

        block_input = block.get("input") if isinstance(block, dict) else getattr(block, "input", None)
        return model.model_validate(block_input)

    raise ValueError(f"No tool_use block named '{tool_name}' found in response")