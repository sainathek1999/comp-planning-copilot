import os
import sys
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_server.db.models import Employee, BudgetPool, Proposal

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///comp_data.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "index.html")

app = FastAPI(title="Comp Copilot Dashboard")

CYCLE = "2026-H1"


def _peer_median(emp_list: list, emp) -> tuple[float | None, int]:
    peers = [e for e in emp_list
             if e.role == emp.role and e.level == emp.level
             and e.location == emp.location and e.id != emp.id]
    if not peers:
        return None, 0
    s = sorted(p.current_salary for p in peers)
    n = len(s)
    return (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2), len(peers)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open(TEMPLATE_PATH, "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/data")
def get_data():
    with Session(engine) as session:
        pools     = session.scalars(select(BudgetPool).where(BudgetPool.cycle_id == CYCLE)).all()
        proposals = session.scalars(select(Proposal).where(Proposal.cycle_id == CYCLE)).all()
        employees = list(session.scalars(select(Employee)).all())

        # Manager breakdown
        managers = []
        for pool in pools:
            mgr = session.get(Employee, pool.manager_id)
            mgr_props = [p for p in proposals if p.manager_id == pool.manager_id]
            util = round(pool.allocated_budget / pool.total_budget * 100, 1) if pool.total_budget else 0
            managers.append({
                "name":       mgr.name if mgr else "Unknown",
                "total":      pool.total_budget,
                "allocated":  round(pool.allocated_budget, 2),
                "remaining":  round(pool.total_budget - pool.allocated_budget, 2),
                "utilization": util,
                "proposals":  len(mgr_props),
                "flags":      sum(1 for p in mgr_props if p.equity_flagged),
            })
        managers.sort(key=lambda x: -x["utilization"])

        # Equity risks
        risks = []
        for emp in employees:
            median, peer_count = _peer_median(employees, emp)
            if not median:
                continue
            pct = (emp.current_salary - median) / median * 100
            if pct < -5.0:
                risks.append({
                    "name":       emp.name,
                    "role":       emp.role,
                    "level":      emp.level,
                    "location":   emp.location,
                    "current":    emp.current_salary,
                    "median":     round(median),
                    "gap_pct":    round(pct, 1),
                    "gap_dollar": round(median - emp.current_salary),
                })
        risks.sort(key=lambda x: x["gap_pct"])

        # Recent proposals
        recent = []
        for p in sorted(proposals, key=lambda x: x.created_at or datetime.min, reverse=True)[:8]:
            emp = session.get(Employee, p.employee_id)
            recent.append({
                "employee":      emp.name if emp else "Unknown",
                "increase_pct":  p.increase_pct,
                "current":       p.current_salary,
                "proposed":      p.proposed_salary,
                "status":        p.status,
                "equity_flagged": bool(p.equity_flagged),
            })

        total_budget   = sum(p.total_budget for p in pools)
        total_allocated = sum(p.allocated_budget for p in pools)

        return {
            "cycle_id":        CYCLE,
            "total_budget":    total_budget,
            "total_allocated": round(total_allocated, 2),
            "utilization_pct": round(total_allocated / total_budget * 100, 1) if total_budget else 0,
            "total_proposals": len(proposals),
            "equity_flags":    len(risks),
            "escalated":       sum(1 for p in proposals if p.status == "escalated"),
            "managers":        managers,
            "equity_risks":    risks,
            "recent_proposals": recent,
            "updated_at":      datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC"),
        }


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "3000"))
    uvicorn.run("dashboard.app:app", host="0.0.0.0", port=port, reload=False)
