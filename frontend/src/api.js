const DEFAULT_API_BASE = 'http://127.0.0.1:8000';

function getApiBase() {
  const params = new URLSearchParams(window.location.search);
  const apiBase = params.get('apiBase');

  if (apiBase) {
    return apiBase.replace(/\/$/, '');
  }

  if (window.__AIMONITOR_API_BASE__) {
    return String(window.__AIMONITOR_API_BASE__).replace(/\/$/, '');
  }

  return DEFAULT_API_BASE;
}

const API_BASE = getApiBase();

async function api(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    throw new Error(`API request failed: ${res.status} ${res.statusText}`);
  }
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

// Settings APIs
export async function getSettings() {
  return api('/settings');
}

export async function saveSettings(model) {
  return api('/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
}
