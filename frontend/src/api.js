// Dynamically determine backend port
// In Electron, port.json is written by main.js before page loads
// In dev mode, fallback to 8899
let API_BASE = 'http://127.0.0.1:8899';

async function initPort() {
  try {
    const res = await fetch('./port.json');
    if (res.ok) {
      const data = await res.json();
      API_BASE = `http://127.0.0.1:${data.port}`;
    }
  } catch (e) {
    // Use default
  }
}

// Initialize on load
const portReady = initPort();

async function api(path, options) {
  await portReady;
  const res = await fetch(`${API_BASE}${path}`, options);
  return res.json();
}

// Session APIs
export async function startSession(task, durationMinutes, checkIntervalSeconds) {
  return api('/session/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task, duration_minutes: durationMinutes, check_interval_seconds: checkIntervalSeconds }),
  });
}

export async function stopSession(sessionId) {
  return api('/session/stop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function getStatus() {
  return api('/session/status');
}

// Schedule APIs
export async function getSchedules() {
  return api('/schedule/list');
}

export async function addSchedule(task, date, startTime, durationMinutes, checkIntervalSeconds) {
  return api('/schedule/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task, date, start_time: startTime, duration_minutes: durationMinutes, check_interval_seconds: checkIntervalSeconds }),
  });
}

export async function deleteSchedule(scheduleId) {
  return api('/schedule/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ schedule_id: scheduleId }),
  });
}

// Analytics APIs
export async function getAnalytics() {
  return api('/analytics/summary');
}

// Quiz APIs
export async function getWrongAnswers() {
  return api('/quiz/wrong-answers');
}


// Test trigger
export async function testBlock() {
  return api('/session/test-block', { method: 'POST' });
}
