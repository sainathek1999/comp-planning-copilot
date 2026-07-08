"""Thin async wrapper around the FastMCP HTTP client."""

import json
import os
from typing import Any

from fastmcp import Client

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")


async def call_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Call an MCP tool and return the parsed result dict."""
    async with Client(MCP_SERVER_URL) as client:
        raw = await client.call_tool(tool_name, arguments)

    # FastMCP 3.x returns CallToolResult; .data is already parsed.
    if hasattr(raw, "data") and raw.data is not None:
        return raw.data
    # Fallback: parse from text content
    content = getattr(raw, "content", raw)
    if isinstance(content, list) and content:
        text = getattr(content[0], "text", None)
        if text is not None:
            return json.loads(text)
    return raw


async def find_employee(name_query: str) -> list[dict]:
    return await call_tool("find_employee", {"name_query": name_query})


async def check_budget(manager_id: int, employee_id: int, pct: float) -> dict:
    return await call_tool("check_budget", {
        "manager_id": manager_id,
        "employee_id": employee_id,
        "proposed_increase_pct": pct,
    })


async def check_equity(employee_id: int, proposed_salary: float) -> dict:
    return await call_tool("check_equity", {
        "employee_id": employee_id,
        "proposed_salary": proposed_salary,
    })


async def submit_proposal(
    employee_id: int,
    manager_id: int,
    proposed_salary: float,
    notes: str = "",
) -> dict:
    return await call_tool("submit_proposal", {
        "employee_id": employee_id,
        "manager_id": manager_id,
        "proposed_salary": proposed_salary,
        "notes": notes,
    })


async def get_pay_band(role: str, level: str, location: str) -> dict:
    return await call_tool("get_pay_band", {"role": role, "level": level, "location": location})


async def list_equity_risks(limit: int = 10) -> list[dict]:
    return await call_tool("list_equity_risks", {"limit": limit})


async def cycle_status(manager_id: int | None = None) -> dict:
    args: dict[str, Any] = {}
    if manager_id is not None:
        args["manager_id"] = manager_id
    return await call_tool("cycle_status", args)
