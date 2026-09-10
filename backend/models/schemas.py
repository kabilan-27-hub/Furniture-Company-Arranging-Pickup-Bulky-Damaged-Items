from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class DeliveryStop:
    delivery_id: str
    customer_id: str
    location: str
    latitude: float
    longitude: float
    delivery_time_window_start: str  # HH:MM
    delivery_time_window_end: str    # HH:MM
    estimated_service_time: int     # minutes
    item_volume: float              # m3
    item_weight: float              # kg
    route_id: str
    vehicle_id: str

@dataclass
class ReturnRequest:
    return_id: str
    customer_id: str
    pickup_location: str
    latitude: float
    longitude: float
    requested_pickup_window_start: str # HH:MM
    requested_pickup_window_end: str   # HH:MM
    item_type: str
    item_length: float                 # meters
    item_width: float                  # meters
    item_height: float                 # meters
    item_volume: float                 # m3
    item_weight: float                 # kg
    handling_requirement: str
    priority: str                      # HIGH, MEDIUM, LOW
    request_status: str                # PENDING, ASSIGNED, REJECTED

@dataclass
class Vehicle:
    vehicle_id: str
    maximum_weight_capacity: float  # kg
    maximum_volume_capacity: float  # m3
    usable_item_length: float       # meters
    usable_item_width: float        # meters
    usable_item_height: float       # meters
    vehicle_type: str
    assigned_driver: str
    assigned_crew: str
    driver_shift_start: str         # HH:MM
    driver_shift_end: str           # HH:MM
    operating_cost_per_km: float    # USD/km
    fuel_emission_factor: float     # kg CO2/km

@dataclass
class RouteStop:
    stop_id: str
    stop_type: str                  # DEPOT, DELIVERY, RETURN
    customer_id: str
    location_name: str
    latitude: float
    longitude: float
    arrival_time: str
    departure_time: str
    time_window_start: str
    time_window_end: str
    service_time_mins: int
    volume_change: float            # - for delivery offload, + for return pickup
    weight_change: float            # - for delivery offload, + for return pickup
    cumulative_volume: float
    cumulative_weight: float
    distance_from_prev_km: float
    travel_time_from_prev_mins: float
    is_late: bool = False
    late_minutes: float = 0.0

@dataclass
class VehicleRoute:
    route_id: str
    vehicle_id: str
    driver_name: str
    stops: List[RouteStop] = field(default_factory=list)
    total_distance_km: float = 0.0
    total_duration_mins: float = 0.0
    total_deliveries: int = 0
    total_returns: int = 0
    max_volume_used: float = 0.0
    max_weight_used: float = 0.0
    volume_utilization_pct: float = 0.0
    weight_utilization_pct: float = 0.0
    overtime_mins: float = 0.0
    is_feasible: bool = True
    constraint_violations: List[str] = field(default_factory=list)

@dataclass
class PlannerOutput:
    plan_name: str
    objective_name: str
    vehicle_routes: List[VehicleRoute]
    assigned_returns: List[str]
    rejected_returns: List[Dict[str, Any]]  # return_id -> reason details
    total_km: float
    incremental_km: float
    baseline_km: float
    target_km: float
    km_reduction_pct: float
    total_cost: float
    total_co2_kg: float
    on_time_pickup_pct: float
    driver_overtime_hours: float
    avg_volume_utilization_pct: float
    avg_weight_utilization_pct: float
