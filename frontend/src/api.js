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
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (e) {
      // Ignore JSON parse errors for non-JSON backend errors.
    }
    throw new Error(detail);
  }
  return res.json();
}

// Session APIs
export async function startSession(task, durationMinutes, checkIntervalSeconds, tags = [], strictMode = false, triggerThreshold = 1) {
  return api('/session/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      task,
      duration_minutes: durationMinutes,
      check_interval_seconds: checkIntervalSeconds,
      trigger_threshold: triggerThreshold,
      tags,
      strict_mode: strictMode,
    }),
  });
}

export async function stopSession(sessionId, reason, stopMinutes, tags = []) {
  return api('/session/stop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, reason, stop_minutes: stopMinutes, tags }),
  });
}

export async function getStatus() {
  return api('/session/status');
}

// Schedule APIs
export async function getSchedules() {
  return api('/schedule/list');
}

export async function addSchedule(task, date, startTime, endTime, checkIntervalSeconds, tags = [], strictMode = false, triggerThreshold = 1) {
  return api('/schedule/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      task,
      date,
      start_time: startTime,
      end_time: endTime,
      check_interval_seconds: checkIntervalSeconds,
      trigger_threshold: triggerThreshold,
      tags,
      strict_mode: strictMode,
    }),
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

export async function getDailyReport(date) {
  const suffix = date ? `?date=${encodeURIComponent(date)}` : '';
  return api(`/report/daily${suffix}`);
}

export async function saveDailyNotes(date, todaySummary, tomorrowPlan) {
  return api('/report/daily-notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date, today_summary: todaySummary, tomorrow_plan: tomorrowPlan }),
  });
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

export async function saveSettings(payload) {
  return api('/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(typeof payload === 'string' ? { model: payload } : payload),
  });
}

export async function getAiStatus() {
  return api('/ai/status');
}

// Dataset APIs
export async function captureDatasetSample(label = 'unlabeled', tags = undefined) {
  return api('/dataset/capture', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label, ...(tags ? { tags } : {}) }),
  });
}

export async function getDatasetSamples({ label = '', reviewed = '', limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (label) params.set('label', label);
  if (reviewed !== '') params.set('reviewed', reviewed ? 'true' : 'false');
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  return api(`/dataset/samples?${params.toString()}`);
}

export async function updateDatasetSample(sampleId, payload) {
  return api(`/dataset/samples/${encodeURIComponent(sampleId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function deleteDatasetSample(sampleId) {
  return api(`/dataset/samples/${encodeURIComponent(sampleId)}`, { method: 'DELETE' });
}

export async function exportDataset() {
  return api('/dataset/export', { method: 'POST' });
}

export async function openDatasetFolder(sampleId) {
  const suffix = sampleId ? `?sample_id=${encodeURIComponent(sampleId)}` : '';
  return api(`/dataset/open-folder${suffix}`, { method: 'POST' });
}

export function getDatasetImageUrl(sample) {
  return `${API_BASE}${sample.screenshot_url}`;
}

export function getGuardianImageUrl(status) {
  if (!status?.latest_screenshot_url) return '';
  return `${API_BASE}${status.latest_screenshot_url}?t=${encodeURIComponent(status.last_checked_at || '')}`;
}
