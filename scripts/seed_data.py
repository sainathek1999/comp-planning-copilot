"""
Seed 58 synthetic employees + 17 demo proposals for the 2026-H1 merit cycle.

Demo hooks:
  Budget guardrail  → Dana Whitfield: $38k pool, $35.5k used (93.4%), 2 escalated proposals
  Equity flags      → Kim/Maria (SE L4 SF), Lily (PM L3 NY), Nina (DS L4 Austin)
  Rich proposals    → 8 approved · 5 pending · 2 escalated · 2 equity-flagged pending
  Overall utilization after approved raises: ~73.6% ($230.5k of $313k)
"""

import os
import sys
import random
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from mcp_server.db.models import Base, Employee, PayBand, BudgetPool, Rating, Proposal

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///comp_data.db")
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)

random.seed(42)

# ---------------------------------------------------------------------------
# Pay bands: (role, level, location) → (min, mid, max)
# ---------------------------------------------------------------------------

SF_BANDS: dict[tuple[str, str], tuple[float, float, float]] = {
    ("Software Engineer", "L3"): (120_000, 155_000, 190_000),
    ("Software Engineer", "L4"): (150_000, 190_000, 230_000),
    ("Software Engineer", "L5"): (185_000, 235_000, 285_000),
    ("Software Engineer", "L6"): (230_000, 290_000, 350_000),
    ("Product Manager",   "L3"): (110_000, 140_000, 170_000),
    ("Product Manager",   "L4"): (140_000, 175_000, 210_000),
    ("Product Manager",   "L5"): (170_000, 215_000, 260_000),
    ("Data Scientist",    "L3"): (115_000, 148_000, 181_000),
    ("Data Scientist",    "L4"): (145_000, 185_000, 225_000),
    ("Data Scientist",    "L5"): (180_000, 228_000, 276_000),
    ("Product Designer",  "L3"): (100_000, 128_000, 156_000),
    ("Product Designer",  "L4"): (125_000, 158_000, 191_000),
    ("Product Designer",  "L5"): (155_000, 196_000, 237_000),
    ("HR Business Partner", "L4"): (115_000, 148_000, 181_000),
    ("HR Business Partner", "L5"): (145_000, 188_000, 231_000),
}

LOC_MULT: dict[str, float] = {
    "San Francisco": 1.00,
    "New York":      0.95,
    "Austin":        0.80,
    "Remote":        0.87,
}

LOCATIONS = list(LOC_MULT.keys())


def band(role: str, level: str, loc: str) -> tuple[float, float, float]:
    mn, mid, mx = SF_BANDS[(role, level)]
    m = LOC_MULT[loc]
    return round(mn * m), round(mid * m), round(mx * m)


# ---------------------------------------------------------------------------
# Employee definitions
# ---------------------------------------------------------------------------

MANAGER_SLOTS = [
    ("alex",   "Alex Chen",      "alex.chen@example.com",      "Software Engineer",    "L6", "San Francisco", 310_000, "Engineering"),
    ("jordan", "Jordan Lee",     "jordan.lee@example.com",     "Product Manager",      "L5", "New York",      210_000, "Product"),
    ("morgan", "Morgan Davis",   "morgan.davis@example.com",   "Data Scientist",       "L5", "Austin",        185_000, "Data"),
    ("casey",  "Casey Brown",    "casey.brown@example.com",    "Product Designer",     "L5", "Remote",        172_000, "Design"),
    ("dana",   "Dana Whitfield", "dana.whitfield@example.com", "HR Business Partner",  "L5", "San Francisco", 188_000, "People"),
    ("sam",    "Sam Taylor",     "sam.taylor@example.com",     "Software Engineer",    "L6", "New York",      295_000, "Engineering"),
]

IC_ROWS = [
    # --- Alex Chen's SE team (SF + Austin) ---
    ("Kim Johnson",       "kim.johnson@example.com",       "Software Engineer", "L4", "San Francisco", 152_000, "alex", "Engineering"),
    ("Maria Smith",       "maria.smith@example.com",       "Software Engineer", "L4", "San Francisco", 158_000, "alex", "Engineering"),
    ("David Park",        "david.park@example.com",        "Software Engineer", "L4", "San Francisco", 186_000, "alex", "Engineering"),
    ("Emma Wilson",       "emma.wilson@example.com",       "Software Engineer", "L3", "San Francisco", 148_000, "alex", "Engineering"),
    ("Liam Martinez",     "liam.martinez@example.com",     "Software Engineer", "L3", "San Francisco", 152_000, "alex", "Engineering"),
    ("Sofia Anderson",    "sofia.anderson@example.com",    "Software Engineer", "L3", "San Francisco", 145_000, "alex", "Engineering"),
    ("Noah Thomas",       "noah.thomas@example.com",       "Software Engineer", "L3", "San Francisco", 155_000, "alex", "Engineering"),
    ("Isabella Jackson",  "isabella.jackson@example.com",  "Software Engineer", "L4", "Austin",        145_000, "alex", "Engineering"),
    ("James White",       "james.white@example.com",       "Software Engineer", "L4", "Austin",        148_000, "alex", "Engineering"),
    # --- Jordan Lee's PM team (NY + Austin) ---
    ("Lily Lopez",        "lily.lopez@example.com",        "Product Manager",   "L3", "New York",      116_000, "jordan", "Product"),
    ("Ava Harris",        "ava.harris@example.com",        "Product Manager",   "L3", "New York",      130_000, "jordan", "Product"),
    ("Oliver Martin",     "oliver.martin@example.com",     "Product Manager",   "L3", "New York",      132_000, "jordan", "Product"),
    ("Mia Thompson",      "mia.thompson@example.com",      "Product Manager",   "L4", "New York",      158_000, "jordan", "Product"),
    ("Lucas Garcia",      "lucas.garcia@example.com",      "Product Manager",   "L4", "New York",      162_000, "jordan", "Product"),
    ("Harper Martinez",   "harper.martinez@example.com",   "Product Manager",   "L4", "New York",      166_000, "jordan", "Product"),
    ("Ethan Robinson",    "ethan.robinson@example.com",    "Product Manager",   "L3", "Austin",        105_000, "jordan", "Product"),
    ("Evelyn Clark",      "evelyn.clark@example.com",      "Product Manager",   "L3", "Austin",        108_000, "jordan", "Product"),
    ("Aiden Rodriguez",   "aiden.rodriguez@example.com",   "Product Manager",   "L3", "Austin",        112_000, "jordan", "Product"),
    # --- Morgan Davis's DS team (Austin + Remote) ---
    ("Nina Garcia",       "nina.garcia@example.com",       "Data Scientist",    "L4", "Austin",        133_000, "morgan", "Data"),
    ("Benjamin Lewis",    "benjamin.lewis@example.com",    "Data Scientist",    "L4", "Austin",        146_000, "morgan", "Data"),
    ("Amelia Lee",        "amelia.lee@example.com",        "Data Scientist",    "L4", "Austin",        149_000, "morgan", "Data"),
    ("Henry Walker",      "henry.walker@example.com",      "Data Scientist",    "L3", "Austin",        112_000, "morgan", "Data"),
    ("Abigail Hall",      "abigail.hall@example.com",      "Data Scientist",    "L3", "Austin",        115_000, "morgan", "Data"),
    ("Sebastian Allen",   "sebastian.allen@example.com",   "Data Scientist",    "L3", "Austin",        118_000, "morgan", "Data"),
    ("Emily Young",       "emily.young@example.com",       "Data Scientist",    "L3", "Remote",        103_000, "morgan", "Data"),
    ("Daniel Hernandez",  "daniel.hernandez@example.com",  "Data Scientist",    "L3", "Remote",        106_000, "morgan", "Data"),
    ("Ella King",         "ella.king@example.com",         "Data Scientist",    "L3", "Remote",        108_000, "morgan", "Data"),
    # --- Casey Brown's Design team (Remote) ---
    ("Matthew Wright",    "matthew.wright@example.com",    "Product Designer",  "L3", "Remote",        100_000, "casey", "Design"),
    ("Elizabeth Scott",   "elizabeth.scott@example.com",   "Product Designer",  "L3", "Remote",        103_000, "casey", "Design"),
    ("Joseph Green",      "joseph.green@example.com",      "Product Designer",  "L3", "Remote",        106_000, "casey", "Design"),
    ("Grace Adams",       "grace.adams@example.com",       "Product Designer",  "L4", "Remote",        131_000, "casey", "Design"),
    ("Christopher Baker", "christopher.baker@example.com", "Product Designer",  "L4", "Remote",        134_000, "casey", "Design"),
    ("Chloe Gonzalez",    "chloe.gonzalez@example.com",    "Product Designer",  "L4", "Remote",        138_000, "casey", "Design"),
    ("Ryan Nelson",       "ryan.nelson@example.com",       "Product Designer",  "L5", "Remote",        165_000, "casey", "Design"),
    ("Victoria Carter",   "victoria.carter@example.com",   "Product Designer",  "L5", "Remote",        170_000, "casey", "Design"),
    # --- Dana Whitfield's HR team (SF + NY) — TIGHT BUDGET ---
    ("Andrew Mitchell",   "andrew.mitchell@example.com",   "HR Business Partner", "L4", "San Francisco", 142_000, "dana", "People"),
    ("Zoe Perez",         "zoe.perez@example.com",         "HR Business Partner", "L4", "San Francisco", 146_000, "dana", "People"),
    ("Joshua Roberts",    "joshua.roberts@example.com",    "HR Business Partner", "L4", "San Francisco", 148_000, "dana", "People"),
    ("Madison Turner",    "madison.turner@example.com",    "HR Business Partner", "L4", "New York",      132_000, "dana", "People"),
    ("Jayden Phillips",   "jayden.phillips@example.com",   "HR Business Partner", "L4", "New York",      135_000, "dana", "People"),
    ("Samantha Campbell", "samantha.campbell@example.com", "HR Business Partner", "L4", "New York",      138_000, "dana", "People"),
    ("Nathan Parker",     "nathan.parker@example.com",     "HR Business Partner", "L5", "San Francisco", 178_000, "dana", "People"),
    ("Brooklyn Evans",    "brooklyn.evans@example.com",    "HR Business Partner", "L5", "San Francisco", 182_000, "dana", "People"),
    # --- Sam Taylor's SE team (NY) ---
    ("David Edwards",     "david.edwards@example.com",     "Software Engineer", "L3", "New York",      138_000, "sam", "Engineering"),
    ("Alexis Collins",    "alexis.collins@example.com",    "Software Engineer", "L3", "New York",      141_000, "sam", "Engineering"),
    ("Evelyn Stewart",    "evelyn.stewart@example.com",    "Software Engineer", "L3", "New York",      144_000, "sam", "Engineering"),
    ("Kevin Sanchez",     "kevin.sanchez@example.com",     "Software Engineer", "L3", "New York",      147_000, "sam", "Engineering"),
    ("Rachel Morris",     "rachel.morris@example.com",     "Software Engineer", "L4", "New York",      168_000, "sam", "Engineering"),
    ("Tyler Rogers",      "tyler.rogers@example.com",      "Software Engineer", "L4", "New York",      172_000, "sam", "Engineering"),
    ("Lauren Reed",       "lauren.reed@example.com",       "Software Engineer", "L4", "New York",      175_000, "sam", "Engineering"),
    ("Brandon Cook",      "brandon.cook@example.com",      "Software Engineer", "L4", "New York",      178_000, "sam", "Engineering"),
    ("Jessica Morgan",    "jessica.morgan@example.com",    "Software Engineer", "L5", "New York",      218_000, "sam", "Engineering"),
]

RATINGS_MAP = {
    "kim.johnson@example.com":    "Exceeds",
    "maria.smith@example.com":    "Exceeds",
    "lily.lopez@example.com":     "Exceeds",
    "nina.garcia@example.com":    "Exceeds",
    "david.park@example.com":     "Exceeds",
    "jessica.morgan@example.com": "Exceeds",
    "rachel.morris@example.com":  "Exceeds",
    "mia.thompson@example.com":   "Exceeds",
}

# Budget pools: total, allocated (approved raises only — pending/escalated not counted)
BUDGET_POOLS = {
    "alex":   (65_000,  50_000),   # $28k base + $14k (David) + $8k (Emma) approved
    "jordan": (50_000,  36_000),   # $20k base + $8k (Mia) + $8k (Ava) approved
    "morgan": (48_000,  29_000),   # $18k base + $7k (Benjamin) + $4k (Henry) approved
    "casey":  (42_000,  23_000),   # $15k base + $8k (Grace) approved
    "dana":   (38_000,  35_500),   # TIGHT — 2 escalated proposals, no new budget consumed
    "sam":    (70_000,  57_000),   # $30k base + $12k (Rachel) + $9k (Tyler) + $6k (David E) approved
}

# ---------------------------------------------------------------------------
# Demo proposals — (employee_email, mgr_slot, current, proposed, status,
#                   equity_flagged, notes, created_at_str)
# ---------------------------------------------------------------------------
def _dt(date_str: str) -> datetime:
    return datetime.fromisoformat(date_str).replace(tzinfo=None)

PROPOSAL_SEEDS = [
    # ── Alex Chen's team ──────────────────────────────────────────────────────
    (
        "david.park@example.com", "alex",
        186_000, 200_000, "approved", 0,
        "Top performer, led Auth platform rewrite. Strong retention risk.",
        _dt("2026-06-18T10:22:00"),
    ),
    (
        "emma.wilson@example.com", "alex",
        148_000, 156_000, "approved", 0,
        "Solid cycle, promoted to tech lead on mobile squad.",
        _dt("2026-07-02T14:05:00"),
    ),
    (
        "liam.martinez@example.com", "alex",
        152_000, 163_000, "pending", 0,
        "Delivered infra migration 2 weeks early. Requesting 7% to match band midpoint.",
        _dt("2026-07-07T09:30:00"),
    ),
    # ── Jordan Lee's team ─────────────────────────────────────────────────────
    (
        "mia.thompson@example.com", "jordan",
        158_000, 166_000, "approved", 0,
        "Led Q1 roadmap planning, strong cross-functional feedback.",
        _dt("2026-06-20T11:00:00"),
    ),
    (
        "ava.harris@example.com", "jordan",
        130_000, 138_000, "approved", 0,
        "Consistent Meets+ performer, market data shows risk of attrition.",
        _dt("2026-06-29T16:45:00"),
    ),
    (
        "lily.lopez@example.com", "jordan",
        116_000, 127_000, "pending", 1,
        "Exceeds rating 2 cycles running. Salary 11.5% below peer median — EU Pay Transparency risk.",
        _dt("2026-06-30T13:20:00"),
    ),
    # ── Morgan Davis's team ───────────────────────────────────────────────────
    (
        "benjamin.lewis@example.com", "morgan",
        146_000, 153_000, "approved", 0,
        "Shipped recommendation engine, 18% uplift in click-through.",
        _dt("2026-06-24T10:10:00"),
    ),
    (
        "henry.walker@example.com", "morgan",
        112_000, 116_000, "approved", 0,
        "Meets expectations, annual merit adjustment.",
        _dt("2026-06-28T15:30:00"),
    ),
    (
        "nina.garcia@example.com", "morgan",
        133_000, 148_000, "pending", 1,
        "Critical ML infra contributor. 9.8% below peer median — retention risk + equity flag.",
        _dt("2026-07-04T09:00:00"),
    ),
    # ── Casey Brown's team ────────────────────────────────────────────────────
    (
        "grace.adams@example.com", "casey",
        131_000, 139_000, "approved", 0,
        "Design system overhaul shipped — reduced component debt by 40%.",
        _dt("2026-06-25T12:00:00"),
    ),
    (
        "matthew.wright@example.com", "casey",
        100_000, 105_000, "pending", 0,
        "First full cycle, strong onboarding and delivery. Merit bump.",
        _dt("2026-07-06T10:45:00"),
    ),
    # ── Dana Whitfield's team — TIGHT BUDGET → ESCALATED ─────────────────────
    (
        "andrew.mitchell@example.com", "dana",
        142_000, 153_360, "escalated", 0,
        "8% raise — market correction. Budget pool exhausted, escalated for HR exception.",
        _dt("2026-06-27T14:00:00"),
    ),
    (
        "zoe.perez@example.com", "dana",
        146_000, 153_300, "escalated", 0,
        "5% standard merit. Pool at 93% utilization — escalated for exception approval.",
        _dt("2026-07-03T11:30:00"),
    ),
    # ── Sam Taylor's team ─────────────────────────────────────────────────────
    (
        "rachel.morris@example.com", "sam",
        168_000, 180_000, "approved", 0,
        "Exceeds performer, led NY office migration project. Strong retention priority.",
        _dt("2026-06-22T09:15:00"),
    ),
    (
        "tyler.rogers@example.com", "sam",
        172_000, 181_000, "approved", 0,
        "Consistent delivery, L4 band midpoint adjustment.",
        _dt("2026-07-01T13:00:00"),
    ),
    (
        "david.edwards@example.com", "sam",
        138_000, 144_000, "approved", 0,
        "Annual merit cycle, Meets expectations.",
        _dt("2026-07-05T10:00:00"),
    ),
    (
        "jessica.morgan@example.com", "sam",
        218_000, 231_000, "pending", 0,
        "L5 top performer, staff eng track. Competing offer from competitor at $240k.",
        _dt("2026-06-16T08:30:00"),
    ),
]


def main() -> None:
    with Session(engine) as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()

        # Pay bands
        bands = []
        for (role, level), (mn_sf, mid_sf, mx_sf) in SF_BANDS.items():
            for loc, mult in LOC_MULT.items():
                bands.append(PayBand(
                    role=role, level=level, location=loc,
                    min_salary=round(mn_sf * mult),
                    mid_salary=round(mid_sf * mult),
                    max_salary=round(mx_sf * mult),
                ))
        session.add_all(bands)
        session.commit()

        # Managers
        slot_to_id: dict[str, int] = {}
        for slot, name, email, role, level, loc, salary, dept in MANAGER_SLOTS:
            emp = Employee(name=name, email=email, role=role, level=level,
                           location=loc, current_salary=salary, department=dept)
            session.add(emp)
            session.flush()
            slot_to_id[slot] = emp.id

        # ICs
        email_to_id: dict[str, int] = {}
        for name, email, role, level, loc, salary, mgr_slot, dept in IC_ROWS:
            emp = Employee(
                name=name, email=email, role=role, level=level,
                location=loc, current_salary=salary,
                manager_id=slot_to_id[mgr_slot], department=dept,
            )
            session.add(emp)
            session.flush()
            email_to_id[email] = emp.id

        # Ratings
        all_ids = list(email_to_id.values())
        random.shuffle(all_ids)
        rating_choices = ["Exceeds"] * 12 + ["Meets"] * 32 + ["Below"] * 8
        assigned: dict[int, str] = {}
        for eid, rating in zip(all_ids, rating_choices):
            assigned[eid] = rating
        for email, override_rating in RATINGS_MAP.items():
            if email in email_to_id:
                assigned[email_to_id[email]] = override_rating
        session.add_all([
            Rating(employee_id=eid, cycle_id="2026-H1", rating=r)
            for eid, r in assigned.items()
        ])

        # Budget pools
        pools = []
        for slot, (total, allocated) in BUDGET_POOLS.items():
            pools.append(BudgetPool(
                manager_id=slot_to_id[slot],
                cycle_id="2026-H1",
                total_budget=total,
                allocated_budget=allocated,
            ))
        session.add_all(pools)
        session.commit()

        # Demo proposals
        proposals = []
        for emp_email, mgr_slot, current, proposed, status, eq_flag, notes, created_at in PROPOSAL_SEEDS:
            emp_id = email_to_id.get(emp_email)
            mgr_id = slot_to_id.get(mgr_slot)
            if not emp_id or not mgr_id:
                print(f"  SKIP: {emp_email} not found")
                continue
            inc_pct = round((proposed - current) / current * 100, 2)
            proposals.append(Proposal(
                employee_id=emp_id,
                manager_id=mgr_id,
                cycle_id="2026-H1",
                current_salary=current,
                proposed_salary=proposed,
                increase_pct=inc_pct,
                status=status,
                equity_flagged=eq_flag,
                notes=notes,
                created_at=created_at,
            ))
        session.add_all(proposals)
        session.commit()

    total_emp = len(MANAGER_SLOTS) + len(IC_ROWS)
    approved  = sum(1 for p in PROPOSAL_SEEDS if p[4] == "approved")
    pending   = sum(1 for p in PROPOSAL_SEEDS if p[4] == "pending")
    escalated = sum(1 for p in PROPOSAL_SEEDS if p[4] == "escalated")
    eq_flags  = sum(1 for p in PROPOSAL_SEEDS if p[5] == 1)

    print(f"Seeded {total_emp} employees · {len(bands)} pay bands · {len(pools)} budget pools")
    print(f"Proposals: {len(PROPOSAL_SEEDS)} total — {approved} approved · {pending} pending · {escalated} escalated · {eq_flags} equity-flagged")
    print()
    print("Dashboard: ~73.6% overall budget utilization ($230.5k of $313k)")
    print()
    print("Demo hooks:")
    print("  Budget guardrail → Dana's team at 93.4% — any new raise escalates")
    print("  Pending equity flags → Lily Lopez (PM L3 NY, 9.5% below), Nina Garcia (DS L4 Austin, 11.3% below)")
    print("  Escalated → Andrew Mitchell & Zoe Perez (Dana's pool exhausted)")
    print("  Competing offer → Jessica Morgan SE L5 NY ($231k ask vs $240k competitor)")


if __name__ == "__main__":
    main()
