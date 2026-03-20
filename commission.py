"""
Commission calculation engine.

Commission rules:
  - Transportation rep  → commission_rate % of CustomerTotal (revenue)
  - Procurement rep     → commission_rate % of Margin

Rates are resolved in priority order:
  1. Team-specific override (stored in RATE_OVERRIDES)
  2. Global default from config
"""

from typing import Optional
from config import DEFAULT_TRANSPORT_RATE, DEFAULT_PROCUREMENT_RATE
from models import EmployeeCommission, TeamCommission, CommissionSummary
from database import query

# In-memory rate overrides: {team_id: {"transport": float, "procurement": float}}
RATE_OVERRIDES: dict[int, dict] = {}

TRANSPORT_TYPES   = {"SALE", "TFM"}
PROCUREMENT_TYPES = {"PROC"}


def get_rates(team_id: Optional[int]) -> tuple[float, float]:
    """Return (transport_rate, procurement_rate) for a team."""
    if team_id and team_id in RATE_OVERRIDES:
        o = RATE_OVERRIDES[team_id]
        return o.get("transport", DEFAULT_TRANSPORT_RATE), o.get("procurement", DEFAULT_PROCUREMENT_RATE)
    return DEFAULT_TRANSPORT_RATE, DEFAULT_PROCUREMENT_RATE


def _date_filter(year: int, month: Optional[int]) -> tuple[str, tuple]:
    if month:
        return "YEAR(s.CreatedDateUtc) = ? AND MONTH(s.CreatedDateUtc) = ?", (year, month)
    return "YEAR(s.CreatedDateUtc) = ?", (year,)


def calc_team_commissions(year: int, month: Optional[int] = None) -> list[TeamCommission]:
    """Calculate commissions for all teams for the given period."""
    date_clause, date_params = _date_filter(year, month)

    # ── Transport reps (TransportationRepId) ──────────────────────────────
    transport_sql = f"""
        SELECT
            t.Id                                AS team_id,
            t.Name                              AS team_name,
            e.Id                                AS employee_id,
            e.Name                              AS employee_name,
            e.Type                              AS employee_type,
            COUNT(s.Id)                         AS shipments,
            SUM(sf.CustomerTotal)               AS revenue,
            SUM(sf.Margin)                      AS margin
        FROM dbo.Shipments s
        JOIN dbo.ShipmentFinancials sf ON sf.ShipmentId = s.Id
        JOIN crm.Teams t               ON t.Id = s.TeamId
        JOIN crm.Employees e           ON e.Id = s.TransportationRepId
        WHERE {date_clause}
          AND sf.CustomerTotal > 0
          AND s.TransportationRepId IS NOT NULL
        GROUP BY t.Id, t.Name, e.Id, e.Name, e.Type
    """
    transport_rows = query(transport_sql, date_params)

    # ── Procurement reps (ProcurementRepId) ───────────────────────────────
    procurement_sql = f"""
        SELECT
            t.Id                                AS team_id,
            t.Name                              AS team_name,
            e.Id                                AS employee_id,
            e.Name                              AS employee_name,
            e.Type                              AS employee_type,
            COUNT(s.Id)                         AS shipments,
            SUM(sf.CustomerTotal)               AS revenue,
            SUM(sf.Margin)                      AS margin
        FROM dbo.Shipments s
        JOIN dbo.ShipmentFinancials sf ON sf.ShipmentId = s.Id
        JOIN crm.Teams t               ON t.Id = s.TeamId
        JOIN crm.Employees e           ON e.Id = s.ProcurementRepId
        WHERE {date_clause}
          AND sf.CustomerTotal > 0
          AND s.ProcurementRepId IS NOT NULL
        GROUP BY t.Id, t.Name, e.Id, e.Name, e.Type
    """
    procurement_rows = query(procurement_sql, date_params)

    # ── Aggregate by team ─────────────────────────────────────────────────
    teams: dict[int, dict] = {}

    def add_employee(rows, rep_type: str):
        for r in rows:
            tid = r["team_id"]
            if tid not in teams:
                teams[tid] = {
                    "team_id": tid,
                    "team_name": r["team_name"],
                    "shipments": 0,
                    "revenue": 0.0,
                    "margin": 0.0,
                    "transport_commission": 0.0,
                    "procurement_commission": 0.0,
                    "employees": {},
                }

            t_rate, p_rate = get_rates(tid)

            revenue = float(r["revenue"] or 0)
            margin  = float(r["margin"] or 0)
            ships   = int(r["shipments"] or 0)

            if rep_type == "transport":
                rate       = t_rate
                commission = revenue * rate
                teams[tid]["transport_commission"] += commission
            else:
                rate       = p_rate
                commission = margin * rate
                teams[tid]["procurement_commission"] += commission

            teams[tid]["shipments"] += ships
            teams[tid]["revenue"]   += revenue
            teams[tid]["margin"]    += margin

            eid = (r["employee_id"], rep_type)
            if eid not in teams[tid]["employees"]:
                teams[tid]["employees"][eid] = EmployeeCommission(
                    employee_id=r["employee_id"],
                    employee_name=r["employee_name"],
                    employee_type=r["employee_type"] or rep_type.upper(),
                    team_id=tid,
                    team_name=r["team_name"],
                    shipments=ships,
                    revenue=revenue,
                    margin=margin,
                    commission_rate=rate,
                    commission=commission,
                )
            else:
                emp = teams[tid]["employees"][eid]
                emp.shipments += ships
                emp.revenue   += revenue
                emp.margin    += margin
                emp.commission += commission

    add_employee(transport_rows,   "transport")
    add_employee(procurement_rows, "procurement")

    result = []
    for t in teams.values():
        t_rate, p_rate = get_rates(t["team_id"])
        avg_margin_pct = (t["margin"] / t["revenue"] * 100) if t["revenue"] else 0
        total_commission = t["transport_commission"] + t["procurement_commission"]
        result.append(TeamCommission(
            team_id=t["team_id"],
            team_name=t["team_name"],
            shipments=t["shipments"],
            revenue=round(t["revenue"], 2),
            margin=round(t["margin"], 2),
            avg_margin_pct=round(avg_margin_pct, 2),
            transport_commission=round(t["transport_commission"], 2),
            procurement_commission=round(t["procurement_commission"], 2),
            total_commission=round(total_commission, 2),
            employees=sorted(t["employees"].values(), key=lambda e: e.commission, reverse=True),
        ))

    return sorted(result, key=lambda t: t.total_commission, reverse=True)


def calc_summary(year: int, month: Optional[int] = None) -> CommissionSummary:
    teams = calc_team_commissions(year, month)
    return CommissionSummary(
        year=year,
        month=month,
        total_shipments=sum(t.shipments for t in teams),
        total_revenue=round(sum(t.revenue for t in teams), 2),
        total_margin=round(sum(t.margin for t in teams), 2),
        total_commission=round(sum(t.total_commission for t in teams), 2),
        teams=teams,
    )
