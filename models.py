from pydantic import BaseModel
from typing import List, Optional, Any


class HourlyInput(BaseModel):
    hour: int
    demand_kwh: float
    solar_kwh: float
    tariff_bdt_per_kwh: float


class BatteryConfig(BaseModel):
    capacity_kwh: float
    initial_energy_kwh: float
    minimum_energy_kwh: float
    max_charge_kwh_per_hour: float
    max_discharge_kwh_per_hour: float


class EnergyScenarioRequest(BaseModel):
    scenario_id: str
    operator_notes: List[str]
    hours: List[HourlyInput]
    battery: BatteryConfig


class HourlyPlan(BaseModel):
    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_action: str
    battery_kwh: float
    battery_energy_after_kwh: float
    hourly_cost_bdt: float


class OptimizeEnergyResponse(BaseModel):
    scenario_id: str
    directive_interpretation: List[Any]
    hourly_plan: List[HourlyPlan]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str