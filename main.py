from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from models import EnergyScenarioRequest, OptimizeEnergyResponse
from llm_interpreter import parse_operator_notes
from optimizer import solve_energy_schedule


app = FastAPI(
    title="GridWise LLM Energy Optimizer API",
    version="1.0.0",
)


@app.get("/")
def home():
    return FileResponse("index.html")


@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }


@app.post(
    "/optimize-energy",
    response_model=OptimizeEnergyResponse,
)
def optimize_energy(
    scenario: EnergyScenarioRequest,
):
    try:
        directives = parse_operator_notes(
            scenario.operator_notes
        )

        (
            hourly_plans,
            total_grid,
            total_cost,
            peak_grid,
        ) = solve_energy_schedule(
            scenario,
            directives,
        )

        return OptimizeEnergyResponse(
            scenario_id=scenario.scenario_id,
            directive_interpretation=directives,
            hourly_plan=hourly_plans,
            total_grid_kwh=total_grid,
            total_cost_bdt=total_cost,
            peak_grid_kwh=peak_grid,
            plan_summary=(
                "Optimized 24-hour energy schedule "
                "generated successfully."
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Optimization failed: {str(exc)}",
        )