import { useState, useEffect, useRef } from 'react'
import {
  startSession, stopSession, getStatus,
  getSchedules, addSchedule, deleteSchedule,
  getDailyReport, testBlock,
  getSettings, saveSettings, getAiStatus
} from './api'

function todayString() {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const IDLE_STATUS_POLL_MS = 15000
const ACTIVE_STATUS_POLL_MS = 30000

function App() {
  const [tab, setTab] = useState('session')
  const [task, setTask] = useState('')
  const [duration, setDuration] = useState('30')
  const [interval, setInterval_] = useState('30')
  const [status, setStatus] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [remainingSeconds, setRemainingSeconds] = useState(0)
  const [formError, setFormError] = useState('')
  const taskRef = useRef(null)
  const sessionEndsAtRef = useRef(0)
  const completionCheckedRef = useRef(false)

  const [aiStatus, setAiStatus] = useState(null)
  const [schedules, setSchedules] = useState([])
  const [schedTask, setSchedTask] = useState('')
  const [schedDate, setSchedDate] = useState(todayString())
  const [schedStart, setSchedStart] = useState('')
  const [schedEnd, setSchedEnd] = useState('')
  const [scheduleError, setScheduleError] = useState('')

  const [reportDate, setReportDate] = useState(todayString())
  const [dailyReport, setDailyReport] = useState(null)
  const [settings, setSettings] = useState(null)
  const [modelOptions, setModelOptions] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  const [settingsStatus, setSettingsStatus] = useState('')

  const applySessionStatus = (s) => {
    setStatus(s)
    setSessionId(s.session_id || null)
    const active = Boolean(s.active)
    setIsRunning(active)
    if (active && typeof s.remaining_seconds === 'number') {
      sessionEndsAtRef.current = Date.now() + s.remaining_seconds * 1000
      setRemainingSeconds(s.remaining_seconds)
      completionCheckedRef.current = false
    }
  }

  useEffect(() => {
    const poll = async () => {
      try {
        applySessionStatus(await getStatus())
      } catch (e) {
        // Backend may still be starting.
      }
    }
    poll()
    const intervalMs = isRunning ? ACTIVE_STATUS_POLL_MS : IDLE_STATUS_POLL_MS
    const id = window.setInterval(poll, intervalMs)
    return () => window.clearInterval(id)
  }, [isRunning])

  useEffect(() => {
    if (!isRunning) {
      completionCheckedRef.current = false
      setRemainingSeconds(0)
      return
    }

    const tick = () => {
      const left = Math.max(0, Math.ceil((sessionEndsAtRef.current - Date.now()) / 1000))
      setRemainingSeconds(left)
      if (left <= 0 && !completionCheckedRef.current) {
        completionCheckedRef.current = true
        getStatus()
          .then((s) => applySessionStatus(s))
          .catch(() => {})
      }
    }

    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [isRunning])

  useEffect(() => {
    const pollAi = async () => {
      try {
        setAiStatus(await getAiStatus())
      } catch (e) {
        setAiStatus({ state: 'error', message: '无法连接后端。' })
      }
    }
    pollAi()
    const id = window.setInterval(pollAi, 10000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    if (tab === 'schedule') {
      refreshSchedules()
      const id = window.setInterval(refreshSchedules, 5000)
      return () => window.clearInterval(id)
    }
  }, [tab])

  useEffect(() => {
    if (tab === 'report') {
      refreshReport()
    }
  }, [tab, reportDate])

  useEffect(() => {
    if (tab === 'settings') {
      getSettings()
        .then((d) => {
          setSettings(d.settings)
          setModelOptions(d.model_options || [])
          setSelectedModel(d.settings?.model || '')
          setSettingsStatus('')
        })
        .catch(() => setSettingsStatus('设置读取失败'))
    }
  }, [tab])

  const refreshSchedules = async () => {
    try {
      const d = await getSchedules()
      setSchedules(d.schedules || [])
    } catch (e) {
      // Keep the last loaded list.
    }
  }

  const refreshReport = async () => {
    try {
      setDailyReport(await getDailyReport(reportDate))
    } catch (e) {
      setDailyReport(null)
    }
  }

  const parsePositiveInt = (value, min) => {
    if (value === '') return null
    const n = Number(value)
    return Number.isInteger(n) && n >= min ? n : null
  }

  const handleStart = async () => {
    setFormError('')
    const durationMinutes = parsePositiveInt(duration, 1)
    const checkIntervalSeconds = parsePositiveInt(interval, 5)

    if (!task.trim()) {
      setFormError('请输入当前要完成的任务。')
      taskRef.current?.focus()
      return
    }
    if (durationMinutes === null) {
      setFormError('工作时长需要是 1 分钟以上的整数。')
      return
    }
    if (checkIntervalSeconds === null) {
      setFormError('检查间隔需要是 5 秒以上的整数。')
      return
    }

    try {
      const res = await startSession(task.trim(), durationMinutes, checkIntervalSeconds)
      setSessionId(res.session_id)
      setIsRunning(true)
      sessionEndsAtRef.current = Date.now() + durationMinutes * 60 * 1000
      setRemainingSeconds(durationMinutes * 60)
      completionCheckedRef.current = false
    } catch (e) {
      setFormError(e.message || '无法启动监督。')
    }
  }

  const handleStop = async () => {
    await stopSession(sessionId)
    setIsRunning(false)
    setRemainingSeconds(0)
    sessionEndsAtRef.current = 0
    await refreshReport()
  }

  const handleAddSchedule = async () => {
    setScheduleError('')
    if (!schedTask.trim() || !schedDate || !schedStart || !schedEnd) {
      setScheduleError('请填写任务、日期、开始时间和结束时间。')
      return
    }

    try {
      await addSchedule(schedTask.trim(), schedDate, schedStart, schedEnd, 30)
      await refreshSchedules()
      setSchedTask('')
      setSchedStart('')
      setSchedEnd('')
    } catch (e) {
      setScheduleError(e.message || '无法添加日程。')
    }
  }

  const handleDeleteSchedule = async (id) => {
    await deleteSchedule(id)
    await refreshSchedules()
  }

  const formatTime = (seconds) => {
    if (!seconds && seconds !== 0) return '--:--'
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }

  const getStatusLabel = () => {
    if (!status || !status.active) return '待机中'
    if (!status.latest_judgement) return '等待首次检查'
    if (status.latest_judgement.judgement_status === 'api_error') return 'AI 未连接'
    return status.latest_judgement.on_task ? '专注中' : '疑似分心'
  }

  const handleSaveSettings = async () => {
    if (!selectedModel) return
    setSettingsStatus('保存中...')
    try {
      const res = await saveSettings(selectedModel)
      setSettings(res.settings)
      setSettingsStatus('已保存，下一次 AI 判定生效。')
      setAiStatus(await getAiStatus())
    } catch (e) {
      setSettingsStatus(e.message || '保存失败')
    }
  }

  const aiClass = aiStatus?.state === 'connected' ? 'ok' : aiStatus?.state === 'unknown' ? 'warn' : 'bad'
  const statusText = status?.latest_judgement?.judgement_status === 'api_error'
    ? status.latest_judgement.reason
    : status?.latest_judgement?.reason || '--'

  const statusName = {
    completed: '已完成',
    stopped: '手动停止',
    replaced: '被新任务替换',
    missed: '已错过',
    skipped_conflict: '冲突跳过',
    break: '休息',
    day_paused: '暂停今日',
  }

  return (
    <div className="container">
      <header>
        <h1>FocusGuard Agent</h1>
        <p className="subtitle">AI 工作监督助手</p>
      </header>

      <nav className="tabs">
        <button className={tab === 'session' ? 'tab active' : 'tab'} onClick={() => setTab('session')}>Session</button>
        <button className={tab === 'schedule' ? 'tab active' : 'tab'} onClick={() => setTab('schedule')}>Schedule</button>
        <button className={tab === 'report' ? 'tab active' : 'tab'} onClick={() => setTab('report')}>Report</button>
        <button className={tab === 'settings' ? 'tab active' : 'tab'} onClick={() => setTab('settings')}>Settings</button>
      </nav>

      <div className={`ai-banner ${aiClass}`}>
        <span>AI 状态：{aiStatus?.message || '读取中...'}</span>
        {aiStatus?.model && <span className="ai-model">{aiStatus.model}</span>}
      </div>

      {tab === 'session' && (
        <>
          {!isRunning ? (
            <section className="controls">
              <div className="input-group">
                <label>当前任务</label>
                <input ref={taskRef} type="text" value={task} onChange={(e) => setTask(e.target.value)}
                  placeholder="例如：开发产品 / 写报告 / 准备面谈" />
              </div>
              <div className="input-row">
                <div className="input-group">
                  <label>工作时长（分钟）</label>
                  <input type="number" value={duration} onChange={(e) => setDuration(e.target.value)} min="1" step="1" />
                </div>
                <div className="input-group">
                  <label>检查间隔（秒）</label>
                  <input type="number" value={interval} onChange={(e) => setInterval_(e.target.value)} min="5" step="1" />
                </div>
              </div>
              {formError && <p className="form-error">{formError}</p>}
              <button className="btn-start" onClick={handleStart}>开始监督</button>
              <button className="btn-test" onClick={() => testBlock()}>测试遮挡窗口</button>
            </section>
          ) : (
            <section className="status-panel">
              <div className="status-header">
                <div className="status-badge">{getStatusLabel()}</div>
                <button className="btn-stop" onClick={handleStop}>停止</button>
              </div>
              <div className="status-info">
                <div className="info-item"><span className="label">任务</span><span className="value">{status?.task || task}</span></div>
                <div className="info-item"><span className="label">来源</span><span className="value">{status?.source === 'schedule' ? 'Schedule' : '手动'}</span></div>
                <div className="info-item"><span className="label">剩余时间</span><span className="value timer">{formatTime(remainingSeconds)}</span></div>
                <div className="info-item"><span className="label">当前活动</span><span className="value">{status?.latest_judgement?.current_activity || '等待检查...'}</span></div>
                <div className="info-item"><span className="label">AI 理由</span><span className="value">{statusText}</span></div>
                <div className="info-item"><span className="label">连续分心</span><span className={`value ${status?.off_task_streak >= 2 ? 'danger' : ''}`}>{status?.off_task_streak ?? 0}</span></div>
              </div>
            </section>
          )}

          {status?.logs && status.logs.length > 0 && (
            <section className="logs">
              <h2>最近检查</h2>
              <div className="log-list">
                {[...status.logs].reverse().map((log, i) => (
                  <div key={i} className={`log-item ${log.judgement_status === 'api_error' ? 'api-error' : log.on_task ? 'on-task' : 'off-task'}`}>
                    <div className="log-time">{new Date(log.timestamp).toLocaleTimeString()}</div>
                    <div className="log-details">
                      <span className="log-activity">{log.current_activity}</span>
                      <span className="log-reason">{log.reason}</span>
                      <span className="log-model">{log.judgement_status || 'ok'} · {log.model || '--'}</span>
                    </div>
                    <div className="log-confidence">{Math.round((log.confidence || 0) * 100)}%</div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {tab === 'schedule' && (
        <section className="schedule-panel">
          <h2>自动日程</h2>
          <div className="schedule-form">
            <div className="input-group">
              <label>任务</label>
              <input type="text" value={schedTask} onChange={(e) => setSchedTask(e.target.value)}
                placeholder="例如：产品开发" />
            </div>
            <div className="input-row">
              <div className="input-group">
                <label>日期</label>
                <input type="date" value={schedDate} onChange={(e) => setSchedDate(e.target.value)} />
              </div>
              <div className="input-group">
                <label>开始</label>
                <input type="time" value={schedStart} onChange={(e) => setSchedStart(e.target.value)} />
              </div>
              <div className="input-group">
                <label>结束</label>
                <input type="time" value={schedEnd} onChange={(e) => setSchedEnd(e.target.value)} />
              </div>
            </div>
            {scheduleError && <p className="form-error">{scheduleError}</p>}
            <button className="btn-start" onClick={handleAddSchedule}>添加日程</button>
          </div>

          <div className="schedule-list">
            {schedules.length === 0 && <p className="empty-msg">暂无日程</p>}
            {schedules.map((s) => (
              <div key={s.id} className="schedule-item">
                <div className="schedule-info">
                  <span className="schedule-task">{s.task}</span>
                  <span className="schedule-time">{s.date} {s.start_time} - {s.end_time} · {s.status === 'in_progress' ? '进行中' : '未开始'}</span>
                </div>
                <div className="schedule-actions">
                  <button className="btn-small btn-red" onClick={() => handleDeleteSchedule(s.id)}>×</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {tab === 'report' && (
        <section className="analytics-panel">
          <div className="section-title-row">
            <h2>每日报告</h2>
            <input type="date" value={reportDate} onChange={(e) => setReportDate(e.target.value)} />
          </div>

          {dailyReport ? (
            <>
              <div className="stats-grid">
                <div className="stat-card"><div className="stat-value">{dailyReport.total_blocks}</div><div className="stat-label">Block</div></div>
                <div className="stat-card good"><div className="stat-value">{dailyReport.total_focus_minutes}</div><div className="stat-label">专注分钟</div></div>
                <div className="stat-card"><div className="stat-value">{dailyReport.completed_blocks}</div><div className="stat-label">完成</div></div>
                <div className="stat-card bad"><div className="stat-value">{dailyReport.blocks?.reduce((sum, b) => sum + (b.distracted_checks || 0), 0) || 0}</div><div className="stat-label">分心次数</div></div>
              </div>

              <div className="session-history">
                {(dailyReport.blocks || []).length === 0 && <p className="empty-msg">这一天还没有记录</p>}
                {(dailyReport.blocks || []).map((b) => (
                  <div key={b.session_id} className="history-item">
                    <div className="history-task">{b.task}</div>
                    <div className="history-meta">
                      <span>{b.source === 'schedule' ? 'Schedule' : '手动'} · {statusName[b.status] || b.status}</span>
                      <span>{b.focus_minutes} 分钟专注</span>
                    </div>
                    <div className="history-meta">
                      <span>{b.planned_start ? new Date(b.planned_start).toLocaleTimeString() : '--'} - {b.planned_end ? new Date(b.planned_end).toLocaleTimeString() : '--'}</span>
                      <span>分心 {b.distracted_checks || 0} · AI 错误 {b.api_error_checks || 0}</span>
                    </div>
                    <div className="history-bar">
                      <div className="history-bar-fill" style={{ width: `${b.total_checks > 0 ? (b.focused_checks / b.total_checks * 100) : 0}%` }}></div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="empty-msg">报告读取失败</p>
          )}
        </section>
      )}

      {tab === 'settings' && (
        <section className="settings-panel">
          <h2>设置</h2>

          <div className={`ai-banner ${aiClass}`}>
            <span>{aiStatus?.message || 'AI 状态读取中...'}</span>
            {aiStatus?.last_error_at && <span className="ai-model">最近错误：{new Date(aiStatus.last_error_at).toLocaleString()}</span>}
          </div>

          <div className="input-group">
            <label>AI 模型</label>
            <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
              {modelOptions.map((model) => (
                <option key={model.id} value={model.id}>{model.label}</option>
              ))}
            </select>
          </div>

          <div className="model-list">
            {modelOptions.map((model) => (
              <button
                key={model.id}
                type="button"
                className={selectedModel === model.id ? 'model-option selected' : 'model-option'}
                onClick={() => setSelectedModel(model.id)}
              >
                <span className="model-name">{model.label}</span>
                <span className="model-id">{model.id}</span>
                <span className="model-description">{model.description}</span>
              </button>
            ))}
          </div>

          <button className="btn-start" onClick={handleSaveSettings}>保存设置</button>
          {settingsStatus && <p className="settings-status">{settingsStatus}</p>}
          {settings?.model && <p className="settings-current">当前模型：{settings.model}</p>}
        </section>
      )}
    </div>
  )
}

export default App
