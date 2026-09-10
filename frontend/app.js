document.addEventListener('DOMContentLoaded', () => {
    // API base URL
    const API_BASE = '';

    const appContainer = document.getElementById('app-container');
    const authScreen = document.getElementById('auth-screen');
    const loginForm = document.getElementById('login-form');
    const loginMessage = document.getElementById('login-message');
    const registerForm = document.getElementById('register-form');
    const registerMessage = document.getElementById('register-message');
    const authTitle = document.getElementById('auth-title');

    function showAuthView(mode = 'login') {
        document.querySelectorAll('.auth-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.auth === mode);
        });
        document.getElementById('login-form').classList.toggle('active', mode === 'login');
        document.getElementById('register-form').classList.toggle('active', mode === 'register');
        authTitle.textContent = mode === 'login' ? 'Sign in to your account' : 'Create your account';
    }

    document.querySelectorAll('.auth-tab').forEach(tab => {
        tab.addEventListener('click', () => showAuthView(tab.dataset.auth));
    });

    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            name: document.getElementById('register-name').value.trim(),
            company: document.getElementById('register-company').value.trim(),
            email: document.getElementById('register-email').value.trim().toLowerCase(),
            phone: document.getElementById('register-phone').value.trim(),
            role: document.getElementById('register-role').value,
            password: document.getElementById('register-password').value.trim()
        };

        if (!payload.name || !payload.company || !payload.email || !payload.phone || !payload.role || !payload.password) {
            registerMessage.textContent = 'Please fill all registration fields.';
            registerMessage.className = 'auth-message error';
            return;
        }

        if (payload.password.length < 6) {
            registerMessage.textContent = 'Password must be at least 6 characters.';
            registerMessage.className = 'auth-message error';
            return;
        }

        try {
            const res = await fetch(`${API_BASE}/api/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (!res.ok) {
                registerMessage.textContent = data.detail || 'Registration failed.';
                registerMessage.className = 'auth-message error';
                return;
            }

            registerMessage.textContent = 'Account registered successfully.';
            registerMessage.className = 'auth-message success';
            registerForm.reset();
            showAuthView('login');
        } catch (err) {
            registerMessage.textContent = 'Unable to register right now.';
            registerMessage.className = 'auth-message error';
        }
    });

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            email: document.getElementById('login-email').value.trim().toLowerCase(),
            password: document.getElementById('login-password').value.trim()
        };

        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (!res.ok) {
                loginMessage.textContent = data.detail || 'Invalid email or password.';
                loginMessage.className = 'auth-message error';
                return;
            }

            loginMessage.textContent = 'Login successful.';
            loginMessage.className = 'auth-message success';
            authScreen.classList.add('auth-screen-hidden');
            appContainer.style.display = 'flex';

            await fetchSummaryData();
            await runPlanner();
        } catch (err) {
            loginMessage.textContent = 'Unable to reach the authentication service.';
            loginMessage.className = 'auth-message error';
        }
    });

    // State Variables
    let currentPlanData = null;
    let comparisonData = null;
    let defaultSummary = null;
    let leafletMap = null;
    let mapLayers = [];

    // Vehicle Colors for Map Routes
    const vehicleColors = {
        "V01": "#3b82f6", // Blue
        "V02": "#10b981", // Green
        "V03": "#8b5cf6", // Purple
        "V04": "#f59e0b", // Orange
        "V05": "#06b6d4", // Cyan
        "DEFAULT": "#ef4444"
    };

    // Initialize Map
    function initMap() {
        if (leafletMap) return;
        // Centered over NYC Urban Hub
        leafletMap = L.map('route-map').setView([40.7350, -73.9850], 12);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap &copy; CARTO',
            maxZoom: 18
        }).addTo(leafletMap);
    }

    // Navigation Tab Switching
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            
            btn.classList.add('active');
            const targetTab = btn.getAttribute('data-tab');
            document.getElementById(targetTab).classList.add('active');

            if (targetTab === 'map-tab') {
                setTimeout(() => {
                    initMap();
                    leafletMap.invalidateSize();
                    renderMapRoutes();
                }, 100);
            }
        });
    });

    // Fetch Initial Summary Data
    async function fetchSummaryData() {
        try {
            const res = await fetch(`${API_BASE}/api/data/summary`);
            defaultSummary = await res.json();
            document.getElementById('dataset-summary-text').innerText = 
                `${defaultSummary.vehicles_count} Vehicles | ${defaultSummary.deliveries_count} Deliveries | ${defaultSummary.returns_count} Returns`;

            populateOverrideDropdowns();
        } catch (err) {
            console.error("Error fetching summary data:", err);
        }
    }

    // Populate Return and Vehicle Dropdowns for Override Modal
    function populateOverrideDropdowns() {
        if (!defaultSummary) return;

        const retSelect = document.getElementById('ovr-return-id');
        retSelect.innerHTML = '<option value="">Select Return...</option>';
        defaultSummary.returns.forEach(r => {
            const opt = document.createElement('option');
            opt.value = r.return_id;
            opt.innerText = `${r.return_id} — ${r.item_type} (${r.pickup_location})`;
            retSelect.appendChild(opt);
        });

        const vehSelect = document.getElementById('ovr-vehicle-id');
        vehSelect.innerHTML = '<option value="">Select Vehicle...</option>';
        defaultSummary.vehicles.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.vehicle_id;
            opt.innerText = `${v.vehicle_id} — ${v.vehicle_type} (${v.assigned_driver})`;
            vehSelect.appendChild(opt);
        });
    }

    // Run Planner API Call
    async function runPlanner() {
        const objective = document.getElementById('objective-select').value;
        const btn = document.getElementById('run-planner-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Optimizing Routes...';

        try {
            const res = await fetch(`${API_BASE}/api/plan/solve?objective=${objective}`);
            currentPlanData = await res.json();
            
            updateDashboardKPIs(currentPlanData);
            renderRejectionDiagnostics(currentPlanData.rejected_returns);
            populateRouteFilter(currentPlanData.vehicle_routes);
            renderTimelineSequence(currentPlanData.vehicle_routes);

            if (leafletMap) renderMapRoutes();

            // Also fetch 3-way comparative experiment metrics
            await runComparativeExperiment();

        } catch (err) {
            console.error("Planner execution failed:", err);
            alert("Error running route planner engine.");
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-play"></i> Run Route Planner';
        }
    }

    // Update Dashboard Top KPI Cards
    function updateDashboardKPIs(data) {
        document.getElementById('kpi-baseline-km').innerText = `${data.baseline_km.toFixed(1)} km`;
        document.getElementById('kpi-incremental-km').innerText = `${data.incremental_km.toFixed(1)} km`;
        
        const redSpan = document.getElementById('kpi-km-reduction-pct');
        redSpan.innerText = `${data.km_reduction_pct.toFixed(1)}% Reduction vs Baseline`;
        if (data.km_reduction_pct >= 20.0) {
            redSpan.className = "kpi-subtext green-text";
        } else {
            redSpan.className = "kpi-subtext blue-text";
        }

        document.getElementById('kpi-total-cost').innerText = `$${data.total_cost.toLocaleString()}`;
        document.getElementById('kpi-co2').innerText = `${data.total_co2_kg.toFixed(1)} kg`;
        document.getElementById('kpi-ontime-pct').innerText = `${data.on_time_pickup_pct.toFixed(1)}%`;
        document.getElementById('kpi-utilization').innerText = `${data.avg_volume_utilization_pct.toFixed(1)}% Vol / ${data.avg_weight_utilization_pct.toFixed(1)}% Wt`;
    }

    // Run 3-Way Comparative Experiment (Baseline vs Obj A vs Obj B)
    async function runComparativeExperiment() {
        try {
            const res = await fetch(`${API_BASE}/api/plan/compare`);
            comparisonData = await res.json();

            const base = comparisonData.baseline;
            const obja = comparisonData.objective_a;
            const objb = comparisonData.objective_b;

            document.getElementById('comp-base-fwd').innerText = `${base.total_km.toFixed(1)} km`;
            document.getElementById('comp-obja-fwd').innerText = `Included in Combined`;
            document.getElementById('comp-objb-fwd').innerText = `Included in Combined`;

            document.getElementById('comp-base-ret').innerText = `${base.incremental_km.toFixed(1)} km`;
            document.getElementById('comp-base-inc').innerText = `${base.incremental_km.toFixed(1)} km`;
            document.getElementById('comp-obja-inc').innerText = `${obja.incremental_km.toFixed(1)} km (-${obja.km_reduction_pct}%)`;
            document.getElementById('comp-objb-inc').innerText = `${objb.incremental_km.toFixed(1)} km (-${objb.km_reduction_pct}%)`;

            document.getElementById('comp-best-inc').innerHTML = obja.incremental_km <= objb.incremental_km ? 
                `<span class="badge badge-success">Obj A (${obja.incremental_km.toFixed(1)} km)</span>` : 
                `<span class="badge badge-success">Obj B (${objb.incremental_km.toFixed(1)} km)</span>`;

            document.getElementById('comp-base-total-km').innerText = `${base.total_km.toFixed(1)} km`;
            document.getElementById('comp-obja-total-km').innerText = `${obja.total_km.toFixed(1)} km`;
            document.getElementById('comp-objb-total-km').innerText = `${objb.total_km.toFixed(1)} km`;
            document.getElementById('comp-best-total-km').innerText = `${Math.min(obja.total_km, objb.total_km).toFixed(1)} km`;

            document.getElementById('comp-base-cost').innerText = `$${base.total_cost.toFixed(2)}`;
            document.getElementById('comp-obja-cost').innerText = `$${obja.total_cost.toFixed(2)}`;
            document.getElementById('comp-objb-cost').innerText = `$${objb.total_cost.toFixed(2)}`;
            document.getElementById('comp-best-cost').innerText = `$${Math.min(obja.total_cost, objb.total_cost).toFixed(2)}`;

            document.getElementById('comp-base-co2').innerText = `${base.total_co2_kg.toFixed(1)} kg`;
            document.getElementById('comp-obja-co2').innerText = `${obja.total_co2_kg.toFixed(1)} kg`;
            document.getElementById('comp-objb-co2').innerText = `${objb.total_co2_kg.toFixed(1)} kg`;
            document.getElementById('comp-best-co2').innerText = `${Math.min(obja.total_co2_kg, objb.total_co2_kg).toFixed(1)} kg`;

            document.getElementById('comp-base-ontime').innerText = `${base.on_time_pickup_pct.toFixed(1)}%`;
            document.getElementById('comp-obja-ontime').innerText = `${obja.on_time_pickup_pct.toFixed(1)}%`;
            document.getElementById('comp-objb-ontime').innerText = `${objb.on_time_pickup_pct.toFixed(1)}%`;
            document.getElementById('comp-best-ontime').innerText = `${Math.max(obja.on_time_pickup_pct, objb.on_time_pickup_pct).toFixed(1)}%`;

            const totalRetCount = defaultSummary ? defaultSummary.returns_count : 15;
            document.getElementById('comp-base-assigned').innerText = `${base.assigned_returns.length} / ${totalRetCount}`;
            document.getElementById('comp-obja-assigned').innerText = `${obja.assigned_returns.length} / ${totalRetCount}`;
            document.getElementById('comp-objb-assigned').innerText = `${objb.assigned_returns.length} / ${totalRetCount}`;
            document.getElementById('comp-best-assigned').innerText = `${Math.max(obja.assigned_returns.length, objb.assigned_returns.length)} / ${totalRetCount}`;

            document.getElementById('comp-base-overtime').innerText = `${base.driver_overtime_hours.toFixed(2)} hrs`;
            document.getElementById('comp-obja-overtime').innerText = `${obja.driver_overtime_hours.toFixed(2)} hrs`;
            document.getElementById('comp-objb-overtime').innerText = `${objb.driver_overtime_hours.toFixed(2)} hrs`;
            document.getElementById('comp-best-overtime').innerText = `${Math.min(obja.driver_overtime_hours, objb.driver_overtime_hours).toFixed(2)} hrs`;

            document.getElementById('comp-base-vol-util').innerText = `${base.avg_volume_utilization_pct.toFixed(1)}%`;
            document.getElementById('comp-obja-vol-util').innerText = `${obja.avg_volume_utilization_pct.toFixed(1)}%`;
            document.getElementById('comp-objb-vol-util').innerText = `${objb.avg_volume_utilization_pct.toFixed(1)}%`;
            document.getElementById('comp-best-vol-util').innerText = `${Math.max(obja.avg_volume_utilization_pct, objb.avg_volume_utilization_pct).toFixed(1)}%`;

            renderOverridesTable(comparisonData.overrides);
        } catch (err) {
            console.error("Error fetching comparison data:", err);
        }
    }

    // Render Rejection Diagnostics Table
    function renderRejectionDiagnostics(rejections) {
        const tbody = document.getElementById('rejections-tbody');
        const badge = document.getElementById('rejection-count-badge');
        
        tbody.innerHTML = '';
        badge.innerText = `${rejections.length} Rejected`;

        if (!rejections || rejections.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">All return requests successfully integrated into delivery routes!</td></tr>';
            return;
        }

        rejections.forEach(r => {
            const tr = document.createElement('tr');
            const prioBadge = r.priority === 'HIGH' ? 'badge-danger' : (r.priority === 'MEDIUM' ? 'badge-warning' : 'badge-secondary');
            
            tr.innerHTML = `
                <td><strong>${r.return_id}</strong></td>
                <td>${r.customer_id}</td>
                <td>${r.item_type || 'Bulky Item'}</td>
                <td>${r.item_volume || '--'} m³ / ${r.item_weight || '--'} kg</td>
                <td><span class="badge ${prioBadge}">${r.priority}</span></td>
                <td><span class="red-text"><i class="fa-solid fa-triangle-exclamation"></i> ${r.reason}</span></td>
                <td>
                    <button class="btn btn-sm btn-outline open-ovr-for-ret" data-ret="${r.return_id}">
                        <i class="fa-solid fa-user-shield"></i> Override
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });

        document.querySelectorAll('.open-ovr-for-ret').forEach(b => {
            b.addEventListener('click', (e) => {
                const retId = e.currentTarget.getAttribute('data-ret');
                document.getElementById('ovr-return-id').value = retId;
                document.getElementById('override-modal').classList.add('active');
            });
        });
    }

    // Populate Route Selection Filter
    function populateRouteFilter(routes) {
        const select = document.getElementById('route-filter-select');
        select.innerHTML = '<option value="ALL">All Vehicle Routes</option>';

        routes.forEach(r => {
            const opt = document.createElement('option');
            opt.value = r.vehicle_id;
            opt.innerText = `${r.vehicle_id} — ${r.driver_name} (${r.stops.length} stops, ${r.total_distance_km} km)`;
            select.appendChild(opt);
        });
    }

    // Render Timeline Sequence Panel
    function renderTimelineSequence(routes, selectedVehId = "ALL") {
        const container = document.getElementById('route-timeline-container');
        container.innerHTML = '';

        const filterRoutes = selectedVehId === "ALL" ? routes : routes.filter(r => r.vehicle_id === selectedVehId);

        if (!filterRoutes || filterRoutes.length === 0) {
            container.innerHTML = '<p class="text-muted">No route sequences available.</p>';
            return;
        }

        filterRoutes.forEach(r => {
            const rDiv = document.createElement('div');
            rDiv.style.marginBottom = '1.5rem';
            
            let stopsHtml = '';
            r.stops.forEach((s, idx) => {
                const isRet = s.stop_type === 'RETURN';
                const icon = isRet ? 'fa-arrow-left-long orange-text' : 'fa-box-open blue-text';
                const typeLabel = isRet ? '<span class="badge badge-warning">RETURN PICKUP</span>' : '<span class="badge badge-success">DELIVERY</span>';
                
                stopsHtml += `
                    <div class="timeline-item ${isRet ? 'return' : ''}">
                        <div class="stop-header">
                            <span><i class="fa-solid ${icon}"></i> Stop ${idx}: ${s.stop_id} (${s.customer_id})</span>
                            <span>${s.arrival_time} - ${s.departure_time}</span>
                        </div>
                        <div>${typeLabel} <strong>${s.location_name}</strong></div>
                        <div style="font-size:0.75rem; color:var(--text-muted); margin-top:0.2rem;">
                            Load Vol: ${s.cumulative_volume} m³ | Wt: ${s.cumulative_weight} kg | Leg Dist: ${s.distance_from_prev_km} km
                            ${s.is_late ? '<span class="red-text"> (LATE)</span>' : ''}
                        </div>
                    </div>
                `;
            });

            rDiv.innerHTML = `
                <div style="font-weight:700; margin-bottom:0.5rem; color:var(--primary); display:flex; justify-between; align-items:center;">
                    <span>Vehicle ${r.vehicle_id} (${r.driver_name})</span>
                    <span class="badge badge-secondary">${r.total_distance_km} km</span>
                </div>
                ${stopsHtml}
            `;
            container.appendChild(rDiv);
        });
    }

    // Render Map Routes on Leaflet
    function renderMapRoutes() {
        if (!leafletMap || !currentPlanData) return;

        // Clear existing map layers
        mapLayers.forEach(l => leafletMap.removeLayer(l));
        mapLayers = [];

        const selectedVehId = document.getElementById('route-filter-select').value;
        const routes = currentPlanData.vehicle_routes;
        const filterRoutes = selectedVehId === "ALL" ? routes : routes.filter(r => r.vehicle_id === selectedVehId);

        const bounds = [];
        const DEPOT_COORDS = [40.7306, -73.9352];

        // Depot Marker
        const depotIcon = L.divIcon({
            html: '<div style="background:#ef4444; color:#fff; width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:bold; border:2px solid #fff;"><i class="fa-solid fa-warehouse"></i></div>',
            className: 'depot-marker',
            iconSize: [28, 28]
        });
        const dMarker = L.marker(DEPOT_COORDS, { icon: depotIcon }).addTo(leafletMap)
            .bindPopup('<b>Depot Central Hub</b><br>NYC Central Logistics Yard');
        mapLayers.push(dMarker);
        bounds.push(DEPOT_COORDS);

        filterRoutes.forEach(r => {
            const color = vehicleColors[r.vehicle_id] || vehicleColors.DEFAULT;
            const latlngs = [DEPOT_COORDS];

            r.stops.forEach((s, idx) => {
                const pt = [s.latitude, s.longitude];
                latlngs.push(pt);
                bounds.push(pt);

                const isRet = s.stop_type === 'RETURN';
                const bg = isRet ? '#f59e0b' : color;
                const iconContent = isRet ? '<i class="fa-solid fa-rotate-left"></i>' : (idx);

                const mIcon = L.divIcon({
                    html: `<div style="background:${bg}; color:#fff; width:24px; height:24px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:10px; font-weight:bold; border:2px solid #fff;">${iconContent}</div>`,
                    className: 'stop-marker',
                    iconSize: [24, 24]
                });

                const popupHtml = `
                    <div style="font-family:sans-serif; color:#0f172a;">
                        <h4 style="margin:0 0 4px 0;">${s.stop_type}: ${s.stop_id}</h4>
                        <b>Customer:</b> ${s.customer_id}<br>
                        <b>Location:</b> ${s.location_name}<br>
                        <b>Eta:</b> ${s.arrival_time} - ${s.departure_time}<br>
                        <b>Window:</b> ${s.time_window_start} - ${s.time_window_end}<br>
                        <b>Payload:</b> ${s.cumulative_volume} m³ / ${s.cumulative_weight} kg
                    </div>
                `;

                const marker = L.marker(pt, { icon: mIcon }).addTo(leafletMap).bindPopup(popupHtml);
                mapLayers.push(marker);
            });

            latlngs.push(DEPOT_COORDS);

            const polyline = L.polyline(latlngs, {
                color: color,
                weight: 4,
                opacity: 0.8,
                dashArray: r.vehicle_id === 'V05' ? '5, 10' : null
            }).addTo(leafletMap);
            mapLayers.push(polyline);
        });

        if (bounds.length > 1) {
            leafletMap.fitBounds(bounds, { padding: [30, 30] });
        }
    }

    // Render Overrides Audit Table
    function renderOverridesTable(overrides) {
        const tbody = document.getElementById('overrides-tbody');
        tbody.innerHTML = '';

        if (!overrides || overrides.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No dispatcher overrides logged yet.</td></tr>';
            return;
        }

        overrides.forEach(o => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${o.override_id}</strong></td>
                <td>${o.dispatcher_name}</td>
                <td>${o.dispatcher_role}</td>
                <td><span class="badge badge-warning">${o.return_id}</span></td>
                <td>${o.target_vehicle_id}</td>
                <td><span class="badge badge-danger">${o.constraint_overridden}</span></td>
                <td>${o.reason}</td>
                <td><small>${o.timestamp || 'Just now'}</small></td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Run Automated Edge Case Tests
    async function runEdgeCaseTests() {
        const btn = document.getElementById('run-tests-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Running Suite...';

        try {
            const res = await fetch(`${API_BASE}/api/tests/run`);
            const data = await res.json();

            const container = document.getElementById('test-results-container');
            container.innerHTML = '';

            data.tests.forEach((t, i) => {
                const card = document.createElement('div');
                card.className = 'test-card glass';
                const statusBadge = t.status === 'PASSED' ? 
                    '<span class="badge badge-success"><i class="fa-solid fa-check"></i> PASSED</span>' : 
                    '<span class="badge badge-danger"><i class="fa-solid fa-xmark"></i> FAILED</span>';

                card.innerHTML = `
                    <div class="test-header">
                        <h4>${t.test_name}</h4>
                        ${statusBadge}
                    </div>
                    <p style="font-size:0.85rem; color:var(--text-muted);">${t.details}</p>
                `;
                container.appendChild(card);
            });

            alert(data.summary);
        } catch (err) {
            console.error("Error running edge tests:", err);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-vial"></i> Run 5 Edge Case Tests';
        }
    }

    // Handle Authorised Override Submission
    document.getElementById('override-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            dispatcher_name: document.getElementById('ovr-dispatcher-name').value,
            dispatcher_role: document.getElementById('ovr-dispatcher-role').value,
            return_id: document.getElementById('ovr-return-id').value,
            target_vehicle_id: document.getElementById('ovr-vehicle-id').value,
            constraint_overridden: document.getElementById('ovr-constraint-type').value,
            reason: document.getElementById('ovr-reason').value
        };

        try {
            const res = await fetch(`${API_BASE}/api/override/apply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();

            document.getElementById('override-modal').classList.remove('active');
            alert(`Override ${data.audit_record.override_id} applied successfully! Routes recalculated.`);

            await runPlanner();
        } catch (err) {
            console.error("Error applying override:", err);
            alert("Failed to apply override.");
        }
    });

    // Event Listeners
    document.getElementById('run-planner-btn').addEventListener('click', runPlanner);
    document.getElementById('refresh-comparison-btn').addEventListener('click', runComparativeExperiment);
    document.getElementById('route-filter-select').addEventListener('change', (e) => {
        if (currentPlanData) {
            renderTimelineSequence(currentPlanData.vehicle_routes, e.target.value);
            renderMapRoutes();
        }
    });

    document.getElementById('export-csv-btn').addEventListener('click', () => {
        const obj = document.getElementById('objective-select').value;
        window.location.href = `${API_BASE}/api/export/csv?objective=${obj}`;
    });

    document.getElementById('open-override-modal-btn').addEventListener('click', () => {
        document.getElementById('override-modal').classList.add('active');
    });

    document.querySelectorAll('.close-modal').forEach(b => {
        b.addEventListener('click', () => {
            document.getElementById('override-modal').classList.remove('active');
        });
    });

    document.getElementById('run-tests-btn').addEventListener('click', runEdgeCaseTests);
});
