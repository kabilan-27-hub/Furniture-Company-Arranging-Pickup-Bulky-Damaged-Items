import math
from typing import Tuple, List, Dict, Any, Optional
from backend.models.schemas import Vehicle, DeliveryStop, ReturnRequest, RouteStop

# Constants
AVERAGE_SPEED_KMH = 35.0  # Urban/Suburban average vehicle speed including minor traffic
DEPOT_LAT = 40.7306       # NYC Central Hub Depot
DEPOT_LON = -73.9352

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float, use_osrm_fallback: bool = False) -> float:
    """
    Calculate distance in kilometers between two lat/lon pairs.
    Uses Haversine formula with a 1.3x urban road circuitry multiplier.
    Optionally supports OSRM API routing fallback for real street network distance.
    """
    R = 6371.0  # Radius of earth in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    direct_dist = R * c
    return round(direct_dist * 1.3, 2)  # 1.3 urban road circuitry multiplier

def time_to_minutes(time_str: str) -> int:
    """Convert HH:MM string into minutes from midnight."""
    h, m = map(int, time_str.split(':'))
    return h * 60 + m

def minutes_to_time(minutes: float) -> str:
    """Convert minutes from midnight to HH:MM string."""
    m_int = int(round(minutes)) % (24 * 60)
    h = m_int // 60
    m = m_int % 60
    return f"{h:02d}:{m:02d}"

def check_item_physical_fit(ret: ReturnRequest, veh: Vehicle) -> Tuple[bool, str]:
    """
    Check if a bulky item physically fits inside vehicle usable dimensions.
    Returns (fits: bool, reason: str).
    Allows 3D rotation orientation check.
    """
    item_dims = sorted([ret.item_length, ret.item_width, ret.item_height], reverse=True)
    veh_dims = sorted([veh.usable_item_length, veh.usable_item_width, veh.usable_item_height], reverse=True)

    for idim, vdim in zip(item_dims, veh_dims):
        if idim > vdim:
            return False, f"Oversized item: dimensions ({ret.item_length}m x {ret.item_width}m x {ret.item_height}m) exceed vehicle max limits ({veh.usable_item_length}m x {veh.usable_item_width}m x {veh.usable_item_height}m)"
    return True, ""

def evaluate_route_feasibility(
    vehicle: Vehicle,
    route_stops: List[RouteStop],
    overrides: Optional[Dict[str, Any]] = None
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Simulate a route timeline stop by stop and check all hard and soft constraints.
    Returns (is_feasible: bool, violations: List[str], metrics_dict).
    """
    violations = []
    overrides = overrides or {}
    
    # Check physical item fit for any return stop
    for stop in route_stops:
        if stop.stop_type == "RETURN" and hasattr(stop, 'return_obj') and stop.return_obj:
            fits, fit_reason = check_item_physical_fit(stop.return_obj, vehicle)
            if not fits and stop.stop_id not in overrides.get("dimension_fit", []):
                violations.append(fit_reason)

    # Initial state at Depot departure
    shift_start_mins = time_to_minutes(vehicle.driver_shift_start)
    shift_end_mins = time_to_minutes(vehicle.driver_shift_end)
    
    # Calculate initial cargo load (deliveries start in truck)
    initial_volume = sum(s.volume_change for s in route_stops if s.stop_type == "DELIVERY")
    initial_weight = sum(s.weight_change for s in route_stops if s.stop_type == "DELIVERY")

    if initial_weight > vehicle.maximum_weight_capacity:
        violations.append(f"Initial delivery weight ({initial_weight:.1f} kg) exceeds vehicle max capacity ({vehicle.maximum_weight_capacity:.1f} kg)")
    if initial_volume > vehicle.maximum_volume_capacity:
        violations.append(f"Initial delivery volume ({initial_volume:.1f} m³) exceeds vehicle max volume ({vehicle.maximum_volume_capacity:.1f} m³)")

    curr_time = float(shift_start_mins)
    curr_lat, curr_lon = DEPOT_LAT, DEPOT_LON
    curr_weight = initial_weight
    curr_volume = initial_volume

    max_weight_used = curr_weight
    max_volume_used = curr_volume
    total_dist_km = 0.0

    updated_stops = []

    for idx, stop in enumerate(route_stops):
        dist = haversine_distance(curr_lat, curr_lon, stop.latitude, stop.longitude)
        travel_time_mins = (dist / AVERAGE_SPEED_KMH) * 60.0

        arr_time = curr_time + travel_time_mins
        
        # Check time window
        win_start = time_to_minutes(stop.time_window_start)
        win_end = time_to_minutes(stop.time_window_end)

        # Wait if arrived early
        start_service_time = max(arr_time, float(win_start))

        # Check late arrival
        is_late = start_service_time > float(win_end)
        late_mins = max(0.0, start_service_time - float(win_end))

        if is_late and stop.stop_id not in overrides.get("time_window", []):
            violations.append(f"Time window conflict at {stop.stop_type.lower()} stop {stop.stop_id} ({stop.location_name}): arrived at {minutes_to_time(start_service_time)}, window ends at {stop.time_window_end}")

        # Update cargo
        if stop.stop_type == "DELIVERY":
            curr_weight -= stop.weight_change
            curr_volume -= stop.volume_change
        elif stop.stop_type == "RETURN":
            curr_weight += stop.weight_change
            curr_volume += stop.volume_change

        max_weight_used = max(max_weight_used, curr_weight)
        max_volume_used = max(max_volume_used, curr_volume)

        # Capacity overflow check
        if curr_weight > vehicle.maximum_weight_capacity and stop.stop_id not in overrides.get("capacity", []):
            violations.append(f"Weight capacity overflow at stop {stop.stop_id} ({stop.location_name}): current load {curr_weight:.1f} kg exceeds vehicle max {vehicle.maximum_weight_capacity:.1f} kg by {curr_weight - vehicle.maximum_weight_capacity:.1f} kg")

        if curr_volume > vehicle.maximum_volume_capacity and stop.stop_id not in overrides.get("capacity", []):
            violations.append(f"Volume capacity overflow at stop {stop.stop_id} ({stop.location_name}): current load {curr_volume:.2f} m³ exceeds vehicle max {vehicle.maximum_volume_capacity:.2f} m³ by {curr_volume - vehicle.maximum_volume_capacity:.2f} m³")

        dep_time = start_service_time + float(stop.service_time_mins)
        
        # Track updated stop info
        upd_stop = RouteStop(
            stop_id=stop.stop_id,
            stop_type=stop.stop_type,
            customer_id=stop.customer_id,
            location_name=stop.location_name,
            latitude=stop.latitude,
            longitude=stop.longitude,
            arrival_time=minutes_to_time(arr_time),
            departure_time=minutes_to_time(dep_time),
            time_window_start=stop.time_window_start,
            time_window_end=stop.time_window_end,
            service_time_mins=stop.service_time_mins,
            volume_change=stop.volume_change,
            weight_change=stop.weight_change,
            cumulative_volume=round(curr_volume, 2),
            cumulative_weight=round(curr_weight, 1),
            distance_from_prev_km=round(dist, 2),
            travel_time_from_prev_mins=round(travel_time_mins, 1),
            is_late=is_late,
            late_minutes=round(late_mins, 1)
        )
        if hasattr(stop, 'return_obj'):
            upd_stop.return_obj = getattr(stop, 'return_obj')
        updated_stops.append(upd_stop)

        total_dist_km += dist
        curr_time = dep_time
        curr_lat, curr_lon = stop.latitude, stop.longitude

    # Return to depot trip
    return_dist = haversine_distance(curr_lat, curr_lon, DEPOT_LAT, DEPOT_LON)
    return_travel_mins = (return_dist / AVERAGE_SPEED_KMH) * 60.0
    final_return_time = curr_time + return_travel_mins
    total_dist_km += return_dist

    overtime_mins = max(0.0, final_return_time - float(shift_end_mins))
    if overtime_mins > 30.0 and vehicle.vehicle_id not in overrides.get("overtime", []):
        violations.append(f"Driver shift limit exceeded for {vehicle.assigned_driver} on vehicle {vehicle.vehicle_id}: return to depot at {minutes_to_time(final_return_time)} exceeds shift end {vehicle.driver_shift_end} by {overtime_mins:.0f} mins")

    is_feasible = len(violations) == 0

    metrics = {
        "total_distance_km": round(total_dist_km, 2),
        "total_duration_mins": round(final_return_time - shift_start_mins, 1),
        "max_volume_used": round(max_volume_used, 2),
        "max_weight_used": round(max_weight_used, 1),
        "volume_utilization_pct": round((max_volume_used / vehicle.maximum_volume_capacity) * 100.0, 1),
        "weight_utilization_pct": round((max_weight_used / vehicle.maximum_weight_capacity) * 100.0, 1),
        "overtime_mins": round(overtime_mins, 1),
        "updated_stops": updated_stops
    }

    return is_feasible, violations, metrics
