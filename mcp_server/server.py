import os
from fastmcp import FastMCP
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from .db.models import Base, Employee, PayBand, BudgetPool, Proposal

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///comp_data.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)

mcp = FastMCP(
    "Comp Planning Copilot",
    instructions=(
        "HR compensation agent. Use check_budget before approving raises. "
        "Use check_equity to detect pay gaps. submit_proposal runs both checks automatically."
    ),
)

CYCLE = "2026-H1"


def _peer_median(session: Session, employee: Employee) -> tuple[float | None, int]:
    peers = session.scalars(
        select(Employee).where(
            Employee.role == employee.role,
            Employee.level == employee.level,
            Employee.location == employee.location,
            Employee.id != employee.id,
        )
    ).all()
    if not peers:
        return None, 0
    salaries = sorted(p.current_salary for p in peers)
    n = len(salaries)
    median = salaries[n // 2] if n % 2 == 1 else (salaries[n // 2 - 1] + salaries[n // 2]) / 2
    return median, n


@mcp.tool()
def find_employee(name_query: str) -> list[dict]:
    """Search employees by partial name (case-insensitive). Returns id, name, role, level, location, salary."""
    with Session(engine) as session:
        q = name_query.lower()
        employees = session.scalars(select(Employee)).all()
        matches = [e for e in employees if q in e.name.lower()]
        return [
            {
                "id": e.id,
                "name": e.name,
                "role": e.role,
                "level": e.level,
                "location": e.location,
                "current_salary": e.current_salary,
                "manager_id": e.manager_id,
            }
            for e in matches
        ]


@mcp.tool()
def check_budget(manager_id: int, employee_id: int, proposed_increase_pct: float) -> dict:
    """Check if a proposed raise % fits within the manager's merit pool. Returns ok, remaining, overage."""
    with Session(engine) as session:
        employee = session.get(Employee, employee_id)
        if not employee:
            return {"ok": False, "error": f"Employee {employee_id} not found"}

        pool = session.scalar(
            select(BudgetPool).where(
                BudgetPool.manager_id == manager_id,
                BudgetPool.cycle_id == CYCLE,
            )
        )
        if not pool:
            return {"ok": False, "error": f"No budget pool found for manager {manager_id} in {CYCLE}"}

        raise_amount = employee.current_salary * (proposed_increase_pct / 100)
        remaining = pool.total_budget - pool.allocated_budget
        over_budget = raise_amount > remaining

        return {
            "ok": not over_budget,
            "employee_name": employee.name,
            "current_salary": employee.current_salary,
            "raise_amount": round(raise_amount, 2),
            "proposed_increase_pct": proposed_increase_pct,
            "pool_total": pool.total_budget,
            "pool_allocated": round(pool.allocated_budget, 2),
            "pool_remaining": round(remaining, 2),
            "utilization_pct": round((pool.allocated_budget / pool.total_budget) * 100, 1),
            "over_budget": over_budget,
            "overage": round(raise_amount - remaining, 2) if over_budget else 0.0,
        }


@mcp.tool()
def check_equity(employee_id: int, proposed_salary: float) -> dict:
    """Check proposed salary vs peer median (same role/level/location). Flags if >5% below median."""
    with Session(engine) as session:
        employee = session.get(Employee, employee_id)
        if not employee:
            return {"ok": False, "error": f"Employee {employee_id} not found"}

        peer_median, peer_count = _peer_median(session, employee)

        if peer_median is None:
            return {
                "ok": True,
                "warning": "No peers found for comparison",
                "employee_name": employee.name,
                "proposed_salary": proposed_salary,
                "peer_count": 0,
            }

        pct_vs_median = ((proposed_salary - peer_median) / peer_median) * 100
        equity_flagged = pct_vs_median < -5.0
        # Recommend landing within ±3% of median
        recommended_min = round(peer_median * 0.97, 0)
        recommended_max = round(peer_median * 1.03, 0)

        return {
            "ok": not equity_flagged,
            "employee_name": employee.name,
            "role": employee.role,
            "level": employee.level,
            "location": employee.location,
            "current_salary": employee.current_salary,
            "proposed_salary": proposed_salary,
            "peer_median": round(peer_median, 2),
            "peer_count": peer_count,
            "pct_vs_median": round(pct_vs_median, 1),
            "equity_flagged": equity_flagged,
            "recommended_min": recommended_min,
            "recommended_max": recommended_max,
            "recommendation": (
                f"Raise to ${recommended_min:,.0f}–${recommended_max:,.0f} "
                f"to stay within 3% of peer median"
            ) if equity_flagged else None,
        }


@mcp.tool()
def get_pay_band(role: str, level: str, location: str) -> dict:
    """Return pay band min/mid/max for a role+level+location."""
    with Session(engine) as session:
        band = session.scalar(
            select(PayBand).where(
                PayBand.role == role,
                PayBand.level == level,
                PayBand.location == location,
            )
        )
        if not band:
            return {"ok": False, "error": f"No pay band for {role}/{level}/{location}"}
        return {
            "ok": True,
            "role": role,
            "level": level,
            "location": location,
            "min_salary": band.min_salary,
            "mid_salary": band.mid_salary,
            "max_salary": band.max_salary,
        }


@mcp.tool()
def submit_proposal(
    employee_id: int,
    manager_id: int,
    proposed_salary: float,
    notes: str = "",
) -> dict:
    """Submit a comp proposal. Runs budget + equity checks automatically and stores result."""
    with Session(engine) as session:
        employee = session.get(Employee, employee_id)
        if not employee:
            return {"ok": False, "error": f"Employee {employee_id} not found"}

        increase_pct = ((proposed_salary - employee.current_salary) / employee.current_salary) * 100

        pool = session.scalar(
            select(BudgetPool).where(
                BudgetPool.manager_id == manager_id,
                BudgetPool.cycle_id == CYCLE,
            )
        )
        raise_amount = proposed_salary - employee.current_salary
        budget_ok = bool(pool and (pool.allocated_budget + raise_amount) <= pool.total_budget)

        peer_median, peer_count = _peer_median(session, employee)
        pct_vs_median = ((proposed_salary - peer_median) / peer_median) * 100 if peer_median else 0.0
        equity_flagged = peer_median is not None and pct_vs_median < -5.0

        status = "escalated" if not budget_ok else "pending"

        proposal = Proposal(
            employee_id=employee_id,
            manager_id=manager_id,
            cycle_id=CYCLE,
            current_salary=employee.current_salary,
            proposed_salary=proposed_salary,
            increase_pct=round(increase_pct, 2),
            status=status,
            equity_flagged=1 if equity_flagged else 0,
            notes=notes,
        )
        session.add(proposal)

        if pool and budget_ok:
            pool.allocated_budget += raise_amount

        session.commit()
        session.refresh(proposal)

        return {
            "ok": True,
            "proposal_id": proposal.id,
            "employee_name": employee.name,
            "current_salary": employee.current_salary,
            "proposed_salary": proposed_salary,
            "increase_pct": round(increase_pct, 2),
            "status": status,
            "budget_ok": budget_ok,
            "equity_flagged": equity_flagged,
            "peer_median": round(peer_median, 2) if peer_median else None,
            "peer_count": peer_count,
            "pct_vs_median": round(pct_vs_median, 1) if peer_median else None,
        }


@mcp.tool()
def cycle_status(manager_id: int | None = None) -> dict:
    """Get merit cycle pulse: allocation %, equity flags, per-manager breakdown."""
    with Session(engine) as session:
        pool_q = select(BudgetPool).where(BudgetPool.cycle_id == CYCLE)
        if manager_id:
            pool_q = pool_q.where(BudgetPool.manager_id == manager_id)
        pools = session.scalars(pool_q).all()

        proposal_q = select(Proposal).where(Proposal.cycle_id == CYCLE)
        if manager_id:
            proposal_q = proposal_q.where(Proposal.manager_id == manager_id)
        proposals = session.scalars(proposal_q).all()

        total_budget = sum(p.total_budget for p in pools)
        total_allocated = sum(p.allocated_budget for p in pools)
        equity_flags = sum(1 for p in proposals if p.equity_flagged)
        escalated = sum(1 for p in proposals if p.status == "escalated")

        manager_breakdown = []
        for pool in pools:
            mgr = session.get(Employee, pool.manager_id)
            mgr_proposals = [p for p in proposals if p.manager_id == pool.manager_id]
            manager_breakdown.append({
                "manager_id": pool.manager_id,
                "manager_name": mgr.name if mgr else "Unknown",
                "total_budget": pool.total_budget,
                "allocated": round(pool.allocated_budget, 2),
                "utilization_pct": round((pool.allocated_budget / pool.total_budget) * 100, 1) if pool.total_budget else 0,
                "proposals": len(mgr_proposals),
                "flags": sum(1 for p in mgr_proposals if p.equity_flagged),
            })

        return {
            "ok": True,
            "cycle_id": CYCLE,
            "total_budget": total_budget,
            "total_allocated": round(total_allocated, 2),
            "utilization_pct": round((total_allocated / total_budget) * 100, 1) if total_budget else 0,
            "total_proposals": len(proposals),
            "equity_flags": equity_flags,
            "escalated": escalated,
            "managers": manager_breakdown,
        }


@mcp.tool()
def list_equity_risks(limit: int = 10) -> list[dict]:
    """Return employees currently >5% below peer median, sorted by largest gap first."""
    with Session(engine) as session:
        employees = session.scalars(select(Employee)).all()
        risks = []
        for emp in employees:
            peer_median, peer_count = _peer_median(session, emp)
            if not peer_median or peer_count == 0:
                continue
            pct = ((emp.current_salary - peer_median) / peer_median) * 100
            if pct < -5.0:
                risks.append({
                    "id": emp.id,
                    "name": emp.name,
                    "role": emp.role,
                    "level": emp.level,
                    "location": emp.location,
                    "current_salary": emp.current_salary,
                    "peer_median": round(peer_median, 2),
                    "pct_vs_median": round(pct, 1),
                    "manager_id": emp.manager_id,
                })
        risks.sort(key=lambda x: x["pct_vs_median"])
        return risks[:limit]


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8080"))
    mcp.run(transport="http", host="0.0.0.0", port=port)
