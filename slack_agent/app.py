"""
Comp Planning Copilot — Slack Bolt app (async, socket mode).

Slash command: /comp give <name> <pct>%
               /comp give <name> $<salary>
               /comp status
               /comp check <name>

App mention: same syntax as slash command.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = AsyncApp(token=os.environ["SLACK_BOT_TOKEN"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GIVE_PCT_RE = re.compile(r"give\s+(.+?)\s+(\d+(?:\.\d+)?)%", re.IGNORECASE)
_GIVE_SAL_RE = re.compile(r"give\s+(.+?)\s+\$(\d[\d,]*)", re.IGNORECASE)
_CHECK_RE    = re.compile(r"check\s+(.+)", re.IGNORECASE)

# Lazy import to avoid circular at module load
def _mcp():
    from . import mcp_client
    return mcp_client

def _blocks():
    from . import blocks
    return blocks


async def _resolve_employee(name_query: str) -> tuple[dict | None, list[dict] | None]:
    """Return (employee, None) or (None, disambiguation_blocks)."""
    bk = _blocks()
    matches = await _mcp().find_employee(name_query)
    if not matches:
        return None, bk.error_card(f"No employee found matching *{name_query}*.")
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 5:
        return None, bk.error_card(
            f"Too many matches for *{name_query}* ({len(matches)}). Be more specific."
        )
    return None, bk.disambiguate_card(matches, name_query)


async def _handle_give_pct(
    say: Any,
    body: dict,
    name: str,
    pct: float,
) -> None:
    bk = _blocks()
    mc = _mcp()

    emp, disambig = await _resolve_employee(name)
    if disambig:
        # Store pending action in private metadata via an ephemeral message
        await say(blocks=disambig, text=f"Multiple matches for {name}")
        return

    proposed_salary = emp["current_salary"] * (1 + pct / 100)
    manager_id = emp.get("manager_id")

    if not manager_id:
        await say(
            blocks=bk.error_card(f"{emp['name']} has no manager on record."),
            text="No manager found",
        )
        return

    budget_res, equity_res, band_res = await asyncio.gather(
        mc.check_budget(manager_id, emp["id"], pct),
        mc.check_equity(emp["id"], proposed_salary),
        mc.get_pay_band(emp["role"], emp["level"], emp["location"]),
    )

    blocks_out = bk.equity_card(
        budget=budget_res,
        equity=equity_res,
        band=band_res if band_res.get("ok") else None,
        employee_id=emp["id"],
        manager_id=manager_id,
        proposed_salary=proposed_salary,
        pct=pct,
    )
    await say(blocks=blocks_out, text=f"Comp proposal for {emp['name']}")


async def _handle_give_salary(
    say: Any,
    name: str,
    target_salary: float,
) -> None:
    bk = _blocks()
    mc = _mcp()

    emp, disambig = await _resolve_employee(name)
    if disambig:
        await say(blocks=disambig, text=f"Multiple matches for {name}")
        return

    pct = ((target_salary - emp["current_salary"]) / emp["current_salary"]) * 100
    manager_id = emp.get("manager_id")

    if not manager_id:
        await say(blocks=bk.error_card(f"{emp['name']} has no manager on record."), text="No manager")
        return

    budget_res, equity_res, band_res = await asyncio.gather(
        mc.check_budget(manager_id, emp["id"], pct),
        mc.check_equity(emp["id"], target_salary),
        mc.get_pay_band(emp["role"], emp["level"], emp["location"]),
    )

    blocks_out = bk.equity_card(
        budget=budget_res,
        equity=equity_res,
        band=band_res if band_res.get("ok") else None,
        employee_id=emp["id"],
        manager_id=manager_id,
        proposed_salary=target_salary,
        pct=pct,
    )
    await say(blocks=blocks_out, text=f"Comp proposal for {emp['name']}")


async def _handle_status(say: Any, manager_id: int | None = None) -> None:
    bk = _blocks()
    result = await _mcp().cycle_status(manager_id)
    await say(blocks=bk.status_card(result), text="Merit cycle status")


async def _dispatch(text: str, say: Any, body: dict) -> None:
    """Parse and dispatch a comp command from either /comp or @mention."""
    bk = _blocks()
    text = text.strip()

    if m := _GIVE_PCT_RE.search(text):
        name, pct_str = m.group(1).strip(), float(m.group(2))
        await _handle_give_pct(say, body, name, pct_str)

    elif m := _GIVE_SAL_RE.search(text):
        name = m.group(1).strip()
        salary = float(m.group(2).replace(",", ""))
        await _handle_give_salary(say, name, salary)

    elif re.search(r"\bstatus\b", text, re.IGNORECASE):
        await _handle_status(say)

    elif m := _CHECK_RE.search(text):
        name = m.group(1).strip()
        emp, disambig = await _resolve_employee(name)
        if disambig:
            await say(blocks=disambig, text=f"Matches for {name}")
        else:
            assert emp
            equity = await _mcp().check_equity(emp["id"], emp["current_salary"])
            msg = (
                f"*{emp['name']}*  ·  {emp['role']} {emp['level']}  ·  {emp['location']}\n"
                f"Current salary: *${emp['current_salary']:,.0f}*\n"
            )
            if equity.get("peer_median"):
                pv = equity["pct_vs_median"]
                direction = "below" if pv < 0 else "above"
                msg += (
                    f"Peer median: ${equity['peer_median']:,.0f}  →  "
                    f"*{abs(pv):.1f}% {direction}*"
                    + ("  ⚖️ *Equity flag*" if equity.get("equity_flagged") else "")
                )
            await say(text=msg)
    else:
        help_text = (
            "Usage:\n"
            "`/comp give <name> <pct>%`  — propose a raise\n"
            "`/comp give <name> $<salary>` — propose a target salary\n"
            "`/comp status` — merit cycle pulse\n"
            "`/comp check <name>` — see current vs peer median"
        )
        await say(text=help_text)


# ---------------------------------------------------------------------------
# Slash command
# ---------------------------------------------------------------------------

@app.command("/comp")
async def handle_comp_command(ack, body, say):
    await ack()
    text = body.get("text", "")
    await _dispatch(text, say, body)


# ---------------------------------------------------------------------------
# App mention (@CompBot give ...)
# ---------------------------------------------------------------------------

@app.event("app_mention")
async def handle_mention(event, say, body):
    text = re.sub(r"<@[A-Z0-9]+>", "", event.get("text", "")).strip()
    await _dispatch(text, say, body)


# ---------------------------------------------------------------------------
# Actions — Approve / Adjust / Edit buttons
# ---------------------------------------------------------------------------

@app.action("approve_proposal")
async def handle_approve(ack, body, say, client):
    await ack()
    payload = json.loads(body["actions"][0]["value"])
    bk = _blocks()

    result = await _mcp().submit_proposal(
        employee_id=payload["employee_id"],
        manager_id=payload["manager_id"],
        proposed_salary=payload["proposed_salary"],
        notes=payload.get("notes", "Approved via Slack"),
    )

    channel = body["container"].get("channel_id")
    ts = body["container"].get("message_ts")

    blocks_out = bk.proposal_submitted_card(result)
    if channel and ts:
        await client.chat_update(channel=channel, ts=ts, blocks=blocks_out, text="Proposal submitted")
    else:
        await say(blocks=blocks_out, text="Proposal submitted")

    # Notify HR channel if escalated or equity-flagged
    hr_channel = os.getenv("HR_ALERTS_CHANNEL")
    if hr_channel and (result.get("status") == "escalated" or result.get("equity_flagged")):
        flag_type = "budget escalation" if result.get("status") == "escalated" else "equity flag"
        try:
            await client.chat_postMessage(
                channel=hr_channel,
                text=(
                    f":bell: *Comp proposal needs review* — {flag_type}\n"
                    f"Employee: *{result.get('employee_name')}*  ·  "
                    f"Proposal #{result.get('proposal_id')}  ·  "
                    f"${result.get('current_salary', 0):,.0f} → ${result.get('proposed_salary', 0):,.0f}"
                ),
            )
        except Exception:
            log.warning("HR_ALERTS_CHANNEL not found — skipping alert")


@app.action("adjust_proposal")
async def handle_adjust(ack, body, say, client):
    await ack()
    payload = json.loads(body["actions"][0]["value"])
    bk = _blocks()

    result = await _mcp().submit_proposal(
        employee_id=payload["employee_id"],
        manager_id=payload["manager_id"],
        proposed_salary=payload["proposed_salary"],
        notes=payload.get("notes", "Adjusted to peer-median recommendation"),
    )

    channel = body["container"].get("channel_id")
    ts = body["container"].get("message_ts")
    blocks_out = bk.proposal_submitted_card(result)

    if channel and ts:
        await client.chat_update(channel=channel, ts=ts, blocks=blocks_out, text="Proposal submitted")
    else:
        await say(blocks=blocks_out, text="Proposal submitted")

    hr_channel = os.getenv("HR_ALERTS_CHANNEL")
    if hr_channel and (result.get("status") == "escalated" or result.get("equity_flagged")):
        try:
            await client.chat_postMessage(
                channel=hr_channel,
                text=(
                    f":bell: *Equity-adjusted proposal* — {result.get('employee_name')}  "
                    f"·  Proposal #{result.get('proposal_id')}"
                ),
            )
        except Exception:
            log.warning("HR_ALERTS_CHANNEL not found — skipping alert")


@app.action("edit_proposal")
async def handle_edit(ack, body, say):
    await ack()
    await say(text="To edit, re-run: `/comp give <name> <new_amount>%` or `/comp give <name> $<salary>`")


@app.action("select_employee")
async def handle_select_employee(ack, body, say):
    """Handle employee disambiguation button — prompt user to re-run with ID."""
    await ack()
    emp_id = body["actions"][0]["value"]
    await say(text=f"Got it — employee ID `{emp_id}`. Re-run your raise command to proceed.")


# ---------------------------------------------------------------------------
# A — App Home
# ---------------------------------------------------------------------------

async def _publish_home(client: Any, user_id: str) -> None:
    mc = _mcp()
    bk = _blocks()
    status, risks = await asyncio.gather(
        mc.cycle_status(),
        mc.list_equity_risks(),
    )
    view = bk.home_view(status, risks)
    result = await client.views_publish(user_id=user_id, view=view)
    log.info("views_publish ok=%s user=%s", result.get("ok"), user_id)


@app.event("app_home_opened")
async def handle_home_opened(event, client):
    await _publish_home(client, event["user"])


@app.action("refresh_home")
async def handle_refresh_home(ack, body, client):
    await ack()
    await _publish_home(client, body["user"]["id"])


# ---------------------------------------------------------------------------
# B — Proposal modal
# ---------------------------------------------------------------------------

@app.action("open_proposal_modal")
async def handle_open_modal(ack, body, client):
    await ack()
    channel_id = body.get("channel", {}).get("id") or body["user"]["id"]
    bk = _blocks()
    await client.views_open(
        trigger_id=body["trigger_id"],
        view=bk.proposal_modal(private_metadata=channel_id),
    )


@app.action("open_proposal_modal_for_employee")
async def handle_open_modal_for_employee(ack, body, client):
    await ack()
    payload = json.loads(body["actions"][0]["value"])
    channel_id = body.get("channel", {}).get("id") or body["user"]["id"]
    bk = _blocks()
    await client.views_open(
        trigger_id=body["trigger_id"],
        view=bk.proposal_modal(
            private_metadata=channel_id,
            prefill_name=payload.get("name", ""),
        ),
    )


@app.view("proposal_modal")
async def handle_modal_submit(ack, body, client, view):
    values = view["state"]["values"]
    channel_id = view.get("private_metadata") or body["user"]["id"]

    emp_name = values["employee_block"]["employee_name"]["value"]
    raise_type = values["raise_type_block"]["raise_type"]["selected_option"]["value"]
    amount_str = values["amount_block"]["amount"]["value"].strip().replace(",", "").replace("$", "").replace("%", "")
    notes = (values.get("notes_block", {}).get("notes", {}).get("value") or "").strip()

    try:
        amount = float(amount_str)
    except ValueError:
        await ack(response_action="errors", errors={"amount_block": "Must be a number — e.g. 8 for 8%, or 175000 for target salary"})
        return

    await ack()

    mc = _mcp()
    bk = _blocks()

    matches = await mc.find_employee(emp_name)
    if not matches:
        await client.chat_postMessage(channel=channel_id, text=f":x: No employee found matching *{emp_name}*.")
        return
    if len(matches) > 5:
        await client.chat_postMessage(channel=channel_id, text=f":x: Too many matches for *{emp_name}* ({len(matches)}). Be more specific.")
        return
    if len(matches) > 1:
        await client.chat_postMessage(channel=channel_id, blocks=bk.disambiguate_card(matches, emp_name), text="Multiple matches")
        return

    emp = matches[0]
    if raise_type == "pct":
        pct = amount
        proposed_salary = emp["current_salary"] * (1 + pct / 100)
    else:
        proposed_salary = amount
        pct = ((proposed_salary - emp["current_salary"]) / emp["current_salary"]) * 100

    manager_id = emp.get("manager_id")
    if not manager_id:
        await client.chat_postMessage(channel=channel_id, text=f":x: {emp['name']} has no manager on record.")
        return

    budget_res, equity_res, band_res = await asyncio.gather(
        mc.check_budget(manager_id, emp["id"], pct),
        mc.check_equity(emp["id"], proposed_salary),
        mc.get_pay_band(emp["role"], emp["level"], emp["location"]),
    )

    blocks_out = bk.equity_card(
        budget=budget_res,
        equity=equity_res,
        band=band_res if band_res.get("ok") else None,
        employee_id=emp["id"],
        manager_id=manager_id,
        proposed_salary=proposed_salary,
        pct=pct,
    )
    await client.chat_postMessage(channel=channel_id, blocks=blocks_out, text=f"Comp proposal for {emp['name']}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
