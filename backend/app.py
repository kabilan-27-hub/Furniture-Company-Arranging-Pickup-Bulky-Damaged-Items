import os
import csv
import io
import json
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.models.schemas import DeliveryStop, ReturnRequest, Vehicle
from backend.models.override import AuthorisedOverrideRequest, override_manager
from backend.planner.baseline import solve_baseline_separate
from backend.planner.optimizer import solve_combined_planner
from backend.tests.test_edge_cases import (
    test_edge_case_1_capacity_overflow,
    test_edge_case_2_time_window_conflict,
    test_edge_case_3_oversized_item,
    test_edge_case_4_driver_shift_limit,
    test_edge_case_5_multiple_returns_priority
)

app = FastAPI(title="Furniture Delivery & Bulky Return Pickup Planner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

# In-Memory Data Store
dataset_store: Dict[str, Any] = {
    "deliveries": [],
    "returns": [],
    "vehicles": []
}

def load_default_data():
    """Load default CSV files from data directory."""
    deliv_path = os.path.join(DATA_DIR, "deliveries.csv")
    ret_path = os.path.join(DATA_DIR, "returns.csv")
    veh_path = os.path.join(DATA_DIR, "vehicles.csv")

    deliveries = []
    if os.path.exists(deliv_path):
        with open(deliv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                deliveries.append(DeliveryStop(
                    delivery_id=row["delivery_id"],
                    customer_id=row["customer_id"],
                    location=row["location"],
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    delivery_time_window_start=row["delivery_time_window_start"],
                    delivery_time_window_end=row["delivery_time_window_end"],
                    estimated_service_time=int(row["estimated_service_time"]),
                    item_volume=float(row["item_volume"]),
                    item_weight=float(row["item_weight"]),
                    route_id=row["route_id"],
                    vehicle_id=row["vehicle_id"]
                ))

    returns = []
    if os.path.exists(ret_path):
        with open(ret_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                returns.append(ReturnRequest(
                    return_id=row["return_id"],
                    customer_id=row["customer_id"],
                    pickup_location=row["pickup_location"],
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    requested_pickup_window_start=row["requested_pickup_window_start"],
                    requested_pickup_window_end=row["requested_pickup_window_end"],
                    item_type=row["item_type"],
                    item_length=float(row["item_length"]),
                    item_width=float(row["item_width"]),
                    item_height=float(row["item_height"]),
                    item_volume=float(row["item_volume"]),
                    item_weight=float(row["item_weight"]),
                    handling_requirement=row["handling_requirement"],
                    priority=row["priority"],
                    request_status=row["request_status"]
                ))

    vehicles = []
    if os.path.exists(veh_path):
        with open(veh_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                vehicles.append(Vehicle(
                    vehicle_id=row["vehicle_id"],
                    maximum_weight_capacity=float(row["maximum_weight_capacity"]),
                    maximum_volume_capacity=float(row["maximum_volume_capacity"]),
                    usable_item_length=float(row["usable_item_length"]),
                    usable_item_width=float(row["usable_item_width"]),
                    usable_item_height=float(row["usable_item_height"]),
                    vehicle_type=row["vehicle_type"],
                    assigned_driver=row["assigned_driver"],
                    assigned_crew=row["assigned_crew"],
                    driver_shift_start=row["driver_shift_start"],
                    driver_shift_end=row["driver_shift_end"],
                    operating_cost_per_km=float(row["operating_cost_per_km"]),
                    fuel_emission_factor=float(row["fuel_emission_factor"])
                ))

    dataset_store["deliveries"] = deliveries
    dataset_store["returns"] = returns
    dataset_store["vehicles"] = vehicles

# Initialize dataset on startup
load_default_data()

# FastAPI Request Models
class RegisterUserPayload(BaseModel):
    name: str
    company: str
    email: str
    phone: str
    role: str
    password: str

class LoginUserPayload(BaseModel):
    email: str
    password: str

class OverridePayload(BaseModel):
    dispatcher_name: str
    dispatcher_role: str
    return_id: str
    target_vehicle_id: str
    constraint_overridden: str
    reason: str

# In-memory user store for demo auth
users_db: Dict[str, Dict[str, str]] = {}

@app.post("/api/auth/register")
def register_user(payload: RegisterUserPayload):
    email = payload.email.strip().lower()
    if not payload.name.strip() or not payload.company.strip() or not email or not payload.phone.strip() or not payload.role.strip() or len(payload.password.strip()) < 6:
        raise HTTPException(status_code=400, detail="Please complete all fields with a password of at least 6 characters.")

    if email in users_db:
        raise HTTPException(status_code=409, detail="A user with this email already exists.")

    users_db[email] = {
        "name": payload.name.strip(),
        "company": payload.company.strip(),
        "email": email,
        "phone": payload.phone.strip(),
        "role": payload.role.strip(),
        "password": payload.password.strip()
    }

    return {
        "status": "SUCCESS",
        "message": "Registration successful.",
        "user": {
            "name": payload.name.strip(),
            "email": email,
            "company": payload.company.strip(),
            "role": payload.role.strip()
        }
    }

@app.post("/api/auth/login")
def login_user(payload: LoginUserPayload):
    email = payload.email.strip().lower()
    password = payload.password.strip()

    user = users_db.get(email)
    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    return {
        "status": "SUCCESS",
        "message": "Login successful.",
        "user": {
            "name": user["name"],
            "email": user["email"],
            "company": user["company"],
            "role": user["role"]
        }
    }

@app.get("/api/data/summary")
def get_data_summary():
    return {
        "deliveries_count": len(dataset_store["deliveries"]),
        "returns_count": len(dataset_store["returns"]),
        "vehicles_count": len(dataset_store["vehicles"]),
        "deliveries": dataset_store["deliveries"],
        "returns": dataset_store["returns"],
        "vehicles": dataset_store["vehicles"]
    }

@app.get("/api/plan/solve")
def solve_planner(objective: str = "OBJECTIVE_A"):
    deliveries = dataset_store["deliveries"]
    returns = dataset_store["returns"]
    vehicles = dataset_store["vehicles"]

    if not deliveries or not vehicles:
        raise HTTPException(status_code=400, detail="Data not loaded")

    # Run Baseline to calculate baseline KM
    baseline_output = solve_baseline_separate(deliveries, returns, vehicles)
    
    if objective == "BASELINE":
        return baseline_output

    combined_output = solve_combined_planner(
        deliveries=deliveries,
        returns=returns,
        vehicles=vehicles,
        objective=objective,
        baseline_km=baseline_output.total_km
    )
    return combined_output

@app.get("/api/plan/compare")
def compare_all_plans():
    deliveries = dataset_store["deliveries"]
    returns = dataset_store["returns"]
    vehicles = dataset_store["vehicles"]

    baseline_out = solve_baseline_separate(deliveries, returns, vehicles)
    
    obj_a_out = solve_combined_planner(
        deliveries=deliveries,
        returns=returns,
        vehicles=vehicles,
        objective="OBJECTIVE_A",
        baseline_km=baseline_out.total_km
    )

    obj_b_out = solve_combined_planner(
        deliveries=deliveries,
        returns=returns,
        vehicles=vehicles,
        objective="OBJECTIVE_B",
        baseline_km=baseline_out.total_km
    )

    return {
        "baseline": baseline_out,
        "objective_a": obj_a_out,
        "objective_b": obj_b_out,
        "overrides": override_manager.get_overrides()
    }

@app.post("/api/override/apply")
def apply_authorised_override(payload: OverridePayload):
    req = AuthorisedOverrideRequest(
        override_id=f"OVR-{len(override_manager.get_overrides())+1:03d}",
        dispatcher_name=payload.dispatcher_name,
        dispatcher_role=payload.dispatcher_role,
        return_id=payload.return_id,
        target_vehicle_id=payload.target_vehicle_id,
        constraint_overridden=payload.constraint_overridden,
        reason=payload.reason,
        timestamp=""
    )
    impact = f"Overrode constraint '{payload.constraint_overridden}' for return {payload.return_id} assigned to {payload.target_vehicle_id}. Reason: {payload.reason}"
    audit_rec = override_manager.add_override(req, impact)

    # Re-run plan with override
    deliveries = dataset_store["deliveries"]
    returns = dataset_store["returns"]
    vehicles = dataset_store["vehicles"]
    baseline_out = solve_baseline_separate(deliveries, returns, vehicles)
    
    recalculated_plan = solve_combined_planner(
        deliveries=deliveries,
        returns=returns,
        vehicles=vehicles,
        objective="OBJECTIVE_A",
        baseline_km=baseline_out.total_km
    )

    return {
        "status": "SUCCESS",
        "audit_record": audit_rec,
        "updated_plan": recalculated_plan
    }

@app.get("/api/overrides")
def get_all_overrides():
    return override_manager.get_overrides()

@app.get("/api/tests/run")
def run_edge_case_tests():
    results = []
    
    # Test 1
    try:
        test_edge_case_1_capacity_overflow()
        results.append({"test_name": "Edge Case 1 — Capacity Overflow", "status": "PASSED", "details": "Return item exceeding weight capacity correctly rejected"})
    except Exception as e:
        results.append({"test_name": "Edge Case 1 — Capacity Overflow", "status": "FAILED", "details": str(e)})

    # Test 2
    try:
        test_edge_case_2_time_window_conflict()
        results.append({"test_name": "Edge Case 2 — Time Window Conflict", "status": "PASSED", "details": "Infeasible pickup time window correctly rejected"})
    except Exception as e:
        results.append({"test_name": "Edge Case 2 — Time Window Conflict", "status": "FAILED", "details": str(e)})

    # Test 3
    try:
        test_edge_case_3_oversized_item()
        results.append({"test_name": "Edge Case 3 — Oversized Item", "status": "PASSED", "details": "Physical item length > vehicle length correctly rejected"})
    except Exception as e:
        results.append({"test_name": "Edge Case 3 — Oversized Item", "status": "FAILED", "details": str(e)})

    # Test 4
    try:
        test_edge_case_4_driver_shift_limit()
        results.append({"test_name": "Edge Case 4 — Driver Shift Limit", "status": "PASSED", "details": "Pickup exceeding driver max shift hours correctly rejected"})
    except Exception as e:
        results.append({"test_name": "Edge Case 4 — Driver Shift Limit", "status": "FAILED", "details": str(e)})

    # Test 5
    try:
        test_edge_case_5_multiple_returns_priority()
        results.append({"test_name": "Edge Case 5 — Multiple Returns Priority", "status": "PASSED", "details": "HIGH priority returns favored over LOW priority under tight capacity"})
    except Exception as e:
        results.append({"test_name": "Edge Case 5 — Multiple Returns Priority", "status": "FAILED", "details": str(e)})

    all_passed = all(r["status"] == "PASSED" for r in results)
    return {
        "all_passed": all_passed,
        "summary": "5 of 5 Edge Case Automated Tests Passed Successfully" if all_passed else "Some Edge Case Tests Failed",
        "tests": results
    }

@app.get("/api/export/csv")
def export_plan_csv(objective: str = "OBJECTIVE_A"):
    deliveries = dataset_store["deliveries"]
    returns = dataset_store["returns"]
    vehicles = dataset_store["vehicles"]

    baseline_out = solve_baseline_separate(deliveries, returns, vehicles)
    plan_out = solve_combined_planner(
        deliveries=deliveries,
        returns=returns,
        vehicles=vehicles,
        objective=objective,
        baseline_km=baseline_out.total_km
    )

    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header and route stops
    writer.writerow([
        "Plan Name", "Route ID", "Vehicle ID", "Driver", "Stop Seq", "Stop ID",
        "Stop Type", "Customer ID", "Location", "Arrival Time", "Departure Time",
        "Time Window Start", "Time Window End", "Cumulative Volume (m3)", "Cumulative Weight (kg)", "Distance from Prev (km)", "Is Late"
    ])

    for route in plan_out.vehicle_routes:
        for idx, stop in enumerate(route.stops, 1):
            writer.writerow([
                plan_out.plan_name, route.route_id, route.vehicle_id, route.driver_name,
                idx, stop.stop_id, stop.stop_type, stop.customer_id, stop.location_name,
                stop.arrival_time, stop.departure_time, stop.time_window_start,
                stop.time_window_end, stop.cumulative_volume, stop.cumulative_weight,
                stop.distance_from_prev_km, stop.is_late
            ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=furniture_routes_{objective}.csv"}
    )

# Serve Frontend static files
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    with open(index_file, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
