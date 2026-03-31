const POLLING_INTERVAL = 1000;
let trendChart = null;

// DOM Elements
const elCount = document.getElementById('crowd-count');
const elBadge = document.getElementById('density-badge');
const elDoorState = document.getElementById('door-state-text');
const elAlert = document.getElementById('alert-banner');
const elConnStatus = document.getElementById('connection-status');
const elLiveDot = document.getElementById('live-dot');
const ctx = document.getElementById('trendGraph').getContext('2d');

// Initialize Chart.js safely
function initChart() {
    trendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Crowd Count',
                data: [],
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                borderWidth: 2,
                pointRadius: 1,
                pointBackgroundColor: '#3b82f6',
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 500, // smooth transitions
                easing: 'linear'
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8', stepSize: 1 }
                },
                x: {
                    grid: { display: false },
                    ticks: { 
                        color: '#94a3b8', 
                        maxTicksLimit: 8,
                        maxRotation: 0
                    }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(15, 17, 21, 0.9)',
                    titleColor: '#f8fafc',
                    bodyColor: '#f8fafc',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1
                }
            }
        }
    });
}

function updateConnectionStatus(isConnected) {
    if (isConnected) {
        elConnStatus.textContent = '● Live System Connected';
        elConnStatus.style.color = 'var(--success)';
        elConnStatus.style.background = 'rgba(16, 185, 129, 0.1)';
        elLiveDot.classList.remove('offline');
    } else {
        elConnStatus.textContent = '○ Backend Disconnected';
        elConnStatus.style.color = 'var(--danger)';
        elConnStatus.style.background = 'rgba(239, 68, 68, 0.1)';
        elLiveDot.classList.add('offline');
    }
}

async function fetchCrowdData() {
    try {
        const response = await fetch('/crowd_data');
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        
        updateConnectionStatus(true);
        
        // Update Stats cleanly
        elCount.textContent = data.people_count;
        elBadge.textContent = data.status_text;
        elBadge.className = 'status-badge ' + data.status_color;
        
        elDoorState.textContent = data.door_state;
        elDoorState.className = data.door_state === 'CLOSE' ? 'status-closed' : 'status-open';
        
        // Alert Handling
        if (data.status_color === 'red') {
            elAlert.style.display = 'flex';
        } else {
            elAlert.style.display = 'none';
        }
        
    } catch (error) {
        // Reduce log spam in console if disconnected server
        updateConnectionStatus(false);
    }
}

async function fetchCrowdHistory() {
    try {
        const response = await fetch('/crowd_history');
        if (!response.ok) return;
        const data = await response.json();
        
        if (trendChart && data.length > 0) {
            trendChart.data.labels = data.map(d => d.time);
            trendChart.data.datasets[0].data = data.map(d => d.count);
            // Dynamic threshold color update on chart if needed
            trendChart.update('none'); // Update without full rigid animation to prevent popping
        }
    } catch (error) {
        // Ignore
    }
}

// Hardware Controls
async function setDoorState(command) {
    try {
        const response = await fetch('/door_control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command })
        });
        const data = await response.json();
        
        if (data.status === 'success') {
             elDoorState.textContent = data.door_state;
             elDoorState.className = data.door_state === 'CLOSE' ? 'status-closed' : 'status-open';
             
             // Trigger a manual data fetch to sync UI faster
             fetchCrowdData();
        }
    } catch (error) {
        console.error('Door control failed.', error);
        alert("Failed to communicate with Door Control endpoint.");
    }
}

// Lifecycle Initialization
window.addEventListener('DOMContentLoaded', () => {
    initChart();
    
    // Polling schedules
    setInterval(fetchCrowdData, POLLING_INTERVAL);
    setInterval(fetchCrowdHistory, POLLING_INTERVAL * 2); 
    
    // Immediate initial fetches
    fetchCrowdData();
    fetchCrowdHistory();
});
