import copy
from typing import List, Dict, Any, Tuple, Optional
from backend.models.schemas import DeliveryStop, ReturnRequest, Vehicle, VehicleRoute, RouteStop, PlannerOutput
from backend.planner.constraints import (
    evaluate_route_feasibility,
    check_item_physical_fit,
    time_to_minutes,
    minutes_to_time
)
from backend.planner.metrics import calculate_planner_kpis
from backend.models.override import override_manager

def evaluate_insertion_score(
    objective: str,
    delta_km: float,
    delta_time_mins: float,
    is_late: bool,
    late_mins: float,
    overtime_mins: float,
    priority: str
) -> float:
    """
    Score an insertion option. Lower score is better.
    Objective A — Cost/Distance Optimization:
        Score = 0.5 * Delta_KM + 0.3 * Operating_Cost + 0.2 * Route_Deviation_Time
    Objective B — Service/Reliability Optimization:
        Score = 0.4 * Late_Penalty + 0.3 * Wait_Penalty + 0.2 * Overtime_Penalty + 0.1 * Delta_KM
    """
    prio_bonus = {"HIGH": -15.0, "MEDIUM": -5.0, "LOW": 0.0}.get(priority, 0.0)

    if objective == "OBJECTIVE_A":  # Cost / Distance Focus
        operating_cost = delta_km * 1.85
        score = (0.5 * delta_km) + (0.3 * operating_cost) + (0.2 * delta_time_mins) + (10.0 if is_late else 0.0) + prio_bonus
    else:  # OBJECTIVE_B — Service / Reliability Focus
        late_penalty = (late_mins * 2.0) if is_late else 0.0
        overtime_penalty = overtime_mins * 1.5
        score = (0.4 * late_penalty) + (0.3 * overtime_penalty) + (0.1 * delta_km) + prio_bonus

    return score

def solve_combined_planner(
    deliveries: List[DeliveryStop],
    returns: List[ReturnRequest],
    vehicles: List[Vehicle],
    objective: str = "OBJECTIVE_A",
    baseline_km: float = 0.0,
    active_overrides: Optional[Dict[str, Any]] = None
) -> PlannerOutput:
    """
    Combined Forward Delivery + Return Pickup Planner Engine.
    Uses Greedy Insertion + Feasibility Checking + 2-opt route refinement.
    Evaluates both Objective A (Cost/Distance) and Objective B (Service/Reliability).
    """
    veh_map = {v.vehicle_id: v for v in vehicles}
    active_overrides = active_overrides or {}

    # Initial state: Build forward delivery routes per vehicle
    routes_by_veh: Dict[str, List[RouteStop]] = {v.vehicle_id: [] for v in vehicles}
    
    deliveries_by_veh: Dict[str, List[DeliveryStop]] = {}
    for d in deliveries:
        deliveries_by_veh.setdefault(d.vehicle_id, []).append(d)

    for veh_id, v_deliveries in deliveries_by_veh.items():
        if veh_id not in veh_map:
            continue
        sorted_delivs = sorted(v_deliveries, key=lambda x: time_to_minutes(x.delivery_time_window_start))
        stops = []
        for d in sorted_delivs:
            s = RouteStop(
                stop_id=d.delivery_id,
                stop_type="DELIVERY",
                customer_id=d.customer_id,
                location_name=d.location,
                latitude=d.latitude,
                longitude=d.longitude,
                arrival_time=d.delivery_time_window_start,
                departure_time=d.delivery_time_window_end,
                time_window_start=d.delivery_time_window_start,
                time_window_end=d.delivery_time_window_end,
                service_time_mins=d.estimated_service_time,
                volume_change=d.item_volume,
                weight_change=d.item_weight,
                cumulative_volume=0.0,
                cumulative_weight=0.0,
                distance_from_prev_km=0.0,
                travel_time_from_prev_mins=0.0
            )
            stops.append(s)
        routes_by_veh[veh_id] = stops

    # Prepare return requests
    prio_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    sorted_returns = sorted(returns, key=lambda r: (prio_order.get(r.priority, 1), time_to_minutes(r.requested_pickup_window_start)))

    assigned_returns: List[str] = []
    rejected_reasons: List[Dict[str, Any]] = []

    # Iterative insertion heuristic
    for ret in sorted_returns:
        best_candidate = None
        best_score = float('inf')
        rejection_diagnostic_log = []

        ret_stop = RouteStop(
            stop_id=ret.return_id,
            stop_type="RETURN",
            customer_id=ret.customer_id,
            location_name=ret.pickup_location,
            latitude=ret.latitude,
            longitude=ret.longitude,
            arrival_time=ret.requested_pickup_window_start,
            departure_time=ret.requested_pickup_window_end,
            time_window_start=ret.requested_pickup_window_start,
            time_window_end=ret.requested_pickup_window_end,
            service_time_mins=20,
            volume_change=ret.item_volume,
            weight_change=ret.item_weight,
            cumulative_volume=0.0,
            cumulative_weight=0.0,
            distance_from_prev_km=0.0,
            travel_time_from_prev_mins=0.0
        )
        setattr(ret_stop, 'return_obj', ret)

        # Check dispatcher manual override first
        overridden_rec = override_manager.is_return_overridden(ret.return_id)

        # Try inserting into each vehicle route at every possible index i
        for veh_id, current_stops in routes_by_veh.items():
            veh = veh_map[veh_id]

            # Physical dimensions check
            fits, fit_msg = check_item_physical_fit(ret, veh)
            if not fits and (not overridden_rec or overridden_rec.constraint_overridden != "DIMENSION_FIT"):
                rejection_diagnostic_log.append(f"Vehicle {veh_id}: {fit_msg}")
                continue

            # Original route baseline stats
            orig_is_feas, _, orig_metrics = evaluate_route_feasibility(veh, current_stops, active_overrides)

            for idx in range(len(current_stops) + 1):
                candidate_stops = current_stops[:idx] + [ret_stop] + current_stops[idx:]

                # Check override applicability
                eff_overrides = copy.deepcopy(active_overrides)
                if overridden_rec and overridden_rec.target_vehicle_id == veh_id:
                    c_type = overridden_rec.constraint_overridden.lower()
                    eff_overrides.setdefault(c_type, []).append(ret.return_id)

                is_feas, viols, new_metrics = evaluate_route_feasibility(veh, candidate_stops, eff_overrides)

                if is_feas or overridden_rec:
                    delta_km = new_metrics["total_distance_km"] - orig_metrics["total_distance_km"]
                    delta_time = new_metrics["total_duration_mins"] - orig_metrics["total_duration_mins"]

                    # Find inserted stop to check lateness
                    inserted_stop = next((s for s in new_metrics["updated_stops"] if s.stop_id == ret.return_id), None)
                    is_late = inserted_stop.is_late if inserted_stop else False
                    late_mins = inserted_stop.late_minutes if inserted_stop else 0.0

                    score = evaluate_insertion_score(
                        objective=objective,
                        delta_km=delta_km,
                        delta_time_mins=delta_time,
                        is_late=is_late,
                        late_mins=late_mins,
                        overtime_mins=new_metrics["overtime_mins"],
                        priority=ret.priority
                    )

                    if score < best_score:
                        best_score = score
                        best_candidate = {
                            "vehicle_id": veh_id,
                            "index": idx,
                            "candidate_stops": candidate_stops,
                            "metrics": new_metrics
                        }
                else:
                    for v_msg in viols:
                        rejection_diagnostic_log.append(f"Vehicle {veh_id} (stop pos {idx}): {v_msg}")

        if best_candidate:
            veh_id = best_candidate["vehicle_id"]
            routes_by_veh[veh_id] = best_candidate["candidate_stops"]
            assigned_returns.append(ret.return_id)
        else:
            primary_reason = rejection_diagnostic_log[0] if rejection_diagnostic_log else "No feasible vehicle route insertion point found respecting capacity/time window bounds"
            rejected_reasons.append({
                "return_id": ret.return_id,
                "customer_id": ret.customer_id,
                "reason": primary_reason,
                "all_diagnostics": rejection_diagnostic_log,
                "item_type": ret.item_type,
                "item_volume": ret.item_volume,
                "item_weight": ret.item_weight,
                "priority": ret.priority
            })

    # 3. 2-opt Refinement on Final Routes
    final_vehicle_routes: List[VehicleRoute] = []

    for veh_id, final_stops in routes_by_veh.items():
        veh = veh_map[veh_id]
        
        # 2-opt search
        improved = True
        best_stops = final_stops
        _, _, best_metrics = evaluate_route_feasibility(veh, best_stops, active_overrides)

        while improved:
            improved = False
            for i in range(1, len(best_stops) - 1):
                for j in range(i + 1, len(best_stops)):
                    # Swap segment [i:j]
                    cand = best_stops[:i] + list(reversed(best_stops[i:j])) + best_stops[j:]
                    is_f, _, c_metrics = evaluate_route_feasibility(veh, cand, active_overrides)
                    if is_f and c_metrics["total_distance_km"] < best_metrics["total_distance_km"]:
                        best_stops = cand
                        best_metrics = c_metrics
                        improved = True
                        break
                if improved:
                    break

        is_feas, viols, final_metrics = evaluate_route_feasibility(veh, best_stops, active_overrides)
        
        deliv_count = sum(1 for s in best_stops if s.stop_type == "DELIVERY")
        ret_count = sum(1 for s in best_stops if s.stop_type == "RETURN")

        v_route = VehicleRoute(
            route_id=f"COMBINED-{veh_id}",
            vehicle_id=veh_id,
            driver_name=veh.assigned_driver,
            stops=final_metrics["updated_stops"],
            total_distance_km=final_metrics["total_distance_km"],
            total_duration_mins=final_metrics["total_duration_mins"],
            total_deliveries=deliv_count,
            total_returns=ret_count,
            max_volume_used=final_metrics["max_volume_used"],
            max_weight_used=final_metrics["max_weight_used"],
            volume_utilization_pct=final_metrics["volume_utilization_pct"],
            weight_utilization_pct=final_metrics["weight_utilization_pct"],
            overtime_mins=final_metrics["overtime_mins"],
            is_feasible=is_feas,
            constraint_violations=viols
        )
        final_vehicle_routes.append(v_route)

    obj_title = "Objective A — Cost & Distance Optimization" if objective == "OBJECTIVE_A" else "Objective B — Service & Reliability Optimization"
    all_ret_ids = [r.return_id for r in returns]

    return calculate_planner_kpis(
        plan_name=f"Combined Plan ({objective})",
        objective_name=obj_title,
        vehicle_routes=final_vehicle_routes,
        all_return_ids=all_ret_ids,
        assigned_returns=assigned_returns,
        rejected_reasons=rejected_reasons,
        baseline_km=baseline_km,
        target_km_reduction_pct=20.0
    )
