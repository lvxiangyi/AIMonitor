import { useState, useEffect, useRef } from 'react'
import {
  startSession, stopSession, getStatus,
  getSchedules, addSchedule, deleteSchedule,
  getAnalytics, getWrongAnswers, testBlock
} from './api'

function App() {
  const [tab, setTab] = useState('session')
  const [task, setTask] = useState('')
  const [duration, setDuration] = useState(10)
  const [interval, setInterval_] = useState(30)
  const [status, setStatus] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const pollRef = useRef(null)

  const [schedules, setSchedules] = useState([])
  const [schedTask, setSchedTask] = useState('')
  const [schedDate, setSchedDate] = useState('')
  const [schedTime, setSchedTime] = useState('')
  const [schedDuration, setSchedDuration] = useState(25)

  const [analytics, setAnalytics] = useState(null)
  const [wrongAnswers, setWrongAnswers] = useState([])

  useEffect(() => {
    if (isRunning) {
      const poll = async () => {
        try {
          const s = await getStatus()
          setStatus(s)
          if (!s.active && isRunning) setIsRunning(false)
        } catch (e) { /* ignore */ }
      }
      poll()
      pollRef.current = window.setInterval(poll, 3000)
      return () => window.clearInterval(pollRef.current)
    }
  }, [isRunning])

  useEffect(() => {
    if (tab === 'schedule') {
      getSchedules().then(d => setSchedules(d.schedules || [])).catch(() => {})
    }
  }, [tab])

  useEffect(() => {
    if (tab === 'analytics') {
      getAnalytics().then(setAnalytics).catch(() => {})
      getWrongAnswers().then(d => setWrongAnswers(d.wrong_answers || [])).catch(() => {})
    }
  }, [tab])

  const handleStart = async () => {
    try {
      const res = await startSession(task, duration, interval)
      setSessionId(res.session_id)
      setIsRunning(true)
    } catch (e) {
      alert('バックエンドに接続できません')
    }
  }

  const handleStop = async () => {
    await stopSession(sessionId)
    setIsRunning(false)
    setStatus(null)
  }

  const handleAddSchedule = async () => {
    if (!schedTask || !schedDate || !schedTime) return
    await addSchedule(schedTask, schedDate, schedTime, schedDuration, 30)
    const d = await getSchedules()
    setSchedules(d.schedules || [])
    setSchedTask('')
    setSchedDate('')
    setSchedTime('')
  }

  const handleDeleteSchedule = async (id) => {
    await deleteSchedule(id)
    const d = await getSchedules()
    setSchedules(d.schedules || [])
  }

  const handleStartFromSchedule = (sched) => {
    setTask(sched.task)
    setDuration(sched.duration_minutes)
    setInterval_(sched.check_interval_seconds)
    setTab('session')
  }

  const formatTime = (seconds) => {
    if (!seconds && seconds !== 0) return '--:--'
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }

  const getStatusLabel = () => {
    if (!status || !status.active) return '待機中'
    if (!status.latest_judgement) return '初回チェック待ち...'
    return status.latest_judgement.on_task ? '✅ 集中' : '❌ 気が散っている'
  }

  return (
    <div className="container">
      <header>
        <h1>🛡️ FocusGuard Agent</h1>
        <p className="subtitle">AI学習監督アシスタント</p>
      </header>

      <nav className="tabs">
        <button className={tab === 'session' ? 'tab active' : 'tab'} onClick={() => setTab('session')}>
          ⏱️ セッション
        </button>
        <button className={tab === 'schedule' ? 'tab active' : 'tab'} onClick={() => setTab('schedule')}>
          📅 スケジュール
        </button>
        <button className={tab === 'analytics' ? 'tab active' : 'tab'} onClick={() => setTab('analytics')}>
          📊 レポート
        </button>
      </nav>

      {tab === 'session' && (
        <>
          {!isRunning ? (
            <section className="controls">
              <div className="input-group">
                <label>学習目標</label>
                <input type="text" value={task} onChange={(e) => setTask(e.target.value)}
                  placeholder="例：数学を勉強する / 論文を書く / 英語を復習する" />
              </div>
              <div className="input-row">
                <div className="input-group">
                  <label>学習時間（分）</label>
                  <input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))} min="1" />
                </div>
                <div className="input-group">
                  <label>チェック間隔（秒）</label>
                  <input type="number" value={interval} onChange={(e) => setInterval_(Number(e.target.value))} min="5" />
                </div>
              </div>
              <button className="btn-start" onClick={handleStart}>▶️ 監督を開始</button>
              <button className="btn-test" onClick={() => testBlock()}>🧪 テスト（遮蔽画面を表示）</button>
            </section>
          ) : (
            <section className="status-panel">
              <div className="status-header">
                <div className="status-badge">{getStatusLabel()}</div>
                <button className="btn-stop" onClick={handleStop}>⏹️ 停止</button>
              </div>
              <div className="status-info">
                <div className="info-item">
                  <span className="label">現在のタスク</span>
                  <span className="value">{status?.task || task}</span>
                </div>
                <div className="info-item">
                  <span className="label">残り時間</span>
                  <span className="value timer">{formatTime(status?.remaining_seconds)}</span>
                </div>
                <div className="info-item">
                  <span className="label">現在の活動</span>
                  <span className="value">{status?.latest_judgement?.current_activity || '待機中...'}</span>
                </div>
                <div className="info-item">
                  <span className="label">AI理由</span>
                  <span className="value">{status?.latest_judgement?.reason || '--'}</span>
                </div>
                <div className="info-item">
                  <span className="label">連続気散り回数</span>
                  <span className={`value ${status?.off_task_streak >= 2 ? 'danger' : ''}`}>
                    {status?.off_task_streak ?? 0}
                  </span>
                </div>
              </div>
            </section>
          )}

          {status?.logs && status.logs.length > 0 && (
            <section className="logs">
              <h2>📋 セッションログ</h2>
              <div className="log-list">
                {[...status.logs].reverse().map((log, i) => (
                  <div key={i} className={`log-item ${log.on_task ? 'on-task' : 'off-task'}`}>
                    <div className="log-time">{new Date(log.timestamp).toLocaleTimeString()}</div>
                    <div className="log-status">{log.on_task ? '✅' : '❌'}</div>
                    <div className="log-details">
                      <span className="log-activity">{log.current_activity}</span>
                      <span className="log-reason">{log.reason}</span>
                    </div>
                    <div className="log-confidence">{Math.round(log.confidence * 100)}%</div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {tab === 'schedule' && (
        <section className="schedule-panel">
          <h2>📅 学習スケジュール</h2>
          <div className="schedule-form">
            <div className="input-group">
              <label>タスク</label>
              <input type="text" value={schedTask} onChange={(e) => setSchedTask(e.target.value)}
                placeholder="例：数学を勉強する" />
            </div>
            <div className="input-row">
              <div className="input-group">
                <label>日付</label>
                <input type="date" value={schedDate} onChange={(e) => setSchedDate(e.target.value)} />
              </div>
              <div className="input-group">
                <label>開始時間</label>
                <input type="time" value={schedTime} onChange={(e) => setSchedTime(e.target.value)} />
              </div>
              <div className="input-group">
                <label>時間（分）</label>
                <input type="number" value={schedDuration} onChange={(e) => setSchedDuration(Number(e.target.value))} min="5" />
              </div>
            </div>
            <button className="btn-start" onClick={handleAddSchedule}>➕ スケジュールに追加</button>
          </div>

          <div className="schedule-list">
            {schedules.length === 0 && <p className="empty-msg">まだスケジュールがありません</p>}
            {schedules.map((s) => (
              <div key={s.id} className="schedule-item">
                <div className="schedule-info">
                  <span className="schedule-task">{s.task}</span>
                  <span className="schedule-time">{s.date} {s.start_time} ({s.duration_minutes}分)</span>
                </div>
                <div className="schedule-actions">
                  <button className="btn-small btn-green" onClick={() => handleStartFromSchedule(s)}>▶</button>
                  <button className="btn-small btn-red" onClick={() => handleDeleteSchedule(s.id)}>✕</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {tab === 'analytics' && (
        <section className="analytics-panel">
          <h2>📊 学習レポート</h2>

          {analytics && (
            <>
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-value">{analytics.total_checks}</div>
                  <div className="stat-label">総チェック数</div>
                </div>
                <div className="stat-card good">
                  <div className="stat-value">{analytics.focus_rate}%</div>
                  <div className="stat-label">集中率</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{analytics.focused_checks}</div>
                  <div className="stat-label">集中</div>
                </div>
                <div className="stat-card bad">
                  <div className="stat-value">{analytics.distracted_checks}</div>
                  <div className="stat-label">気散り</div>
                </div>
              </div>

              {analytics.total_checks > 0 && (
                <div className="focus-bar-container">
                  <div className="focus-bar">
                    <div className="focus-bar-fill" style={{ width: `${analytics.focus_rate}%` }}></div>
                  </div>
                  <span className="focus-bar-label">集中 {analytics.focus_rate}% / 気散り {(100 - analytics.focus_rate).toFixed(1)}%</span>
                </div>
              )}

              {analytics.top_distractions && analytics.top_distractions.length > 0 && (
                <div className="section-block">
                  <h3>🚨 気散りランキング</h3>
                  <div className="distraction-list">
                    {analytics.top_distractions.map((d, i) => (
                      <div key={i} className="distraction-item">
                        <span className="distraction-rank">#{i + 1}</span>
                        <span className="distraction-name">{d.activity}</span>
                        <span className="distraction-count">{d.count}回</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {analytics.sessions && analytics.sessions.length > 0 && (
                <div className="section-block">
                  <h3>📈 セッション履歴</h3>
                  <div className="session-history">
                    {analytics.sessions.slice(-10).reverse().map((s, i) => (
                      <div key={i} className="history-item">
                        <div className="history-task">{s.task}</div>
                        <div className="history-meta">
                          <span>{new Date(s.start_time).toLocaleString()}</span>
                          <span>集中: {s.focused_checks}/{s.total_checks}</span>
                        </div>
                        <div className="history-bar">
                          <div className="history-bar-fill"
                            style={{ width: `${s.total_checks > 0 ? (s.focused_checks / s.total_checks * 100) : 0}%` }}>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {wrongAnswers.length > 0 && (
            <div className="section-block">
              <h3>❌ 間違えた問題</h3>
              <div className="wrong-list">
                {wrongAnswers.slice(-10).reverse().map((w, i) => (
                  <div key={i} className="wrong-item">
                    <div className="wrong-question">{w.question}</div>
                    <div className="wrong-meta">
                      <span className="wrong-your">あなた: {w.user_answer}</span>
                      <span className="wrong-correct">正解: {w.correct_answer}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!analytics && <p className="empty-msg">データがまだありません。セッションを開始してください。</p>}
        </section>
      )}
    </div>
  )
}

export default App
