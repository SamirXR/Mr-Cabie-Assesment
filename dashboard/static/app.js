document.addEventListener('DOMContentLoaded', () => {
    // Theme Management (Monochrome Light / Dark)
    const themeToggleBtn = document.getElementById('btn-theme-toggle');
    const themeIcon = document.getElementById('theme-icon');
    
    const savedTheme = localStorage.getItem('cabie_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    themeToggleBtn.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('cabie_theme', newTheme);
        updateThemeIcon(newTheme);
        addLog(`Switched system visual theme to ${newTheme.toUpperCase()} mode`, 'info');
    });

    function updateThemeIcon(theme) {
        if (theme === 'dark') {
            themeIcon.className = 'fa-solid fa-sun';
        } else {
            themeIcon.className = 'fa-solid fa-moon';
        }
    }

    // State Variables
    let ridesData = [];

    // DOM Elements
    const ridesTbody = document.getElementById('rides-tbody');
    const simTimeInput = document.getElementById('sim-time');
    const btnUseNow = document.getElementById('btn-use-now');
    const btnRunScan = document.getElementById('btn-run-scan');
    const btnReset = document.getElementById('btn-reset');
    const btnRefresh = document.getElementById('btn-refresh');
    const btnListenTTS = document.getElementById('btn-listen-tts');
    const logContainer = document.getElementById('log-container');

    const statTotal = document.getElementById('stat-total');
    const statPending = document.getElementById('stat-pending');
    const statSent = document.getElementById('stat-sent');
    const statUnanswered = document.getElementById('stat-unanswered');

    const sourceBadge = document.getElementById('source-badge');
    const twilioBadge = document.getElementById('twilio-badge');

    // Modal Elements
    const addRideModal = document.getElementById('add-ride-modal');
    const btnAddRideModal = document.getElementById('btn-add-ride-modal');
    const closeModal = document.getElementById('close-modal');
    const btnCancelModal = document.getElementById('btn-cancel-modal');
    const addRideForm = document.getElementById('add-ride-form');

    // Set initial reference time to current local time HH:MM
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    simTimeInput.value = `${hours}:${minutes}`;

    // Initialize Config and Rides
    fetchConfig();
    fetchRides();

    // Event Listeners
    btnUseNow.addEventListener('click', () => {
        const currentNow = new Date();
        const h = String(currentNow.getHours()).padStart(2, '0');
        const m = String(currentNow.getMinutes()).padStart(2, '0');
        simTimeInput.value = `${h}:${m}`;
        addLog(`Reference time synchronized to system clock: ${h}:${m}`, 'info');
        renderRides();
    });

    simTimeInput.addEventListener('change', () => {
        addLog(`Reference time updated to: ${simTimeInput.value}`, 'info');
        renderRides();
    });

    btnRunScan.addEventListener('click', runScan);
    btnReset.addEventListener('click', resetData);
    btnRefresh.addEventListener('click', fetchRides);
    btnListenTTS.addEventListener('click', playTTSPreview);

    // Modal Listeners
    btnAddRideModal.addEventListener('click', () => addRideModal.classList.add('active'));
    closeModal.addEventListener('click', () => addRideModal.classList.remove('active'));
    btnCancelModal.addEventListener('click', () => addRideModal.classList.remove('active'));
    addRideForm.addEventListener('submit', handleAddRide);

    // Fetch System Configuration
    async function fetchConfig() {
        try {
            const res = await fetch('/api/config');
            if (res.ok) {
                const config = await res.json();
                sourceBadge.textContent = `Data: ${config.data_source.toUpperCase()}`;
                twilioBadge.textContent = `Voice: ${config.twilio_provider.toUpperCase()}`;
            }
        } catch (err) {
            console.error('Failed to load system config:', err);
        }
    }

    // Fetch Rides Dataset
    async function fetchRides() {
        try {
            const res = await fetch('/api/rides');
            if (res.ok) {
                ridesData = await res.json();
                renderRides();
                addLog('Fetched scheduled ride records', 'info');
            }
        } catch (err) {
            addLog('Error fetching rides dataset', 'danger');
        }
    }

    // Calculate Lead Time & Render Table
    function renderRides() {
        if (!ridesData || ridesData.length === 0) {
            ridesTbody.innerHTML = `<tr><td colspan="7" class="loading-cell">No scheduled ride records found.</td></tr>`;
            updateStats(0, 0, 0, 0);
            return;
        }

        const simTimeStr = simTimeInput.value || '09:15';
        const [simH, simM] = simTimeStr.split(':').map(Number);
        const refMinutes = simH * 60 + simM;

        let total = ridesData.length;
        let pending = 0;
        let sent = 0;
        let unanswered = 0;

        ridesTbody.innerHTML = '';

        ridesData.forEach(ride => {
            const dt = new Date(ride.scheduled_pickup_time);
            const pickupH = dt.getHours();
            const pickupM = dt.getMinutes();
            const pickupMinutes = pickupH * 60 + pickupM;

            const diffMins = pickupMinutes - refMinutes;

            let statusClass = 'status-pending';
            if (ride.status === 'Reminder Sent') {
                statusClass = 'status-sent';
                sent++;
            } else if (ride.status === 'Calling') {
                statusClass = 'status-calling';
            } else if (ride.status === 'No Answer' || ride.status === 'Failed') {
                statusClass = 'status-unanswered';
                unanswered++;
            } else {
                pending++;
            }

            // Target lead window: 25 - 35 mins away
            const inWindow = diffMins >= 25 && diffMins <= 35 && ride.status === 'Pending';
            const countdownClass = inWindow ? 'countdown-badge countdown-target' : 'countdown-badge';
            const countdownText = diffMins >= 0 ? `${diffMins} min lead` : `${Math.abs(diffMins)} min ago`;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${ride.ride_id}</strong></td>
                <td>
                    <div class="driver-info">
                        <span class="name">${ride.driver_name}</span>
                        <span class="phone">${ride.driver_phone}</span>
                    </div>
                </td>
                <td>${ride.pickup_location}</td>
                <td><span class="time-pill">${formatTime(dt)}</span></td>
                <td><span class="${countdownClass}">${countdownText}</span></td>
                <td><span class="status-tag ${statusClass}">${ride.status}</span></td>
                <td>
                    <button class="btn btn-sm btn-secondary btn-trigger-single" data-id="${ride.ride_id}">
                        <i class="fa-solid fa-phone"></i> Call
                    </button>
                </td>
            `;
            ridesTbody.appendChild(tr);
        });

        updateStats(total, pending, sent, unanswered);

        // Bind single call buttons
        document.querySelectorAll('.btn-trigger-single').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const rideId = e.currentTarget.getAttribute('data-id');
                triggerSingleCall(rideId);
            });
        });
    }

    function updateStats(total, pending, sent, unanswered) {
        statTotal.textContent = total;
        statPending.textContent = pending;
        statSent.textContent = sent;
        statUnanswered.textContent = unanswered;
    }

    // Run 30-Min Lead Scan
    async function runScan() {
        const simTimeStr = simTimeInput.value || '09:15';
        addLog(`Initiating 30-minute lead scan for reference time ${simTimeStr}...`, 'info');
        btnRunScan.disabled = true;

        try {
            const res = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reference_time: simTimeStr })
            });

            if (res.ok) {
                const data = await res.json();
                addLog(`Scan execution complete. ${data.triggered_count} outbound calls dispatched.`, 'success');
                
                if (data.calls && data.calls.length > 0) {
                    data.calls.forEach(call => {
                        addLog(`[CALL DISPATCHED] ${call.driver_name} (${call.driver_phone}) | Call SID: ${call.call_sid}`, 'success');
                    });
                } else {
                    addLog('No pending rides matched the 30-minute window criteria.', 'info');
                }
                fetchRides();
            } else {
                addLog('Scan execution failed.', 'danger');
            }
        } catch (err) {
            addLog('Network error during scan execution.', 'danger');
        } finally {
            btnRunScan.disabled = false;
        }
    }

    // Trigger Single Call
    async function triggerSingleCall(rideId) {
        addLog(`Triggering manual call dispatch for Ride ID ${rideId}...`, 'info');
        try {
            const res = await fetch(`/api/call/${rideId}`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                addLog(`[MANUAL CALL DISPATCHED] Driver: ${data.call.driver_name} | Call SID: ${data.call.call_sid}`, 'success');
                fetchRides();
            } else {
                const err = await res.json();
                addLog(`Manual call failed: ${err.detail}`, 'danger');
            }
        } catch (err) {
            addLog('Error triggering manual call', 'danger');
        }
    }

    // Reset Demo Data
    async function resetData() {
        addLog('Resetting ride statuses to Pending...', 'warning');
        try {
            const res = await fetch('/api/reset', { method: 'POST' });
            if (res.ok) {
                addLog('Dataset state reset to initial pending state.', 'success');
                fetchRides();
            }
        } catch (err) {
            addLog('Reset failed.', 'danger');
        }
    }

    // Add New Test Ride Entry
    async function handleAddRide(e) {
        e.preventDefault();
        const driver_name = document.getElementById('input-driver-name').value;
        const driver_phone = document.getElementById('input-driver-phone').value;
        const pickup_location = document.getElementById('input-pickup-location').value;
        const time_str = document.getElementById('input-pickup-time').value;

        const payload = {
            driver_name,
            driver_phone,
            pickup_location,
            time_str
        };

        try {
            const res = await fetch('/api/rides/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                const newRide = await res.json();
                addLog(`Added scheduled ride ${newRide.ride_id} for ${newRide.driver_name}`, 'success');
                addRideModal.classList.remove('active');
                addRideForm.reset();
                fetchRides();
            }
        } catch (err) {
            addLog('Failed to create scheduled ride record.', 'danger');
        }
    }

    // Browser Speech Synthesis Preview
    function playTTSPreview() {
        if ('speechSynthesis' in window) {
            const text = "Hello driver, this is an automated reminder from Cabie Fleet Management. You have a pickup scheduled in 30 minutes. Please remember to call or message your customer to confirm pickup, and head to the location on time.";
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 0.95;
            window.speechSynthesis.speak(utterance);
            addLog('Audio speech synthesis preview playback started', 'info');
        } else {
            alert('Browser Text-To-Speech is not supported in this browser environment.');
        }
    }

    // Log Feed Helper
    function addLog(msg, type = 'info') {
        const timeStr = new Date().toLocaleTimeString('en-US', { hour12: false });
        const entry = document.createElement('div');
        entry.className = `log-entry log-${type}`;
        entry.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="log-msg">${msg}</span>`;
        logContainer.prepend(entry);
    }

    function formatTime(dt) {
        return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
    }
});
