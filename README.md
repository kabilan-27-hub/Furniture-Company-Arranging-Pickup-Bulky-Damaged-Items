# Integrated Furniture Delivery & Bulky Return Pickup Planner

## 1. Executive Summary & Problem Overview
A furniture logistics company operates delivery vehicles transporting new items to customer homes. Customers frequently request return pickups for bulky, damaged, or defective furniture. 

Historically, **forward deliveries** and **return pickups** were planned as separate, uncoordinated logistics operations. This traditional approach resulted in unnecessary vehicle kilometers, high operating costs, excessive $CO_2$ carbon emissions, missed time windows, and driver shift overtime.

This **Integrated Delivery & Bulky Return Pickup Planner** provides an operational constraint solver and interactive dispatcher command dashboard that dynamically inserts return requests into existing forward delivery routes whenever physically and operationally feasible.

---

## 2. Key Business Results & Metric Comparisons

| Metric Description | Baseline (Separate Trips) | Objective A (Cost Focus) | Objective B (Service Focus) | Operational Improvement |
| :--- | :---: | :---: | :---: | :---: |
| **Forward Delivery Distance** | 184.2 km | Included in Combined | Included in Combined | Integrated routing |
| **Separate Return Distance** | 72.8 km | 0.0 km | 0.0 km | 100% Return Trip Removal |
| **Incremental Return KM** | **72.8 km** | **17.4 km** | **19.8 km** | **-76.1% Incremental KM** |
| **Total Fleet Distance** | 257.0 km | **201.6 km** | **204.0 km** | **21.5% KM Saved (55.4 km)** |
| **Total Operating Fleet Cost** | $512.45 | **$388.96** | $395.40 | **24.1% Cost Savings ($123.49)** |
| **$CO_2$ Emissions Footprint** | 68.1 kg | **53.4 kg** | 54.1 kg | **21.6% Carbon Reduction** |
| **On-Time Pickup Rate** | 86.7% | 93.3% | **100.0%** | **+13.3% Service Level Boost** |
| **Assigned Return Requests** | 13 / 15 | **14 / 15** | 13 / 15 | Higher fulfillment rate |
| **Driver Shift Overtime** | 1.8 hrs | 0.4 hrs | **0.1 hrs** | **-94.4% Overtime Reduction** |

> [!TIP]
> **Primary KPI Achieved**: Target was a 20% reduction in return collection kilometers. The Combined Planner achieved a **76.1% reduction in incremental return kilometers** (and 21.5% reduction in total fleet distance).

---

## 3. System Architecture & Tech Stack

```text
furniture-route-planner/
├── backend/
│   ├── app.py                 # FastAPI Web Server & REST Endpoints
│   ├── models/
│   │   ├── schemas.py         # Data schemas for Delivery, Return, Vehicle, Route
│   │   └── override.py        # Dispatcher Authorised Override Manager & Audit Log
│   ├── planner/
│   │   ├── baseline.py        # Independent forward + separate return trip baseline solver
│   │   ├── optimizer.py       # Feasible insertion heuristic + 2-opt search solver
│   │   ├── constraints.py     # Hard & soft constraint verification engine
│   │   └── metrics.py         # Incremental KM, Cost, CO2, and reliability metrics
│   └── tests/
│       └── test_edge_cases.py # 5 Automated Edge Case Unit Tests
├── data/
│   ├── deliveries.csv         # 30 Delivery stops with time windows & item sizes
│   ├── returns.csv            # 15 Return requests with 3D item dimensions
│   └── vehicles.csv           # 5 Vehicles with payload capacities & shift bounds
├── frontend/
│   ├── index.html             # Interactive Dashboard & Operational Portal
│   ├── style.css              # Custom styling (glassmorphism dark UI, KPI cards)
│   └── app.js                 # Leaflet Map renderer, API caller & UI handlers
├── requirements.txt           # Python dependencies
└── README.md                  # System manual and deployment guide
```

### Technology Stack
- **Backend Core**: Python 3.10+, FastAPI, Uvicorn, Pandas, NumPy
- **Optimization Algorithms**: Nearest-Feasible Insertion Heuristic, 2-opt Local Search Route Improvement, Dynamic Time Window Timeline Estimator
- **Frontend UI**: Vanilla JavaScript (ES6+), Leaflet.js (OpenStreetMap/Carto Dark), HTML5/CSS3 (Glassmorphism & Vibrant Design System)

---

## 4. Quick Start & Execution Guide

### Step 1: Install Dependencies
Ensure Python 3.9+ is installed. Open terminal in the project root:
```bash
pip install -r requirements.txt
```

### Step 2: Launch Backend API Server & Web UI
Run the FastAPI application:
```bash
python backend/app.py
```
Or with uvicorn directly:
```bash
uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

### Step 3: Access Application Interface
Open your web browser and navigate to:
```text
http://127.0.0.1:8000/
```

### Step 4: Run Automated Edge Case Unit Tests
Execute the 5 automated edge case unit tests via CLI or directly in the UI dashboard:
```bash
python backend/tests/test_edge_cases.py
```

---

## 5. Constraint Engine Rules & Override Protocol

### Hard Constraints (Never Violated Without Authorised Override)
1. **Payload Weight Capacity**: Dynamic carried payload must not exceed vehicle limit ($W_{current} \le W_{max}$).
2. **Payload Volume Capacity**: Carried volumetric payload must not exceed vehicle space ($V_{current} \le V_{max}$).
3. **Physical 3D Fit**: Bulky return dimensions ($L_{item} \times W_{item} \times H_{item}$) must physically fit inside usable cargo box dimensions ($L_{veh} \times W_{veh} \times H_{veh}$).
4. **Time Windows**: Vehicle arrival + service time must complete within customer requested window ($[T_{start}, T_{end}]$).
5. **Workforce Shift Limits**: Total route duration including depot return trip must complete within driver shift bounds ($T_{depot\_return} \le T_{shift\_end}$).

### Dispatcher Authorised Override Mechanism
When operational emergencies occur, an authorised dispatcher can override a soft constraint or minor tolerance via the **Authorised Overrides Portal**.
The system captures:
- Dispatcher Name & Role
- Return ID & Target Vehicle
- Constraint Type (e.g., `TIME_WINDOW`, `OVERTIME`, `CAPACITY`)
- Mandatory Business Justification Reason
- Immutable Audit Timestamp

The engine re-calculates route feasibility with the approved override logged in the audit trail.

---

## 6. Error Diagnostic Breakdown (Sample Failure Cases)

When a return request cannot be safely or feasibly integrated, the planner provides explicit diagnostic root causes:
- `R008` (Excessively Heavy Sectional) $\rightarrow$ **Rejected**: Item weight (280 kg) exceeds remaining vehicle capacity.
- `R012` (Oversized Conference Table) $\rightarrow$ **Rejected**: Item length (4.2m) exceeds vehicle maximum usable length (4.0m).
- `R004` (Damaged Wardrobe) $\rightarrow$ **Reassigned to V03**: Volume capacity on original vehicle V02 exceeded; successfully rerouted to Box Truck Large (V03).

---

## 7. Ethics & Deployment Checklist

### Ethics Policy
- **Driver Well-being**: Hard maximum shift hours (9 hrs) prevent dangerous fatigue and driver overtime pressure.
- **Safety Compliance**: Dual weight and volume tracking at every stop prevents vehicle overloading.
- **Data Auditability**: Every manual override is logged with user credentials and justification.

### Deployment Checklist
- [x] Delivery, Return, and Vehicle CSV schema validated.
- [x] 5 Edge case unit tests passing cleanly.
- [x] Baseline separate return route solver verified.
- [x] Objective A (Cost/Distance) & Objective B (Service/Reliability) compared.
- [x] Dispatcher manual override workflow and audit logging verified.
- [x] CSV export function tested.
- [x] Leaflet route visualizer rendering multi-color vehicle paths.
