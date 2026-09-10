from typing import List, Dict, Any, Tuple
from backend.models.schemas import DeliveryStop, ReturnRequest, Vehicle, VehicleRoute, RouteStop, PlannerOutput
from backend.planner.constraints import (
    evaluate_route_feasibility,
    haversine_distance,
    time_to_minutes,
    minutes_to_time,
    DEPOT_LAT,
    DEPOT_LON
)
from backend.planner.metrics import calculate_planner_kpis

def solve_baseline_separate(
    deliveries: List[DeliveryStop],
    returns: List[ReturnRequest],
    vehicles: List[Vehicle]
) -> PlannerOutput:
    """
    Baseline Solution:
    1. Forward delivery routes are planned and executed independently per assigned vehicle.
    2. Return pickups are planned as separate trips dispatching dedicated return vehicles.
    """
    veh_map = {v.vehicle_id: v for v in vehicles}
    
    # 1. Group deliveries by vehicle route
    deliveries_by_veh: Dict[str, List[DeliveryStop]] = {}
    for d in deliveries:
        deliveries_by_veh.setdefault(d.vehicle_id, []).append(d)

    forward_routes: List[VehicleRoute] = []
    forward_total_km = 0.0

    for veh_id, veh in veh_map.items():
        v_deliveries = deliveries_by_veh.get(veh_id, [])
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

        is_feas, viols, metrics = evaluate_route_feasibility(veh, stops)
        
        v_route = VehicleRoute(
            route_id=f"FORWARD-{veh_id}",
            vehicle_id=veh_id,
            driver_name=veh.assigned_driver,
            stops=metrics["updated_stops"],
            total_distance_km=metrics["total_distance_km"],
            total_duration_mins=metrics["total_duration_mins"],
            total_deliveries=len(stops),
            total_returns=0,
            max_volume_used=metrics["max_volume_used"],
            max_weight_used=metrics["max_weight_used"],
            volume_utilization_pct=metrics["volume_utilization_pct"],
            weight_utilization_pct=metrics["weight_utilization_pct"],
            overtime_mins=metrics["overtime_mins"],
            is_feasible=is_feas,
            constraint_violations=viols
        )
        forward_routes.append(v_route)
        forward_total_km += metrics["total_distance_km"]

    # 2. Plan Separate Return Trips (Baseline)
    assigned_returns = []
    rejected_returns = []
    separate_return_routes = []
    
    # Sort returns by priority then pickup window start
    priority_map = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    sorted_returns = sorted(returns, key=lambda r: (priority_map.get(r.priority, 1), time_to_minutes(r.requested_pickup_window_start)))

    # Use available vehicles for dedicated return trips after forward deliveries
    ret_route_idx = 1
    for ret in sorted_returns:
        assigned = False
        for veh in vehicles:
            # Create a dedicated route for this return
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

            is_feas, viols, metrics = evaluate_route_feasibility(veh, [ret_stop])
            if is_feas:
                v_route = VehicleRoute(
                    route_id=f"RET-TRIP-{ret_route_idx:02d}",
                    vehicle_id=veh.vehicle_id,
                    driver_name=f"{veh.assigned_driver} (Dedicated Return)",
                    stops=metrics["updated_stops"],
                    total_distance_km=metrics["total_distance_km"],
                    total_duration_mins=metrics["total_duration_mins"],
                    total_deliveries=0,
                    total_returns=1,
                    max_volume_used=metrics["max_volume_used"],
                    max_weight_used=metrics["max_weight_used"],
                    volume_utilization_pct=metrics["volume_utilization_pct"],
                    weight_utilization_pct=metrics["weight_utilization_pct"],
                    overtime_mins=metrics["overtime_mins"],
                    is_feasible=True,
                    constraint_violations=[]
                )
                separate_return_routes.append(v_route)
                assigned_returns.append(ret.return_id)
                assigned = True
                ret_route_idx += 1
                break

        if not assigned:
            rejected_returns.append({
                "return_id": ret.return_id,
                "customer_id": ret.customer_id,
                "reason": "Oversized or capacity conflict for dedicated return trip",
                "item_type": ret.item_type,
                "priority": ret.priority
            })

    all_routes = forward_routes + separate_return_routes
    total_baseline_km = sum(r.total_distance_km for r in all_routes)

    all_ret_ids = [r.return_id for r in returns]
    return calculate_planner_kpis(
        plan_name="Baseline (Separate Return Trips)",
        objective_name="Separate Forward & Return Routing",
        vehicle_routes=all_routes,
        all_return_ids=all_ret_ids,
        assigned_returns=assigned_returns,
        rejected_reasons=rejected_returns,
        baseline_km=total_baseline_km,
        target_km_reduction_pct=20.0
    )
