import sys
from backend.models.schemas import DeliveryStop, ReturnRequest, Vehicle
from backend.planner.constraints import check_item_physical_fit, evaluate_route_feasibility
from backend.planner.optimizer import solve_combined_planner
from backend.planner.baseline import solve_baseline_separate

def test_edge_case_1_capacity_overflow():
    """
    Edge Case 1: Capacity Overflow
    A return item weight/volume exceeds remaining vehicle capacity.
    Expected: Request rejected or assigned to feasible vehicle with clear diagnostic.
    """
    veh = Vehicle(
        vehicle_id="V_TEST1",
        maximum_weight_capacity=100.0,  # Tight capacity
        maximum_volume_capacity=2.0,
        usable_item_length=3.0,
        usable_item_width=2.0,
        usable_item_height=2.0,
        vehicle_type="Test Van",
        assigned_driver="Tester",
        assigned_crew="1-Person",
        driver_shift_start="08:00",
        driver_shift_end="17:00",
        operating_cost_per_km=1.5,
        fuel_emission_factor=0.2
    )

    deliv = DeliveryStop(
        delivery_id="D_TEST1",
        customer_id="C_TEST",
        location="Stop 1",
        latitude=40.7300,
        longitude=-73.9900,
        delivery_time_window_start="08:30",
        delivery_time_window_end="10:00",
        estimated_service_time=15,
        item_volume=1.5,
        item_weight=80.0, # Uses 80kg out of 100kg
        route_id="RT_TEST",
        vehicle_id="V_TEST1"
    )

    heavy_return = ReturnRequest(
        return_id="R_OVERFLOW",
        customer_id="C_RET",
        pickup_location="Return Stop",
        latitude=40.7350,
        longitude=-73.9850,
        requested_pickup_window_start="10:30",
        requested_pickup_window_end="12:00",
        item_type="Heavy Marble Table",
        item_length=1.5,
        item_width=1.0,
        item_height=0.8,
        item_volume=1.2,
        item_weight=120.0, # 120kg exceeds 100kg vehicle max capacity
        handling_requirement="2-Person",
        priority="HIGH",
        request_status="PENDING"
    )

    res = solve_combined_planner([deliv], [heavy_return], [veh], objective="OBJECTIVE_A")
    
    assert "R_OVERFLOW" in [r["return_id"] for r in res.rejected_returns]
    rejection = next(r for r in res.rejected_returns if r["return_id"] == "R_OVERFLOW")
    assert "capacity" in rejection["reason"].lower() or "overflow" in rejection["reason"].lower() or "exceeds" in rejection["reason"].lower()

def test_edge_case_2_time_window_conflict():
    """
    Edge Case 2: Time-Window Conflict
    Return pickup requested window conflicts with mandatory delivery schedule.
    Expected: Request rejected or flagged with time-window conflict diagnostic.
    """
    veh = Vehicle(
        vehicle_id="V_TEST2",
        maximum_weight_capacity=1000.0,
        maximum_volume_capacity=10.0,
        usable_item_length=3.0,
        usable_item_width=2.0,
        usable_item_height=2.0,
        vehicle_type="Test Van",
        assigned_driver="Tester",
        assigned_crew="1-Person",
        driver_shift_start="08:00",
        driver_shift_end="17:00",
        operating_cost_per_km=1.5,
        fuel_emission_factor=0.2
    )

    deliv1 = DeliveryStop(
        delivery_id="D1",
        customer_id="C1",
        location="Location 1",
        latitude=40.7000,
        longitude=-74.0000,
        delivery_time_window_start="08:30",
        delivery_time_window_end="09:00",
        estimated_service_time=30,
        item_volume=1.0,
        item_weight=20.0,
        route_id="RT_TEST2",
        vehicle_id="V_TEST2"
    )

    conflict_return = ReturnRequest(
        return_id="R_TIME_CONFLICT",
        customer_id="C_RET2",
        pickup_location="Far Location",
        latitude=40.8500, # Far North Manhattan (~20 km away)
        longitude=-73.9000,
        requested_pickup_window_start="08:30", # Impossible to reach before 09:00
        requested_pickup_window_end="08:45",
        item_type="Chair",
        item_length=0.8,
        item_width=0.8,
        item_height=0.8,
        item_volume=0.5,
        item_weight=15.0,
        handling_requirement="1-Person",
        priority="MEDIUM",
        request_status="PENDING"
    )

    res = solve_combined_planner([deliv1], [conflict_return], [veh], objective="OBJECTIVE_A")
    assert "R_TIME_CONFLICT" in [r["return_id"] for r in res.rejected_returns]

def test_edge_case_3_oversized_item():
    """
    Edge Case 3: Oversized Item
    Item length 4.5m exceeds vehicle usable length 3.0m.
    Expected: Physical fit rejected.
    """
    veh = Vehicle(
        vehicle_id="V_TEST3",
        maximum_weight_capacity=2000.0,
        maximum_volume_capacity=20.0,
        usable_item_length=3.0,
        usable_item_width=2.0,
        usable_item_height=2.0,
        vehicle_type="Small Truck",
        assigned_driver="Tester",
        assigned_crew="1-Person",
        driver_shift_start="08:00",
        driver_shift_end="17:00",
        operating_cost_per_km=1.5,
        fuel_emission_factor=0.2
    )

    huge_return = ReturnRequest(
        return_id="R_OVERSIZED",
        customer_id="C_RET3",
        pickup_location="Location",
        latitude=40.7300,
        longitude=-73.9900,
        requested_pickup_window_start="10:00",
        requested_pickup_window_end="14:00",
        item_type="Long Conference Beam",
        item_length=4.5, # Exceeds 3.0m
        item_width=1.0,
        item_height=1.0,
        item_volume=4.5,
        item_weight=100.0,
        handling_requirement="2-Person",
        priority="HIGH",
        request_status="PENDING"
    )

    fits, reason = check_item_physical_fit(huge_return, veh)
    assert not fits
    assert "Oversized" in reason

def test_edge_case_4_driver_shift_limit():
    """
    Edge Case 4: Driver Shift Limit
    Adding pickup causes vehicle return to depot after 17:30 (shift end 17:00).
    Expected: Shift overtime limit violation diagnostic.
    """
    veh = Vehicle(
        vehicle_id="V_TEST4",
        maximum_weight_capacity=2000.0,
        maximum_volume_capacity=20.0,
        usable_item_length=4.0,
        usable_item_width=2.0,
        usable_item_height=2.0,
        vehicle_type="Truck",
        assigned_driver="Tester",
        assigned_crew="1-Person",
        driver_shift_start="08:00",
        driver_shift_end="17:00",
        operating_cost_per_km=1.5,
        fuel_emission_factor=0.2
    )

    deliv = DeliveryStop(
        delivery_id="D_LATE",
        customer_id="C_LATE",
        location="Near Depot",
        latitude=40.7300,
        longitude=-73.9350,
        delivery_time_window_start="16:00",
        delivery_time_window_end="16:45",
        estimated_service_time=25,
        item_volume=1.0,
        item_weight=20.0,
        route_id="RT_TEST4",
        vehicle_id="V_TEST4"
    )

    far_late_return = ReturnRequest(
        return_id="R_OVERTIME",
        customer_id="C_RET4",
        pickup_location="Far Away",
        latitude=40.6000, # South Brooklyn (~20 km away)
        longitude=-74.0500,
        requested_pickup_window_start="16:30",
        requested_pickup_window_end="17:30",
        item_type="Sofa",
        item_length=1.5,
        item_width=1.0,
        item_height=1.0,
        item_volume=1.5,
        item_weight=40.0,
        handling_requirement="1-Person",
        priority="MEDIUM",
        request_status="PENDING"
    )

    res = solve_combined_planner([deliv], [far_late_return], [veh], objective="OBJECTIVE_A")
    assert "R_OVERTIME" in [r["return_id"] for r in res.rejected_returns]

def test_edge_case_5_multiple_returns_priority():
    """
    Edge Case 5: Multiple Return Requests Competition
    When limited capacity exists, HIGH priority returns are scheduled over LOW priority.
    """
    veh = Vehicle(
        vehicle_id="V_TEST5",
        maximum_weight_capacity=60.0, # Fits only 1 return item (50kg)
        maximum_volume_capacity=3.0,
        usable_item_length=3.0,
        usable_item_width=2.0,
        usable_item_height=2.0,
        vehicle_type="Small Van",
        assigned_driver="Tester",
        assigned_crew="1-Person",
        driver_shift_start="08:00",
        driver_shift_end="17:00",
        operating_cost_per_km=1.5,
        fuel_emission_factor=0.2
    )

    high_ret = ReturnRequest(
        return_id="R_HIGH",
        customer_id="CH",
        pickup_location="High Prio Loc",
        latitude=40.7350,
        longitude=-73.9850,
        requested_pickup_window_start="10:00",
        requested_pickup_window_end="12:00",
        item_type="Urgent Sofa",
        item_length=1.5,
        item_width=1.0,
        item_height=0.8,
        item_volume=1.2,
        item_weight=50.0,
        handling_requirement="1-Person",
        priority="HIGH",
        request_status="PENDING"
    )

    low_ret = ReturnRequest(
        return_id="R_LOW",
        customer_id="CL",
        pickup_location="Low Prio Loc",
        latitude=40.7360,
        longitude=-73.9840,
        requested_pickup_window_start="10:00",
        requested_pickup_window_end="12:00",
        item_type="Minor Chair",
        item_length=0.8,
        item_width=0.8,
        item_height=0.8,
        item_volume=0.5,
        item_weight=40.0,
        handling_requirement="1-Person",
        priority="LOW",
        request_status="PENDING"
    )

    res = solve_combined_planner([], [high_ret, low_ret], [veh], objective="OBJECTIVE_A")
    assert "R_HIGH" in res.assigned_returns
    assert "R_LOW" in [r["return_id"] for r in res.rejected_returns]

if __name__ == "__main__":
    print("Executing Edge Case Tests...")
    test_edge_case_1_capacity_overflow()
    test_edge_case_2_time_window_conflict()
    test_edge_case_3_oversized_item()
    test_edge_case_4_driver_shift_limit()
    test_edge_case_5_multiple_returns_priority()
    print("ALL 5 EDGE CASE TESTS PASSED SUCCESSFULLY!")
