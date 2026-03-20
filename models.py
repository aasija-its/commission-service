from pydantic import BaseModel, Field
from typing import Optional


class CommissionRate(BaseModel):
    team_id: Optional[int] = None          # None = global default
    transport_rate: float = Field(..., ge=0, le=1, description="% of revenue for transport reps")
    procurement_rate: float = Field(..., ge=0, le=1, description="% of margin for procurement reps")
    description: Optional[str] = None


class EmployeeCommission(BaseModel):
    employee_id: int
    employee_name: str
    employee_type: str                     # SALE / PROC / etc.
    team_id: Optional[int]
    team_name: Optional[str]
    shipments: int
    revenue: float
    margin: float
    commission_rate: float
    commission: float


class TeamCommission(BaseModel):
    team_id: Optional[int]
    team_name: str
    shipments: int
    revenue: float
    margin: float
    avg_margin_pct: float
    transport_commission: float            # from transport reps
    procurement_commission: float          # from procurement reps
    total_commission: float
    employees: list[EmployeeCommission] = []


class CommissionSummary(BaseModel):
    year: int
    month: Optional[int]
    total_shipments: int
    total_revenue: float
    total_margin: float
    total_commission: float
    teams: list[TeamCommission]
