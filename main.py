import datetime
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import APPLICATIONINSIGHTS_CONNECTION_STRING
from models import CommissionRate, CommissionSummary, TeamCommission, EmployeeCommission
import commission as engine

# ── Telemetry ────────────────────────────────────────────────────────────────
if APPLICATIONINSIGHTS_CONNECTION_STRING:
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(connection_string=APPLICATIONINSIGHTS_CONNECTION_STRING)

logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Commission Service",
    description="Calculates rep and team commissions based on shipment revenue and margin.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Helpers ───────────────────────────────────────────────────────────────────
def _current_year() -> int:
    return datetime.datetime.utcnow().year


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["observability"])
def health():
    return {"status": "ok", "timestamp": datetime.datetime.utcnow().isoformat()}


# ── Commission rates ──────────────────────────────────────────────────────────
@app.get("/commission-rates", tags=["rates"], response_model=list[CommissionRate])
def get_rates():
    """Return all configured commission rate overrides plus the global default."""
    rates = [
        CommissionRate(
            team_id=None,
            transport_rate=engine.DEFAULT_TRANSPORT_RATE,
            procurement_rate=engine.DEFAULT_PROCUREMENT_RATE,
            description="Global default",
        )
    ]
    for team_id, override in engine.RATE_OVERRIDES.items():
        rates.append(CommissionRate(
            team_id=team_id,
            transport_rate=override["transport"],
            procurement_rate=override["procurement"],
            description=f"Override for team {team_id}",
        ))
    return rates


@app.post("/commission-rates", tags=["rates"], status_code=201)
def set_rate(rate: CommissionRate):
    """
    Set a commission rate override for a specific team, or update the global
    default by omitting team_id.
    """
    if rate.team_id is None:
        engine.DEFAULT_TRANSPORT_RATE   = rate.transport_rate
        engine.DEFAULT_PROCUREMENT_RATE = rate.procurement_rate
        logger.info("Global commission rates updated", extra={"transport": rate.transport_rate, "procurement": rate.procurement_rate})
        return {"message": "Global default rates updated"}

    engine.RATE_OVERRIDES[rate.team_id] = {
        "transport":   rate.transport_rate,
        "procurement": rate.procurement_rate,
    }
    logger.info("Team commission rate updated", extra={"team_id": rate.team_id})
    return {"message": f"Rates updated for team {rate.team_id}"}


@app.delete("/commission-rates/{team_id}", tags=["rates"])
def delete_rate(team_id: int):
    """Remove a team-specific rate override (reverts to global default)."""
    if team_id not in engine.RATE_OVERRIDES:
        raise HTTPException(status_code=404, detail="No override found for this team")
    del engine.RATE_OVERRIDES[team_id]
    return {"message": f"Override removed for team {team_id}"}


# ── Commission summary ────────────────────────────────────────────────────────
@app.get("/commissions/summary", tags=["commissions"], response_model=CommissionSummary)
def commission_summary(
    year:  int           = Query(default_factory=_current_year, description="Year (e.g. 2025)"),
    month: Optional[int] = Query(default=None, ge=1, le=12,    description="Month 1–12, omit for full year"),
):
    """Overall commission summary across all teams for a given period."""
    logger.info("Commission summary requested", extra={"year": year, "month": month})
    return engine.calc_summary(year, month)


# ── By team ───────────────────────────────────────────────────────────────────
@app.get("/commissions/teams", tags=["commissions"], response_model=list[TeamCommission])
def commissions_by_team(
    year:  int           = Query(default_factory=_current_year),
    month: Optional[int] = Query(default=None, ge=1, le=12),
):
    """Commission breakdown for every team, sorted by total commission descending."""
    return engine.calc_team_commissions(year, month)


@app.get("/commissions/teams/{team_id}", tags=["commissions"], response_model=TeamCommission)
def commission_for_team(
    team_id: int,
    year:    int           = Query(default_factory=_current_year),
    month:   Optional[int] = Query(default=None, ge=1, le=12),
):
    """Commission detail for a single team including per-employee breakdown."""
    teams = engine.calc_team_commissions(year, month)
    match = next((t for t in teams if t.team_id == team_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found or no shipments in period")
    return match


# ── By employee ───────────────────────────────────────────────────────────────
@app.get("/commissions/employees", tags=["commissions"], response_model=list[EmployeeCommission])
def commissions_by_employee(
    year:  int           = Query(default_factory=_current_year),
    month: Optional[int] = Query(default=None, ge=1, le=12),
):
    """Commission for every rep across all teams, sorted by commission descending."""
    teams = engine.calc_team_commissions(year, month)
    employees = [emp for t in teams for emp in t.employees]
    return sorted(employees, key=lambda e: e.commission, reverse=True)


@app.get("/commissions/employees/{employee_id}", tags=["commissions"], response_model=list[EmployeeCommission])
def commission_for_employee(
    employee_id: int,
    year:        int           = Query(default_factory=_current_year),
    month:       Optional[int] = Query(default=None, ge=1, le=12),
):
    """
    Commission for a specific employee.
    Returns a list because a rep may appear as both transport and procurement.
    """
    teams = engine.calc_team_commissions(year, month)
    results = [emp for t in teams for emp in t.employees if emp.employee_id == employee_id]
    if not results:
        raise HTTPException(status_code=404, detail=f"Employee {employee_id} not found or no shipments in period")
    return results
