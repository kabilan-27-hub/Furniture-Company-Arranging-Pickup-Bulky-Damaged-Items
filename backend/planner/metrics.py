from typing import List, Dict, Any
from backend.models.schemas import PlannerOutput, VehicleRoute

def calculate_planner_kpis(
    plan_name: str,
    objective_name: str,
    vehicle_routes: List[VehicleRoute],
    all_return_ids: List[str],
    assigned_returns: List[str],
    rejected_reasons: List[Dict[str, Any]],
    baseline_km: float,
    target_km_reduction_pct: float = 20.0
) -> PlannerOutput:
    """
    Calculate full suite of KPIs for cost, service, capacity, workforce, environmental and reliability impact.
    """
    total_km = sum(r.total_distance_km for r in vehicle_routes)
    incremental_km = max(0.0, total_km - baseline_km) if "Baseline" not in plan_name else baseline_km
    
    km_reduction_pct = 0.0
    if "Baseline" not in plan_name and baseline_km > 0:
        km_reduction_pct = round(((baseline_km - total_km) / baseline_km) * 100.0, 1)

    target_km = round(baseline_km * (1.0 - (target_km_reduction_pct / 100.0)), 2)

    # Cost Calculation: operating cost per km ($1.85 avg) + driver overtime cost ($35/hr)
    total_operating_cost = 0.0
    total_co2_kg = 0.0
    total_overtime_mins = 0.0
    total_vol_util_pct = 0.0
    total_wt_util_pct = 0.0
    
    total_stops = 0
    total_late_stops = 0

    for r in vehicle_routes:
        # Assuming average operating cost $1.85/km & emission 0.265 kg/km if vehicle cost not passed
        total_operating_cost += r.total_distance_km * 1.85 + (r.overtime_mins / 60.0) * 35.0
        total_co2_kg += r.total_distance_km * 0.265
        total_overtime_mins += r.overtime_mins
        total_vol_util_pct += r.volume_utilization_pct
        total_wt_util_pct += r.weight_utilization_pct

        for stop in r.stops:
            if stop.stop_type == "RETURN":
                total_stops += 1
                if stop.is_late:
                    total_late_stops += 1

    num_vehicles = max(1, len(vehicle_routes))
    avg_vol_util = round(total_vol_util_pct / num_vehicles, 1)
    avg_wt_util = round(total_wt_util_pct / num_vehicles, 1)

    on_time_pct = 100.0
    if total_stops > 0:
        on_time_pct = round(((total_stops - total_late_stops) / total_stops) * 100.0, 1)

    return PlannerOutput(
        plan_name=plan_name,
        objective_name=objective_name,
        vehicle_routes=vehicle_routes,
        assigned_returns=assigned_returns,
        rejected_returns=rejected_reasons,
        total_km=round(total_km, 2),
        incremental_km=round(incremental_km, 2),
        baseline_km=round(baseline_km, 2),
        target_km=target_km,
        km_reduction_pct=km_reduction_pct,
        total_cost=round(total_operating_cost, 2),
        total_co2_kg=round(total_co2_kg, 2),
        on_time_pickup_pct=on_time_pct,
        driver_overtime_hours=round(total_overtime_mins / 60.0, 2),
        avg_volume_utilization_pct=avg_vol_util,
        avg_weight_utilization_pct=avg_wt_util
    )
