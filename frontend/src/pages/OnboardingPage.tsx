import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Api, ApiError } from '../api'

const PLAYER_ID_RE = /^[a-zA-Z0-9_]{3,20}$/

const CASTES = [
  { id: 'ELITE', label: '精英阶层 (Elite)', color: '#ff4d4f', weight: 0.1, desc: '掌控巨量原始资本，拥有信息溯源权' },
  { id: 'MIDDLE', label: '中产阶层 (Middle)', color: '#1890ff', weight: 0.3, desc: '拥有稳健的起步资金' },
  { id: 'WORKING', label: '工薪阶层 (Working)', color: '#52c41a', weight: 0.6, desc: '白手起家，依赖社交网络获取信息' },
]

export default function OnboardingPage() {
  const nav = useNavigate()

  const [err, setErr] = useState<string>('')
  const [playerId, setPlayerId] = useState<string>('')
  const [isRolling, setIsRolling] = useState(false)
  const [resultCaste, setResultCaste] = useState<typeof CASTES[0] | null>(null)
  const [rollIndex, setRollIndex] = useState(0)

  useEffect(() => {
    let timer: number
    if (isRolling) {
      timer = window.setInterval(() => {
        setRollIndex((prev) => (prev + 1) % CASTES.length)
      }, 100)
    }
    return () => clearInterval(timer)
  }, [isRolling])

  const canSubmit = useMemo(() => {
    return PLAYER_ID_RE.test(playerId) && !isRolling
  }, [playerId, isRolling])

  async function startLottery() {
    setErr('')
    if (!PLAYER_ID_RE.test(playerId)) {
      setErr('ID 格式不正确 (3-20位字母数字下划线)')
      return
    }

    setIsRolling(true)
    setResultCaste(null)

    // 随机抽取阶级
    const rand = Math.random()
    let cumulative = 0
    let selected = CASTES[CASTES.length - 1]
    for (const c of CASTES) {
      cumulative += c.weight
      if (rand < cumulative) {
        selected = c
        break
      }
    }

    // 模拟滚动动画
    setTimeout(async () => {
      setIsRolling(false)
      setResultCaste(selected)
      
      try {
        await Api.playersBootstrap({
          player_id: playerId,
          caste_id: selected.id,
        })
        window.localStorage.setItem('if.playerId', playerId)
        window.localStorage.setItem('if.casteId', selected.id)
      } catch (e) {
        if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
        else setErr(e instanceof Error ? e.message : String(e))
      }
    }, 2000)
  }

  function enterGame() {
    nav('/market', { replace: true })
  }

  return (
    <div className="card" style={{ 
      textAlign: 'center', 
      maxWidth: 600, 
      margin: '40px auto', 
      padding: '40px 20px',
      background: '#000',
      color: '#0f0',
      fontFamily: 'monospace',
      border: '1px solid #0f0',
      boxShadow: '0 0 20px rgba(0, 255, 0, 0.2)'
    }}>
      <h2 style={{ textShadow: '0 0 10px #0f0' }}>阶级分配系统 (The Great Lottery)</h2>
      
      {!resultCaste ? (
        <div style={{ marginTop: 30 }}>
          <div style={{ marginBottom: 20, fontSize: 14 }}>
            请输入你的公民唯一识别码以启动分配程序
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 15, alignItems: 'center' }}>
            <input 
              value={playerId} 
              onChange={(e) => setPlayerId(e.target.value)} 
              placeholder="PLAYER_ID"
              disabled={isRolling}
              style={{
                background: '#111',
                border: '1px solid #0f0',
                color: '#0f0',
                padding: '10px 20px',
                fontSize: 18,
                textAlign: 'center',
                width: '80%'
              }}
            />
            
            <div style={{ 
              height: 60, 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              fontSize: 24,
              fontWeight: 'bold',
              color: isRolling ? '#0f0' : '#333',
              border: '1px solid #333',
              width: '80%',
              background: '#111'
            }}>
              {isRolling ? CASTES[rollIndex].label : '--- 等待初始化 ---'}
            </div>

            <button 
              onClick={startLottery} 
              disabled={!canSubmit}
              style={{
                padding: '12px 40px',
                fontSize: 18,
                background: canSubmit ? '#0f0' : '#333',
                color: '#000',
                border: 'none',
                cursor: canSubmit ? 'pointer' : 'not-allowed',
                fontWeight: 'bold'
              }}
            >
              {isRolling ? '分配中...' : '启动分配程序'}
            </button>
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 30, animation: 'fadeIn 0.5s' }}>
          <div style={{ fontSize: 18, marginBottom: 10 }}>分配完成</div>
          <div style={{ 
            fontSize: 32, 
            fontWeight: 'bold', 
            color: resultCaste.color,
            margin: '20px 0',
            textShadow: `0 0 15px ${resultCaste.color}`
          }}>
            {resultCaste.label}
          </div>
          <div style={{ color: '#aaa', fontSize: 14, marginBottom: 30 }}>
            {resultCaste.desc}
          </div>
          
          <button 
            onClick={enterGame}
            style={{
              padding: '12px 40px',
              fontSize: 18,
              background: resultCaste.color,
              color: '#fff',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 'bold'
            }}
          >
            进入华尔街
          </button>
        </div>
      )}

      {err ? <div style={{ color: '#ff4d4f', marginTop: 20 }}>[ERROR]: {err}</div> : null}
      
      <div style={{ marginTop: 40, fontSize: 10, color: '#444', textAlign: 'left' }}>
        SYSTEM_V2.0_IDENTITY_ASSIGNMENT_PROTOCOL<br/>
        ENCRYPTION: AES-256-GCM<br/>
        STATUS: {isRolling ? 'RUNNING...' : 'READY'}
      </div>
    </div>
  )
}
