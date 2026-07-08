"""Block Kit card builders — Comp Planning Copilot."""

import json
import os
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Visual primitives
# ---------------------------------------------------------------------------

def _bar(pct: float, width: int = 16) -> str:
    filled = min(width, round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


def _dot(pct: float) -> str:
    if pct > 90: return "🔴"
    if pct > 70: return "🟡"
    return "🟢"


def _risk_dot(pct_below: float) -> str:
    """Color for equity gap severity."""
    gap = abs(pct_below)
    if gap > 10: return "🔴"
    if gap > 5:  return "🟡"
    return "🟢"


def _risk_label(budget_ok: bool, equity_flagged: bool) -> str:
    if not budget_ok and equity_flagged: return "🔴  HIGH RISK"
    if not budget_ok:                    return "🟡  BUDGET EXCEEDED"
    if equity_flagged:                   return "🟡  EQUITY FLAG"
    return "🟢  CLEAR TO APPROVE"


def _band_position(proposed: float, band: dict) -> str:
    mn, mid, mx = band["min_salary"], band["mid_salary"], band["max_salary"]
    if mx == mn:
        return ""
    raw = (proposed - mn) / (mx - mn) * 100
    clamped = max(0.0, min(100.0, raw))
    w = 20
    pos = round(clamped / 100 * w)
    bar = "─" * pos + "●" + "─" * (w - pos)
    if proposed < mn:   note = "⚠️ below minimum"
    elif proposed > mx: note = "⚠️ above maximum"
    else:               note = f"{clamped:.0f}th percentile"
    return f"`${mn:,.0f}` {bar} `${mx:,.0f}`\n*${proposed:,.0f}* — {note}  ·  mid ${mid:,.0f}"


# ---------------------------------------------------------------------------
# A — App Home dashboard
# ---------------------------------------------------------------------------

def home_view(status: dict, risks: list[dict]) -> dict:
    util   = status.get("utilization_pct", 0)
    alloc  = status.get("total_allocated", 0)
    total  = status.get("total_budget", 0)
    props  = status.get("total_proposals", 0)
    flags  = status.get("equity_flags", 0)
    esc    = status.get("escalated", 0)
    mgrs   = status.get("managers", [])
    now    = datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC")

    blocks: list[dict] = [
        # ── Header ──────────────────────────────────────────────────────────
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📊  Comp Copilot  ·  Merit Cycle 2026-H1"},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Last refreshed {now}"}],
        },
        {"type": "divider"},

        # ── Dashboard CTA ────────────────────────────────────────────────────
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*📈  Full Analytics Dashboard*\nCharts, manager breakdown, equity risks table, and live budget tracking.",
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Open Dashboard ↗"},
                "style": "primary",
                "url": os.getenv("DASHBOARD_URL", "http://localhost:3001"),
                "action_id": "open_dashboard",
            },
        },
        {"type": "divider"},

        # ── Budget bar ───────────────────────────────────────────────────────
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Overall Budget*\n"
                    f"{_dot(util)}  `{_bar(util)}`  *{util:.1f}%*\n"
                    f"*${alloc:,.0f}* allocated  of  ${total:,.0f} total merit pool"
                ),
            },
        },

        # ── KPI grid ─────────────────────────────────────────────────────────
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{props}*\nProposals submitted"},
                {"type": "mrkdwn", "text": f"*{flags}* ⚖️\nEquity flags"},
                {"type": "mrkdwn", "text": f"*{esc}* {'🔺' if esc else '✅'}\nEscalated"},
                {"type": "mrkdwn", "text": f"*{len(mgrs)}*\nManagers active"},
            ],
        },

        # ── Actions ──────────────────────────────────────────────────────────
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🆕  New Proposal"},
                    "style": "primary",
                    "action_id": "open_proposal_modal",
                    "value": "home",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔄  Refresh"},
                    "action_id": "refresh_home",
                    "value": "refresh",
                },
            ],
        },
        {"type": "divider"},
    ]

    # ── Equity risks ─────────────────────────────────────────────────────────
    if risks:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*⚖️  Active Equity Risks*  ·  {len(risks)} employee{'s' if len(risks) != 1 else ''} below peer-median threshold",
            },
        })
        for r in risks[:6]:
            gap   = abs(r["pct_vs_median"])
            dot   = _risk_dot(r["pct_vs_median"])
            delta = r["peer_median"] - r["current_salary"]
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{dot}  *{r['name']}*  ·  {r['role']} {r['level']}  ·  {r['location']}\n"
                        f"    ${r['current_salary']:,.0f} current  →  "
                        f"*{gap:.1f}% below* peer median ${r['peer_median']:,.0f}  "
                        f"_(gap: +${delta:,.0f} needed)_"
                    ),
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Propose raise ↗"},
                    "style": "primary",
                    "action_id": "open_proposal_modal_for_employee",
                    "value": json.dumps({"employee_id": r["id"], "name": r["name"]}),
                },
            })
    else:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "🟢  *No active equity risks* — all employees within 5% of peer median."},
        })

    blocks.append({"type": "divider"})

    # ── Manager tracker ───────────────────────────────────────────────────────
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*💰  Manager Budget Tracker*"},
    })

    for mgr in mgrs:
        mu       = mgr.get("utilization_pct", 0)
        dot      = _dot(mu)
        bar      = _bar(mu, width=10)
        flag_str = f"  ⚖️ {mgr['flags']}" if mgr.get("flags") else ""
        rem      = mgr.get("total_budget", 0) - mgr.get("allocated", 0)
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"{dot}  *{mgr['manager_name']}*\n`{bar}` {mu:.0f}%"},
                {"type": "mrkdwn", "text": f"*{mgr.get('proposals', 0)}* proposals{flag_str}\n${rem:,.0f} remaining"},
            ],
        })

    blocks += [
        {"type": "divider"},
        {
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": "💡  Type `/comp give <name> <pct>%` in any channel  ·  or click *New Proposal* above",
            }],
        },
    ]

    return {"type": "home", "blocks": blocks}


# ---------------------------------------------------------------------------
# B — Proposal modal
# ---------------------------------------------------------------------------

def proposal_modal(private_metadata: str = "", prefill_name: str = "") -> dict:
    name_el: dict = {
        "type": "plain_text_input",
        "action_id": "employee_name",
        "placeholder": {"type": "plain_text", "text": "e.g. Kim Johnson"},
    }
    if prefill_name:
        name_el["initial_value"] = prefill_name

    return {
        "type": "modal",
        "callback_id": "proposal_modal",
        "private_metadata": private_metadata,
        "title": {"type": "plain_text", "text": "New Comp Proposal"},
        "submit": {"type": "plain_text", "text": "Check & Preview"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Both *budget* and *pay equity* are checked automatically before you approve.",
                },
            },
            {"type": "divider"},
            {
                "type": "input",
                "block_id": "employee_block",
                "element": name_el,
                "label": {"type": "plain_text", "text": "👤  Employee name"},
            },
            {
                "type": "input",
                "block_id": "raise_type_block",
                "element": {
                    "type": "radio_buttons",
                    "action_id": "raise_type",
                    "options": [
                        {
                            "text": {"type": "plain_text", "text": "Percentage raise  (enter e.g. 8 for 8%)"},
                            "value": "pct",
                        },
                        {
                            "text": {"type": "plain_text", "text": "Target salary  (enter e.g. 175000)"},
                            "value": "salary",
                        },
                    ],
                    "initial_option": {
                        "text": {"type": "plain_text", "text": "Percentage raise  (enter e.g. 8 for 8%)"},
                        "value": "pct",
                    },
                },
                "label": {"type": "plain_text", "text": "📈  Raise type"},
            },
            {
                "type": "input",
                "block_id": "amount_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "amount",
                    "placeholder": {"type": "plain_text", "text": "e.g.  8   or   175000"},
                },
                "label": {"type": "plain_text", "text": "💵  Amount"},
                "hint": {"type": "plain_text", "text": "Numbers only — no % or $ symbols needed."},
            },
            {
                "type": "input",
                "block_id": "notes_block",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "notes",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Performance notes, context for HR review… (optional)"},
                },
                "label": {"type": "plain_text", "text": "📝  Notes"},
            },
        ],
    }


# ---------------------------------------------------------------------------
# C — Richer equity card  (budget + pay band + equity + actions)
# ---------------------------------------------------------------------------

def equity_card(
    budget: dict,
    equity: dict,
    employee_id: int,
    manager_id: int,
    proposed_salary: float,
    pct: float,
    band: dict | None = None,
) -> list[dict]:
    emp_name      = equity.get("employee_name", "Employee")
    current       = equity.get("current_salary", 0)
    role          = equity.get("role", "")
    level         = equity.get("level", "")
    location      = equity.get("location", "")
    peer_median   = equity.get("peer_median")
    pct_vs_median = equity.get("pct_vs_median", 0)
    flagged       = bool(equity.get("equity_flagged"))
    peer_count    = equity.get("peer_count", 0)
    rec_min       = equity.get("recommended_min")
    rec_max       = equity.get("recommended_max")
    budget_ok     = bool(budget.get("ok", True))
    b_util        = budget.get("utilization_pct", 0)

    risk = _risk_label(budget_ok, flagged)

    blocks: list[dict] = [
        # ── Header ────────────────────────────────────────────────────────────
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Comp Proposal  ·  {emp_name}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Current*\n${current:,.0f}"},
                {"type": "mrkdwn", "text": f"*Proposed*\n${proposed_salary:,.0f}  *(+{pct:.1f}%)*"},
                {"type": "mrkdwn", "text": f"*Role / Level*\n{role} {level}"},
                {"type": "mrkdwn", "text": f"*Location*\n{location}"},
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Assessment:  *{risk}*"}],
        },
        {"type": "divider"},
    ]

    # ── Pay band ─────────────────────────────────────────────────────────────
    if band and band.get("ok"):
        band_str = _band_position(proposed_salary, band)
        if band_str:
            blocks += [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📏  Pay Band  ·  {role} {level}  ·  {location}*\n{band_str}",
                    },
                },
                {"type": "divider"},
            ]

    # ── Budget ───────────────────────────────────────────────────────────────
    b_dot      = _dot(b_util)
    b_status   = "✅  Within limit" if budget_ok else f"🚫  Over budget by *${budget.get('overage', 0):,.0f}*"
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*💰  Budget*  ·  {b_status}\n"
                f"{b_dot}  `{_bar(b_util)}`  {b_util:.1f}%\n"
                f"*${budget.get('pool_remaining', 0):,.0f} remaining*  of  ${budget.get('pool_total', 0):,.0f}"
            ),
        },
    })

    if not budget_ok:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "⚠️  This proposal will be *escalated* to HR for exception approval."}],
        })

    # ── Pay equity ───────────────────────────────────────────────────────────
    if peer_median:
        blocks.append({"type": "divider"})
        direction  = "below" if pct_vs_median < 0 else "above"
        eq_status  = "🚩  FLAGGED — exceeds 5% threshold" if flagged else "✅  Within acceptable range"
        gap_dot    = _risk_dot(pct_vs_median) if flagged else "🟢"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*⚖️  Pay Equity*  ·  {eq_status}\n"
                    f"{gap_dot}  Proposed *${proposed_salary:,.0f}*  vs  peer median *${peer_median:,.0f}*  "
                    f"_(n={peer_count}, same role/level/location)_\n"
                    f"Gap:  *{abs(pct_vs_median):.1f}% {direction} median*"
                ),
            },
        })

        if flagged and rec_min and rec_max:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"🇪🇺  *EU Pay Transparency Directive 2026*\n"
                        f"Salary {abs(pct_vs_median):.1f}% below peer median exceeds the 5% disclosure threshold.\n"
                        f"Recommended range to close gap:  *${rec_min:,.0f} – ${rec_max:,.0f}*"
                    ),
                },
            })

    # ── Action buttons ────────────────────────────────────────────────────────
    approve_val = json.dumps({
        "employee_id": employee_id, "manager_id": manager_id,
        "proposed_salary": proposed_salary,
        "notes": f"Approved as-is at +{pct:.1f}%",
    })

    buttons: list[dict] = []

    if flagged and rec_min:
        mid_rec = (rec_min + (rec_max or rec_min)) / 2
        buttons.append({
            "type": "button",
            "text": {"type": "plain_text", "text": f"⚖️  Adjust to ${mid_rec:,.0f}"},
            "style": "primary",
            "action_id": "adjust_proposal",
            "value": json.dumps({
                "employee_id": employee_id, "manager_id": manager_id,
                "proposed_salary": mid_rec,
                "notes": f"Adjusted to peer-median recommendation ${mid_rec:,.0f}",
            }),
        })

    buttons += [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "✅  Approve as-is"},
            **({"style": "primary"} if not flagged and budget_ok else {}),
            "action_id": "approve_proposal",
            "value": approve_val,
        },
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "✏️  Edit amount"},
            "action_id": "edit_proposal",
            "value": json.dumps({"employee_id": employee_id, "manager_id": manager_id}),
        },
    ]

    blocks += [{"type": "divider"}, {"type": "actions", "elements": buttons}]
    return blocks


# ---------------------------------------------------------------------------
# Confirmation + status cards
# ---------------------------------------------------------------------------

def proposal_submitted_card(result: dict) -> list[dict]:
    status_map = {
        "pending":   ("✅", "Submitted for approval"),
        "escalated": ("🔺", "Escalated — budget exception required"),
        "approved":  ("🎉", "Approved"),
    }
    emoji, label = status_map.get(result.get("status", "pending"), ("📋", "Submitted"))

    blocks: list[dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{emoji}  *Proposal {label}*\n"
                    f"*{result.get('employee_name')}*  ·  "
                    f"${result.get('current_salary', 0):,.0f} → ${result.get('proposed_salary', 0):,.0f} "
                    f"*(+{result.get('increase_pct', 0):.1f}%)*\n"
                    f"Proposal ID:  `#{result.get('proposal_id')}`"
                ),
            },
        },
    ]
    if result.get("equity_flagged"):
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": (
                    f"⚖️  Equity note: {result.get('pct_vs_median', 0):.1f}% vs peer median "
                    f"${result.get('peer_median', 0):,.0f} — HR will review."
                ),
            }],
        })
    return blocks


def status_card(result: dict) -> list[dict]:
    util  = result.get("utilization_pct", 0)
    cycle = result.get("cycle_id", "2026-H1")

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📊  Merit Cycle Pulse  ·  {cycle}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Budget Utilization*\n"
                    f"{_dot(util)}  `{_bar(util)}`  *{util:.1f}%*\n"
                    f"${result.get('total_allocated', 0):,.0f} of ${result.get('total_budget', 0):,.0f} allocated"
                ),
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{result.get('total_proposals', 0)}*\nProposals"},
                {"type": "mrkdwn", "text": f"*{result.get('equity_flags', 0)}* ⚖️\nEquity flags"},
                {"type": "mrkdwn", "text": f"*{result.get('escalated', 0)}* 🔺\nEscalated"},
                {"type": "mrkdwn", "text": f"*{len(result.get('managers', []))}*\nManagers"},
            ],
        },
        {"type": "divider"},
    ]

    for mgr in result.get("managers", []):
        mu       = mgr.get("utilization_pct", 0)
        flag_str = f"  ⚖️ {mgr['flags']}" if mgr.get("flags") else ""
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"{_dot(mu)}  *{mgr['manager_name']}*\n`{_bar(mu, 8)}` {mu:.0f}%"},
                {"type": "mrkdwn", "text": f"*{mgr.get('proposals', 0)}* proposals{flag_str}\n${mgr.get('total_budget', 0) - mgr.get('allocated', 0):,.0f} remaining"},
            ],
        })

    return blocks


def error_card(message: str) -> list[dict]:
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f":x:  {message}"}}]


def disambiguate_card(matches: list[dict], query: str) -> list[dict]:
    blocks: list[dict] = [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*{len(matches)} matches* for _{query}_ — select one:"},
    }]
    for emp in matches[:5]:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{emp['name']}*  ·  {emp['role']} {emp['level']}  ·  "
                    f"{emp['location']}  ·  ${emp['current_salary']:,.0f}"
                ),
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Select"},
                "action_id": "select_employee",
                "value": str(emp["id"]),
            },
        })
    return blocks
