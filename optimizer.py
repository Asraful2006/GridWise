import pulp
from models import EnergyScenarioRequest, HourlyPlan


def solve_energy_schedule(
    scenario: EnergyScenarioRequest,
    directives: list[dict],
):
    battery = scenario.battery
    hours_data = scenario.hours

    if len(hours_data) != 24:
        raise ValueError("Exactly 24 hourly records are required.")

    # Default constraints
    solar_factors = [1.0] * 24
    no_charge = [False] * 24
    no_discharge = [False] * 24
    max_grid = [1000.0] * 24
    min_reserve = [battery.minimum_energy_kwh] * 24

    # Apply LLM directives
    for directive in directives:
        if not directive.get("applies", False):
            continue

        d_type = directive.get("directive_type")
        adjustment = directive.get("structured_adjustment") or {}

        hours = adjustment.get("hours", [])

        if d_type == "solar_reduction":
            factor = adjustment.get("factor", 1.0)

            for h in hours:
                if 0 <= h < 24:
                    solar_factors[h] = factor

        elif d_type == "no_charge_window":
            for h in hours:
                if 0 <= h < 24:
                    no_charge[h] = True

        elif d_type == "no_discharge_window":
            for h in hours:
                if 0 <= h < 24:
                    no_discharge[h] = True

        elif d_type == "max_grid_window":
            limit = adjustment.get("max_grid_kwh", float("inf"))

            for h in hours:
                if 0 <= h < 24:
                    max_grid[h] = limit

        elif d_type == "minimum_battery_reserve":
            reserve = adjustment.get(
                "minimum_energy_kwh",
                battery.minimum_energy_kwh,
            )

            for h in hours:
                if 0 <= h < 24:
                    min_reserve[h] = max(
                        min_reserve[h],
                        reserve,
                    )

    # Optimization model
    prob = pulp.LpProblem(
        "GridWise_Energy_Optimization",
        pulp.LpMinimize,
    )

    grid = [
        pulp.LpVariable(
            f"grid_{t}",
            lowBound=0,
            upBound=max_grid[t],
        )
        for t in range(24)
    ]

    charge = [
        pulp.LpVariable(
            f"charge_{t}",
            lowBound=0,
            upBound=battery.max_charge_kwh_per_hour,
        )
        for t in range(24)
    ]

    discharge = [
        pulp.LpVariable(
            f"discharge_{t}",
            lowBound=0,
            upBound=battery.max_discharge_kwh_per_hour,
        )
        for t in range(24)
    ]

    soc = [
        pulp.LpVariable(
            f"soc_{t}",
            lowBound=0,
            upBound=battery.capacity_kwh,
        )
        for t in range(25)
    ]

    # Initial and final battery energy
    prob += soc[0] == battery.initial_energy_kwh
    prob += soc[24] == battery.initial_energy_kwh

    # Hourly constraints
    for t in range(24):

        solar = hours_data[t].solar_kwh * solar_factors[t]

        # Energy balance
        prob += (
            grid[t]
            + solar
            + discharge[t]
            == hours_data[t].demand_kwh + charge[t]
        )

        # Battery continuity
        prob += (
            soc[t + 1]
            == soc[t] + charge[t] - discharge[t]
        )

        # Minimum reserve
        prob += soc[t + 1] >= min_reserve[t]

        # Operator constraints
        if no_charge[t]:
            prob += charge[t] == 0

        if no_discharge[t]:
            prob += discharge[t] == 0

    # Minimize electricity cost
    prob += pulp.lpSum(
        grid[t] * hours_data[t].tariff_bdt_per_kwh
        for t in range(24)
    )

    # Solve
    status = prob.solve(
        pulp.PULP_CBC_CMD(msg=False)
    )

    if pulp.LpStatus[status] != "Optimal":
        raise ValueError(
            f"Optimization failed: {pulp.LpStatus[status]}"
        )

    hourly_plans = []
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    for t in range(24):

        grid_value = max(
            0.0,
            pulp.value(grid[t]) or 0.0,
        )

        charge_value = max(
            0.0,
            pulp.value(charge[t]) or 0.0,
        )

        discharge_value = max(
            0.0,
            pulp.value(discharge[t]) or 0.0,
        )

        soc_value = max(
            0.0,
            pulp.value(soc[t + 1]) or 0.0,
        )

        solar_value = (
            hours_data[t].solar_kwh
            * solar_factors[t]
        )

        cost = (
            grid_value
            * hours_data[t].tariff_bdt_per_kwh
        )

        if charge_value > 0.01:
            action = "charge"
            battery_value = charge_value

        elif discharge_value > 0.01:
            action = "discharge"
            battery_value = discharge_value

        else:
            action = "idle"
            battery_value = 0.0

        hourly_plans.append(
            HourlyPlan(
                hour=t,
                grid_kwh=round(grid_value, 2),
                solar_used_kwh=round(solar_value, 2),
                battery_action=action,
                battery_kwh=round(battery_value, 2),
                battery_energy_after_kwh=round(soc_value, 2),
                hourly_cost_bdt=round(cost, 2),
            )
        )

        total_grid += grid_value
        total_cost += cost
        peak_grid = max(
            peak_grid,
            grid_value,
        )

    return (
        hourly_plans,
        round(total_grid, 2),
        round(total_cost, 2),
        round(peak_grid, 2),
    )