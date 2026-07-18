import { useState, useEffect, useRef } from 'react'
import {
  startSession, stopSession, getStatus,
  getSchedules, addSchedule, deleteSchedule,
  getDailyReport, testBlock,
  getSettings, saveSettings, getAiStatus,
  saveDailyNotes,
  captureDatasetSample,
  deleteDatasetSample,
  exportDataset,
  getDatasetImageUrl,
  getDatasetSamples,
  openDatasetFolder,
  updateDatasetSample
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
const COUNTDOWN_TICK_MS = 10000

function App() {
  const [tab, setTab] = useState('session')
  const [task, setTask] = useState('')
  const [tags, setTags] = useState('')
  const [sessionStrict, setSessionStrict] = useState(true)
  const [duration, setDuration] = useState('30')
  const [interval, setInterval_] = useState('300')
  const [triggerThreshold, setTriggerThreshold] = useState('1')
  const [status, setStatus] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [remainingSeconds, setRemainingSeconds] = useState(0)
  const [flowRemainingSeconds, setFlowRemainingSeconds] = useState(0)
  const [formError, setFormError] = useState('')
  const [stopReason, setStopReason] = useState('')
  const [stopMinutes, setStopMinutes] = useState('10')
  const [stopTags, setStopTags] = useState('')
  const [showStopForm, setShowStopForm] = useState(false)
  const taskRef = useRef(null)
  const sessionEndsAtRef = useRef(0)
  const flowEndsAtRef = useRef(0)
  const completionCheckedRef = useRef(false)

  const [aiStatus, setAiStatus] = useState(null)
  const [schedules, setSchedules] = useState([])
  const [schedTask, setSchedTask] = useState('')
  const [schedTags, setSchedTags] = useState('')
  const [schedStrict, setSchedStrict] = useState(true)
  const [schedInterval, setSchedInterval] = useState('300')
  const [schedTriggerThreshold, setSchedTriggerThreshold] = useState('1')
  const [schedDate, setSchedDate] = useState(todayString())
  const [schedStart, setSchedStart] = useState('')
  const [schedEnd, setSchedEnd] = useState('')
  const [scheduleError, setScheduleError] = useState('')

  const [reportDate, setReportDate] = useState(todayString())
  const [dailyReport, setDailyReport] = useState(null)
  const [todaySummary, setTodaySummary] = useState('')
  const [tomorrowPlan, setTomorrowPlan] = useState('')
  const [notesStatus, setNotesStatus] = useState('')
  const [settings, setSettings] = useState(null)
  const [modelOptions, setModelOptions] = useState([])
  const [supervisionLevelOptions, setSupervisionLevelOptions] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  const [selectedSupervisionLevel, setSelectedSupervisionLevel] = useState('task_related')
  const [nudgePrompt, setNudgePrompt] = useState('')
  const [defaultInterval, setDefaultInterval] = useState('300')
  const [defaultTriggerThreshold, setDefaultTriggerThreshold] = useState('1')
  const [whitelistText, setWhitelistText] = useState('')
  const [guardianEnabled, setGuardianEnabled] = useState(true)
  const [guardianInterval, setGuardianInterval] = useState('300')
  const [settingsStatus, setSettingsStatus] = useState('')
  const [datasetSamples, setDatasetSamples] = useState([])
  const [datasetIndex, setDatasetIndex] = useState(0)
  const [datasetLabelFilter, setDatasetLabelFilter] = useState('')
  const [datasetReviewedFilter, setDatasetReviewedFilter] = useState('')
  const [datasetActivity, setDatasetActivity] = useState('')
  const [datasetNotes, setDatasetNotes] = useState('')
  const [datasetStatus, setDatasetStatus] = useState('')

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
    if (!active && s.flow_status?.active && typeof s.flow_status.remaining_seconds === 'number') {
      flowEndsAtRef.current = Date.now() + s.flow_status.remaining_seconds * 1000
      setFlowRemainingSeconds(s.flow_status.remaining_seconds)
    } else if (!s.flow_status?.active) {
      flowEndsAtRef.current = 0
      setFlowRemainingSeconds(0)
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
    const id = window.setInterval(tick, COUNTDOWN_TICK_MS)
    return () => window.clearInterval(id)
  }, [isRunning])

  useEffect(() => {
    if (isRunning || !status?.flow_status?.active) return

    const tick = () => {
      const left = Math.max(0, Math.ceil((flowEndsAtRef.current - Date.now()) / 1000))
      setFlowRemainingSeconds(left)
      if (left <= 0) {
        getStatus()
          .then((s) => applySessionStatus(s))
          .catch(() => {})
      }
    }

    tick()
    const id = window.setInterval(tick, COUNTDOWN_TICK_MS)
    return () => window.clearInterval(id)
  }, [isRunning, status?.flow_status?.active])

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
          setSupervisionLevelOptions(d.supervision_level_options || [])
          setSelectedModel(d.settings?.model || '')
          setSelectedSupervisionLevel(d.settings?.supervision_level || 'task_related')
          setNudgePrompt(d.settings?.nudge_prompt || '')
          setDefaultInterval(String(d.settings?.default_check_interval_seconds || 300))
          setDefaultTriggerThreshold(String(d.settings?.trigger_threshold || 1))
          setWhitelistText((d.settings?.whitelist_behaviors || []).join('\n'))
          setGuardianEnabled(Boolean(d.settings?.guardian_mode_enabled ?? true))
          setGuardianInterval(String(d.settings?.guardian_check_interval_seconds || 300))
          setSettingsStatus('')
        })
        .catch(() => setSettingsStatus('设置读取失败'))
    }
  }, [tab])

  useEffect(() => {
    if (tab === 'dataset') {
      refreshDataset()
    }
  }, [tab, datasetLabelFilter, datasetReviewedFilter])

  useEffect(() => {
    const current = datasetSamples[datasetIndex]
    setDatasetActivity(current?.activity || '')
    setDatasetNotes(current?.label_notes || '')
  }, [datasetSamples, datasetIndex])

  useEffect(() => {
    if (tab !== 'dataset') return

    const onKeyDown = (e) => {
      const tag = String(e.target?.tagName || '').toLowerCase()
      const editing = tag === 'input' || tag === 'textarea' || tag === 'select'
      if (editing && !['Escape'].includes(e.key)) return
      if (e.key === '1') updateCurrentDatasetLabel('on_task')
      if (e.key === '2') updateCurrentDatasetLabel('off_task')
      if (e.key === '3') updateCurrentDatasetLabel('ambiguous')
      if (e.key.toLowerCase() === 'r') toggleCurrentReviewed()
      if (e.key.toLowerCase() === 'a') document.getElementById('dataset-activity')?.focus()
      if (e.key.toLowerCase() === 'n') document.getElementById('dataset-notes')?.focus()
      if (e.key === 'ArrowLeft') setDatasetIndex((i) => Math.max(0, i - 1))
      if (e.key === 'ArrowRight') setDatasetIndex((i) => Math.min(datasetSamples.length - 1, i + 1))
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [tab, datasetSamples, datasetIndex, datasetActivity, datasetNotes])

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
      const report = await getDailyReport(reportDate)
      setDailyReport(report)
      setTodaySummary(report.today_summary || '')
      setTomorrowPlan(report.tomorrow_plan || '')
      setNotesStatus('')
    } catch (e) {
      setDailyReport(null)
    }
  }

  const refreshDataset = async () => {
    try {
      const reviewed = datasetReviewedFilter === '' ? '' : datasetReviewedFilter === 'reviewed'
      const data = await getDatasetSamples({ label: datasetLabelFilter, reviewed })
      setDatasetSamples(data.samples || [])
      setDatasetIndex((i) => Math.min(i, Math.max(0, (data.samples || []).length - 1)))
      setDatasetStatus('')
    } catch (e) {
      setDatasetStatus(e.message || '数据集读取失败')
    }
  }

  const currentDatasetSample = datasetSamples[datasetIndex]

  const updateCurrentDatasetLabel = async (label) => {
    if (!currentDatasetSample) return
    try {
      const updated = await updateDatasetSample(currentDatasetSample.id, { distraction_label: label })
      setDatasetSamples((samples) => samples.map((s) => (s.id === updated.id ? updated : s)))
      setDatasetStatus('标签已保存')
    } catch (e) {
      setDatasetStatus(e.message || '标签保存失败')
    }
  }

  const toggleCurrentReviewed = async () => {
    if (!currentDatasetSample) return
    try {
      const updated = await updateDatasetSample(currentDatasetSample.id, { reviewed: !currentDatasetSample.reviewed })
      setDatasetSamples((samples) => samples.map((s) => (s.id === updated.id ? updated : s)))
      setDatasetStatus(updated.reviewed ? '已标记 reviewed' : '已取消 reviewed')
    } catch (e) {
      setDatasetStatus(e.message || 'reviewed 更新失败')
    }
  }

  const saveCurrentDatasetSample = async () => {
    if (!currentDatasetSample) return
    try {
      const updated = await updateDatasetSample(currentDatasetSample.id, {
        activity: datasetActivity,
        label_notes: datasetNotes,
      })
      setDatasetSamples((samples) => samples.map((s) => (s.id === updated.id ? updated : s)))
      setDatasetStatus('样本已保存')
    } catch (e) {
      setDatasetStatus(e.message || '样本保存失败')
    }
  }

  const deleteCurrentDatasetSample = async () => {
    if (!currentDatasetSample) return
    try {
      await deleteDatasetSample(currentDatasetSample.id)
      const next = datasetSamples.filter((s) => s.id !== currentDatasetSample.id)
      setDatasetSamples(next)
      setDatasetIndex((i) => Math.min(i, Math.max(0, next.length - 1)))
      setDatasetStatus('样本已删除')
    } catch (e) {
      setDatasetStatus(e.message || '删除失败')
    }
  }

  const captureDataset = async (label) => {
    try {
      const result = await captureDatasetSample(label)
      setDatasetSamples((samples) => [result.sample, ...samples])
      setDatasetIndex(0)
      setDatasetStatus(`已截图：${label}`)
    } catch (e) {
      setDatasetStatus(e.message || '截图失败')
    }
  }

  const handleDatasetExport = async () => {
    try {
      const result = await exportDataset()
      setDatasetStatus(`已导出 ${result.count} 条：${result.path}`)
    } catch (e) {
      setDatasetStatus(e.message || '导出失败')
    }
  }

  const parsePositiveInt = (value, min) => {
    if (value === '') return null
    const n = Number(value)
    return Number.isInteger(n) && n >= min ? n : null
  }

  const parseTags = (value) => value
    .replace(/，/g, ',')
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)

  const handleStart = async () => {
    setFormError('')
    const durationMinutes = parsePositiveInt(duration, 1)
    const checkIntervalSeconds = parsePositiveInt(interval, 5)
    const threshold = parsePositiveInt(triggerThreshold, 1)

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
    if (threshold === null) {
      setFormError('触发答题命中次数需要是 1 以上的整数。')
      return
    }

    try {
      const res = await startSession(
        task.trim(),
        durationMinutes,
        checkIntervalSeconds,
        parseTags(tags),
        sessionStrict,
        threshold,
      )
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
    setStopTags((status?.tags || []).join(', '))
    setShowStopForm(true)
  }

  const handleConfirmStop = async () => {
    setFormError('')
    const minutes = parsePositiveInt(stopMinutes, 1)
    if (!stopReason.trim()) {
      setFormError('请输入停止原因。')
      return
    }
    if (minutes === null) {
      setFormError('停止多久需要是 1 分钟以上的整数。')
      return
    }

    await stopSession(sessionId, stopReason.trim(), minutes, parseTags(stopTags))
    setIsRunning(false)
    setRemainingSeconds(0)
    sessionEndsAtRef.current = 0
    setShowStopForm(false)
    setStopReason('')
    setStopTags('')
    await refreshReport()
  }

  const handleAddSchedule = async () => {
    setScheduleError('')
    const checkIntervalSeconds = parsePositiveInt(schedInterval, 5)
    const threshold = parsePositiveInt(schedTriggerThreshold, 1)
    if (!schedTask.trim() || !schedDate || !schedStart || !schedEnd) {
      setScheduleError('请填写任务、日期、开始时间和结束时间。')
      return
    }
    if (checkIntervalSeconds === null) {
      setScheduleError('检查间隔需要是 5 秒以上的整数。')
      return
    }
    if (threshold === null) {
      setScheduleError('触发答题命中次数需要是 1 以上的整数。')
      return
    }

    try {
      await addSchedule(
        schedTask.trim(),
        schedDate,
        schedStart,
        schedEnd,
        checkIntervalSeconds,
        parseTags(schedTags),
        schedStrict,
        threshold,
      )
      await refreshSchedules()
      setSchedTask('')
      setSchedTags('')
      setSchedStrict(true)
      setSchedInterval(defaultInterval || '300')
      setSchedTriggerThreshold(defaultTriggerThreshold || '1')
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
    const defaultIntervalSeconds = parsePositiveInt(defaultInterval, 5)
    const defaultThreshold = parsePositiveInt(defaultTriggerThreshold, 1)
    const guardianIntervalSeconds = parsePositiveInt(guardianInterval, 30)
    if (!nudgePrompt.trim()) {
      setSettingsStatus('提示语不能为空。')
      return
    }
    if (defaultIntervalSeconds === null) {
      setSettingsStatus('默认检测间隔需要是 5 秒以上的整数。')
      return
    }
    if (defaultThreshold === null) {
      setSettingsStatus('默认触发答题命中次数需要是 1 以上的整数。')
      return
    }
    if (guardianIntervalSeconds === null) {
      setSettingsStatus('Guardian mode 检测间隔需要是 30 秒以上的整数。')
      return
    }
    setSettingsStatus('保存中...')
    try {
      const res = await saveSettings({
        model: selectedModel,
        supervision_level: selectedSupervisionLevel,
        nudge_prompt: nudgePrompt.trim(),
        default_check_interval_seconds: defaultIntervalSeconds,
        trigger_threshold: defaultThreshold,
        whitelist_behaviors: whitelistText
          .replace(/，/g, '\n')
          .replace(/,/g, '\n')
          .split('\n')
          .map((item) => item.trim())
          .filter(Boolean),
        guardian_mode_enabled: guardianEnabled,
        guardian_check_interval_seconds: guardianIntervalSeconds,
        strict_mode_enabled: true,
      })
      setSettings(res.settings)
      setDefaultInterval(String(res.settings?.default_check_interval_seconds || defaultIntervalSeconds))
      setDefaultTriggerThreshold(String(res.settings?.trigger_threshold || defaultThreshold))
      setWhitelistText((res.settings?.whitelist_behaviors || []).join('\n'))
      setGuardianEnabled(Boolean(res.settings?.guardian_mode_enabled ?? guardianEnabled))
      setGuardianInterval(String(res.settings?.guardian_check_interval_seconds || guardianIntervalSeconds))
      setSettingsStatus('已保存，下一次 AI 判定生效。')
      setAiStatus(await getAiStatus())
    } catch (e) {
      setSettingsStatus(e.message || '保存失败')
    }
  }

  const handleSaveNotes = async () => {
    setNotesStatus('保存中...')
    try {
      setDailyReport(await saveDailyNotes(reportDate, todaySummary, tomorrowPlan))
      setNotesStatus('已保存')
    } catch (e) {
      setNotesStatus(e.message || '保存失败')
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
    stopped_pending: '停止中',
    day_paused: '暂停今日',
  }

  const flowStatus = status?.flow_status
  const strictStatus = status?.strict_status

  const blockStart = (b) => b.actual_start || b.planned_start
  const blockEnd = (b) => b.actual_end || b.planned_end

  const formatClock = (value) => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '--'

  const buildTimeline = () => {
    const blocks = (dailyReport?.blocks || [])
      .filter((b) => blockStart(b))
      .map((b) => ({
        ...b,
        startDate: new Date(blockStart(b)),
        endDate: blockEnd(b) ? new Date(blockEnd(b)) : new Date(),
      }))
      .filter((b) => !Number.isNaN(b.startDate.getTime()))
      .sort((a, b) => a.startDate - b.startDate)

    if (blocks.length === 0) return { segments: [], start: null, end: null }

    const start = blocks[0].startDate
    const end = new Date()
    const totalMs = Math.max(1, end - start)
    const segments = []
    let cursor = start

    blocks.forEach((block) => {
      const blockStartDate = block.startDate < start ? start : block.startDate
      const blockEndDate = block.endDate > end ? end : block.endDate
      if (blockStartDate > cursor) {
        segments.push({ kind: 'idle', label: '无指令', width: ((blockStartDate - cursor) / totalMs) * 100 })
      }
      if (blockEndDate > blockStartDate) {
        const kind = block.status === 'break' ? 'break' : block.status === 'stopped_pending' ? 'stopped' : 'focus'
        segments.push({
          kind,
          label: block.task || statusName[block.status] || block.status,
          width: ((blockEndDate - blockStartDate) / totalMs) * 100,
        })
        cursor = blockEndDate > cursor ? blockEndDate : cursor
      }
    })

    if (cursor < end) {
      segments.push({ kind: 'idle', label: '无指令', width: ((end - cursor) / totalMs) * 100 })
    }

    return { segments, start, end }
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
        <button className={tab === 'dataset' ? 'tab active' : 'tab'} onClick={() => setTab('dataset')}>Dataset</button>
        <button className={tab === 'settings' ? 'tab active' : 'tab'} onClick={() => setTab('settings')}>Settings</button>
      </nav>

      <div className={`ai-banner ${aiClass}`}>
        <span>AI 状态：{aiStatus?.message || '读取中...'}</span>
        {aiStatus?.model && <span className="ai-model">{aiStatus.model}</span>}
      </div>

      {tab === 'session' && (
        <>
          {!isRunning && flowStatus?.active && (
            <section className={`status-panel flow-${flowStatus.kind}`}>
              <div className="status-header">
                <div className="status-badge">{flowStatus.kind === 'break' ? '休息中' : '停止中'}</div>
                <div className="flow-timer">{flowStatus.kind === 'break' ? '休息还差 ' : '还差 '}{formatTime(flowRemainingSeconds || flowStatus.remaining_seconds || 0)}</div>
              </div>
              <div className="status-info">
                <div className="info-item"><span className="label">状态</span><span className="value">{flowStatus.kind === 'break' ? flowStatus.activity : flowStatus.reason}</span></div>
                {flowStatus.minimum_next_step && <div className="info-item"><span className="label">最小下一步</span><span className="value">{flowStatus.minimum_next_step}</span></div>}
                <div className="info-item"><span className="label">结束后</span><span className="value">输入下一轮任务和时间</span></div>
              </div>
            </section>
          )}

          {!isRunning ? (
            <section className="controls">
              <div className="input-group">
                <label>当前任务</label>
                <input ref={taskRef} type="text" value={task} onChange={(e) => setTask(e.target.value)}
                  placeholder="例如：开发产品 / 写报告 / 准备面谈" />
              </div>
              <div className="input-group">
                <label>标签（逗号分隔）</label>
                <input type="text" value={tags} onChange={(e) => setTags(e.target.value)}
                  placeholder="例如：产品, 写作, 深度工作" />
              </div>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={sessionStrict}
                  onChange={(e) => setSessionStrict(e.target.checked)}
                />
                下一个 Session 触发后强制答题（英文到日语翻译）
              </label>
              <div className="input-row">
                <div className="input-group">
                  <label>工作时长（分钟）</label>
                  <input type="number" value={duration} onChange={(e) => setDuration(e.target.value)} min="1" step="1" />
                </div>
                <div className="input-group">
                  <label>检查间隔（秒，默认 300）</label>
                  <input type="number" value={interval} onChange={(e) => setInterval_(e.target.value)} min="5" step="1" />
                </div>
                <div className="input-group">
                  <label>命中几次后答题</label>
                  <input type="number" value={triggerThreshold} onChange={(e) => setTriggerThreshold(e.target.value)} min="1" step="1" />
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
                <button className="btn-stop" onClick={handleStop} disabled={strictStatus?.session_locked}>停止</button>
              </div>
              {strictStatus?.session_locked && <p className="form-error">当前 Session 触发后强制答题；分心后需要完成英文到日语翻译题，然后选择回到工作或定时休息。</p>}
              <div className="status-info">
                <div className="info-item"><span className="label">任务</span><span className="value">{status?.task || task}</span></div>
                <div className="info-item"><span className="label">来源</span><span className="value">{status?.source === 'schedule' ? 'Schedule' : '手动'}</span></div>
                <div className="info-item"><span className="label">标签</span><span className="value">{(status?.tags || []).join(', ') || '--'}</span></div>
                <div className="info-item"><span className="label">强制答题</span><span className="value">{status?.strict_mode ? '开启' : '关闭'}</span></div>
                <div className="info-item"><span className="label">Session 档位</span><span className="value">{supervisionLevelOptions.find((level) => level.id === status?.supervision_level)?.label || status?.supervision_level || '--'}</span></div>
                <div className="info-item"><span className="label">答题阈值</span><span className="value">{status?.trigger_threshold || 1} 次命中</span></div>
                <div className="info-item"><span className="label">剩余时间</span><span className="value timer">{formatTime(remainingSeconds)}</span></div>
                <div className="info-item"><span className="label">当前活动</span><span className="value">{status?.latest_judgement?.current_activity || '等待检查...'}</span></div>
                <div className="info-item"><span className="label">AI 理由</span><span className="value">{statusText}</span></div>
                <div className="info-item"><span className="label">连续分心</span><span className={`value ${status?.off_task_streak >= (status?.trigger_threshold || 1) ? 'danger' : ''}`}>{status?.off_task_streak ?? 0}</span></div>
              </div>
              {showStopForm && (
                <div className="stop-form">
                  <div className="input-group">
                    <label>停止原因</label>
                    <input type="text" value={stopReason} onChange={(e) => setStopReason(e.target.value)}
                      placeholder="例如：临时会议 / 处理家务 / 身体不适" />
                  </div>
                  <div className="input-group">
                    <label>停止多久（分钟）</label>
                    <input type="number" value={stopMinutes} onChange={(e) => setStopMinutes(e.target.value)} min="1" step="1" />
                  </div>
                  <div className="input-group">
                    <label>停止标签（逗号分隔）</label>
                    <input type="text" value={stopTags} onChange={(e) => setStopTags(e.target.value)}
                      placeholder="例如：中断, 会议, 家务" />
                  </div>
                  {formError && <p className="form-error">{formError}</p>}
                  <div className="button-row">
                    <button className="btn-secondary" onClick={() => setShowStopForm(false)}>取消</button>
                    <button className="btn-stop" onClick={handleConfirmStop}>确认停止</button>
                  </div>
                </div>
              )}
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
            <div className="input-group">
              <label>标签（逗号分隔）</label>
              <input type="text" value={schedTags} onChange={(e) => setSchedTags(e.target.value)}
                placeholder="例如：学习, 数学" />
            </div>
            <label className="check-row">
              <input
                type="checkbox"
                checked={schedStrict}
                onChange={(e) => setSchedStrict(e.target.checked)}
              />
              到点后开启强制答题任务
            </label>
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
            <div className="input-row">
              <div className="input-group">
                <label>检查间隔（秒）</label>
                <input type="number" value={schedInterval} onChange={(e) => setSchedInterval(e.target.value)} min="5" step="1" />
              </div>
              <div className="input-group">
                <label>命中几次后答题</label>
                <input type="number" value={schedTriggerThreshold} onChange={(e) => setSchedTriggerThreshold(e.target.value)} min="1" step="1" />
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
                  <span className="schedule-time">
                    {s.date} {s.start_time} - {s.end_time} · {s.status === 'in_progress' ? '进行中' : '未开始'}{s.strict_mode ? ' · 监管' : ''} · {s.check_interval_seconds || 300}s / {s.trigger_threshold || 1} 次
                  </span>
                  {(s.tags || []).length > 0 && <span className="tag-row">{s.tags.join(', ')}</span>}
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
                <div className="stat-card rest"><div className="stat-value">{dailyReport.total_break_minutes || 0}</div><div className="stat-label">休息分钟</div></div>
                <div className="stat-card stopped"><div className="stat-value">{dailyReport.total_stopped_minutes || 0}</div><div className="stat-label">停止分钟</div></div>
              </div>

              {(() => {
                const timeline = buildTimeline()
                return (
                  <div className="timeline-panel">
                    <div className="timeline-head">
                      <span>{timeline.start ? formatClock(timeline.start) : '--'}</span>
                      <span>{timeline.end ? formatClock(timeline.end) : '--'}</span>
                    </div>
                    <div className="timeline-bar">
                      {timeline.segments.length === 0 && <div className="timeline-empty">无记录</div>}
                      {timeline.segments.map((segment, i) => (
                        <div
                          key={`${segment.kind}-${i}`}
                          className={`timeline-segment ${segment.kind}`}
                          title={segment.label}
                          style={{ width: `${Math.max(segment.width, 0.5)}%` }}
                        />
                      ))}
                    </div>
                    <div className="timeline-legend">
                      <span><b className="legend focus"></b>专注</span>
                      <span><b className="legend break"></b>休息</span>
                      <span><b className="legend stopped"></b>停止</span>
                      <span><b className="legend idle"></b>无指令</span>
                    </div>
                  </div>
                )
              })()}

              <div className="notes-panel">
                <div className="input-group">
                  <label>今天的总结</label>
                  <textarea value={todaySummary} onChange={(e) => setTodaySummary(e.target.value)}
                    placeholder="今天完成了什么？哪里被打断？明天要注意什么？" />
                </div>
                <div className="input-group">
                  <label>明天的规划</label>
                  <textarea value={tomorrowPlan} onChange={(e) => setTomorrowPlan(e.target.value)}
                    placeholder="明天准备做哪些任务？" />
                </div>
                <button className="btn-start" onClick={handleSaveNotes}>保存总结和规划</button>
                {notesStatus && <p className="settings-status">{notesStatus}</p>}
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
                    {(b.tags || []).length > 0 && <div className="tag-row">{b.tags.join(', ')}</div>}
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

      {tab === 'dataset' && (
        <section className="dataset-panel">
          <div className="section-title-row">
            <h2>截图数据集</h2>
            <button className="btn-secondary" onClick={refreshDataset}>刷新</button>
          </div>

          <div className="dataset-capture-row">
            <button className="btn-secondary" onClick={() => captureDataset('on_task')}>Ctrl+Alt+1 / on_task</button>
            <button className="btn-secondary" onClick={() => captureDataset('off_task')}>Ctrl+Alt+2 / off_task</button>
            <button className="btn-secondary" onClick={() => captureDataset('ambiguous')}>Ctrl+Alt+3 / ambiguous</button>
            <button className="btn-secondary" onClick={() => captureDataset('unlabeled')}>Ctrl+Alt+0 / unlabeled</button>
          </div>

          <div className="input-row">
            <div className="input-group">
              <label>标签筛选</label>
              <select value={datasetLabelFilter} onChange={(e) => { setDatasetLabelFilter(e.target.value); setDatasetIndex(0) }}>
                <option value="">全部</option>
                <option value="on_task">on_task</option>
                <option value="off_task">off_task</option>
                <option value="ambiguous">ambiguous</option>
                <option value="unlabeled">unlabeled</option>
              </select>
            </div>
            <div className="input-group">
              <label>Reviewed</label>
              <select value={datasetReviewedFilter} onChange={(e) => { setDatasetReviewedFilter(e.target.value); setDatasetIndex(0) }}>
                <option value="">全部</option>
                <option value="reviewed">已 reviewed</option>
                <option value="unreviewed">未 reviewed</option>
              </select>
            </div>
          </div>

          {currentDatasetSample ? (
            <div className="dataset-layout">
              <div className="dataset-preview">
                <img src={getDatasetImageUrl(currentDatasetSample)} alt="Dataset screenshot preview" />
              </div>
              <div className="dataset-editor">
                <div className="history-meta">
                  <span>{datasetIndex + 1} / {datasetSamples.length}</span>
                  <span>{new Date(currentDatasetSample.captured_at).toLocaleString()}</span>
                </div>
                <div className="info-item"><span className="label">任务</span><span className="value">{currentDatasetSample.task}</span></div>
                <div className="info-item"><span className="label">当前标签</span><span className="value">{currentDatasetSample.distraction_label}</span></div>
                <div className="label-button-row">
                  <button className="btn-secondary" onClick={() => updateCurrentDatasetLabel('on_task')}>1 on_task</button>
                  <button className="btn-secondary" onClick={() => updateCurrentDatasetLabel('off_task')}>2 off_task</button>
                  <button className="btn-secondary" onClick={() => updateCurrentDatasetLabel('ambiguous')}>3 ambiguous</button>
                  <button className="btn-secondary" onClick={() => updateCurrentDatasetLabel('unlabeled')}>unlabeled</button>
                </div>
                <div className="input-group">
                  <label>Activity</label>
                  <input id="dataset-activity" value={datasetActivity} onChange={(e) => setDatasetActivity(e.target.value)} />
                </div>
                <div className="input-group">
                  <label>Notes</label>
                  <textarea id="dataset-notes" value={datasetNotes} onChange={(e) => setDatasetNotes(e.target.value)} />
                </div>
                <div className="button-row">
                  <button className="btn-secondary" onClick={() => setDatasetIndex((i) => Math.max(0, i - 1))}>Previous</button>
                  <button className="btn-secondary" onClick={() => setDatasetIndex((i) => Math.min(datasetSamples.length - 1, i + 1))}>Next</button>
                </div>
                <div className="button-row">
                  <button className="btn-start" onClick={saveCurrentDatasetSample}>Save</button>
                  <button className="btn-secondary" onClick={toggleCurrentReviewed}>{currentDatasetSample.reviewed ? 'Unreview' : 'Mark reviewed'}</button>
                </div>
                <div className="button-row">
                  <button className="btn-secondary" onClick={() => openDatasetFolder(currentDatasetSample.id).catch((e) => setDatasetStatus(e.message || '打开文件夹失败'))}>Open screenshot folder</button>
                  <button className="btn-stop" onClick={deleteCurrentDatasetSample}>Delete sample</button>
                </div>
                {currentDatasetSample.ai_model && (
                  <p className="settings-current">AI: {currentDatasetSample.ai_model} · {currentDatasetSample.ai_confidence ?? '--'}</p>
                )}
              </div>
            </div>
          ) : (
            <p className="empty-msg">暂无样本。可以用 Ctrl+Alt+1/2/3/0 或上方按钮快速截图。</p>
          )}

          <div className="button-row dataset-bottom-actions">
            <button className="btn-secondary" onClick={handleDatasetExport}>Export JSONL</button>
            <button className="btn-secondary" onClick={() => openDatasetFolder().catch((e) => setDatasetStatus(e.message || '打开文件夹失败'))}>Open dataset folder</button>
          </div>
          {datasetStatus && <p className="settings-status">{datasetStatus}</p>}
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

          <div className="strict-box">
            <h3>Session 模式</h3>
            <div className="input-group">
              <label>Session 档位</label>
              <select value={selectedSupervisionLevel} onChange={(e) => setSelectedSupervisionLevel(e.target.value)}>
                {supervisionLevelOptions.map((level) => (
                  <option key={level.id} value={level.id}>{level.label}</option>
                ))}
              </select>
            </div>
            <div className="model-list">
              {supervisionLevelOptions.map((level) => (
                <button
                  key={level.id}
                  type="button"
                  className={selectedSupervisionLevel === level.id ? 'model-option selected' : 'model-option'}
                  onClick={() => setSelectedSupervisionLevel(level.id)}
                >
                  <span className="model-name">{level.label}</span>
                  <span className="model-description">{level.description}</span>
                </button>
              ))}
            </div>
            <div className="input-group">
              <label>触发时的心理距离提示语</label>
              <textarea value={nudgePrompt} onChange={(e) => setNudgePrompt(e.target.value)}
                placeholder="例如：先和冲动保持一点距离，然后选择一个最小下一步。" />
            </div>
            <div className="input-row">
              <div className="input-group">
                <label>默认检测间隔（秒）</label>
                <input type="number" value={defaultInterval} onChange={(e) => setDefaultInterval(e.target.value)} min="5" step="1" />
              </div>
              <div className="input-group">
                <label>默认命中几次后答题</label>
                <input type="number" value={defaultTriggerThreshold} onChange={(e) => setDefaultTriggerThreshold(e.target.value)} min="1" step="1" />
              </div>
            </div>
            <div className="input-group">
              <label>白名单行为（每行一条）</label>
              <textarea value={whitelistText} onChange={(e) => setWhitelistText(e.target.value)}
                placeholder="例如：听音乐&#10;看计时器&#10;查字典" />
            </div>
            <p className="settings-current">
              Session 模式用于正在运行的任务；白名单行为优先于 Session 档位，但小说、漫画和色情内容仍会被硬拦截。
            </p>
          </div>
          <div className="strict-box">
            <h3>Guardian mode</h3>
            <label className="check-row">
              <input
                type="checkbox"
                checked={guardianEnabled}
                onChange={(e) => setGuardianEnabled(e.target.checked)}
              />
              默认开启常驻 Guardian mode
            </label>
            <div className="input-group">
              <label>Guardian 检测间隔（秒）</label>
              <input type="number" value={guardianInterval} onChange={(e) => setGuardianInterval(e.target.value)} min="30" step="1" />
            </div>
            <p className="settings-current">
              Guardian mode 独立于 Session，常驻检测明显娱乐行为：小说、游戏、漫画、色情内容。
            </p>
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
