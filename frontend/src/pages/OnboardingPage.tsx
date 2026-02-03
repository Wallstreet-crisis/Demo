import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Api, ApiError } from '../api'
import { useAppSession } from '../app/context'

const PLAYER_ID_RE = /^[a-zA-Z0-9_]{3,20}$/

const CASTES = [
  { id: 'ELITE', label: '精英阶层 (Elite)', color: '#ff4d4f', weight: 0.1, desc: '掌控巨量原始资本，拥有信息溯源权' },
  { id: 'MIDDLE', label: '中产阶层 (Middle)', color: '#1890ff', weight: 0.3, desc: '拥有稳健的起步资金' },
  { id: 'WORKING', label: '工薪阶层 (Working)', color: '#52c41a', weight: 0.6, desc: '白手起家，依赖社交网络获取信息' },
]

export default function OnboardingPage() {
  const nav = useNavigate()
  const { setPlayerId: setGlobalPlayerId, setCasteId: setGlobalCasteId } = useAppSession()

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
        setGlobalPlayerId(playerId)
        setGlobalCasteId(selected.id)
      } catch (e) {
        if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
        else setErr(e instanceof Error ? e.message : String(e))
      }
    }, 2000)
  }

  function enterGame() {
    nav('/dashboard', { replace: true })
  }

  return (
    <div className="cyber-card" style={{ 
      textAlign: 'center', 
      maxWidth: '500px', 
      margin: '80px auto', 
      padding: '40px',
      background: 'var(--panel-bg)',
      border: '1px solid var(--terminal-border)',
      borderRadius: '4px'
    }}>
      <h2 style={{ color: '#fff', fontSize: '20px', marginBottom: '8px' }}>IDENTITY_ASSIGNMENT</h2>
      <div style={{ color: '#64748b', fontSize: '13px', marginBottom: '30px' }}>THE GREAT LOTTERY // PROTOCOL v4.2</div>
      
      {!resultCaste ? (
        <div style={{ marginTop: '20px' }}>
          <div style={{ marginBottom: '20px', fontSize: '14px', color: '#94a3b8' }}>
            Enter citizen identification code to initiate allocation
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', alignItems: 'center' }}>
            <input 
              value={playerId} 
              onChange={(e) => setPlayerId(e.target.value)} 
              placeholder="CITIZEN_ID"
              disabled={isRolling}
              className="cyber-input"
              style={{
                fontSize: '18px',
                textAlign: 'center',
                width: '100%',
                height: '48px',
                letterSpacing: '2px'
              }}
            />
            
            <div style={{ 
              height: '60px', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              fontSize: '20px',
              fontWeight: '700',
              color: isRolling ? 'var(--terminal-info)' : '#334155',
              border: '1px solid var(--terminal-border)',
              width: '100%',
              background: 'var(--terminal-bg)',
              borderRadius: '2px'
            }}>
              {isRolling ? CASTES[rollIndex].label.toUpperCase() : '--- WAITING_FOR_INIT ---'}
            </div>

            <button 
              onClick={startLottery} 
              disabled={!canSubmit}
              className="cyber-button"
              style={{
                width: '100%',
                height: '48px',
                fontSize: '16px',
                background: canSubmit ? 'var(--terminal-info)' : '#1e293b',
                color: '#fff',
                border: 'none',
                fontWeight: '700',
                opacity: canSubmit ? 1 : 0.5
              }}
            >
              {isRolling ? 'ALLOCATING...' : 'INITIATE_ALLOCATION'}
            </button>
          </div>
        </div>
      ) : (
        <div style={{ marginTop: '20px', animation: 'fadeIn 0.3s ease-out' }}>
          <div style={{ fontSize: '14px', color: '#94a3b8', marginBottom: '10px' }}>ALLOCATION_COMPLETE</div>
          <div style={{ 
            fontSize: '28px', 
            fontWeight: '800', 
            color: resultCaste.color,
            margin: '24px 0',
            letterSpacing: '1px'
          }}>
            {resultCaste.label.toUpperCase()}
          </div>
          <div style={{ color: '#cbd5e1', fontSize: '14px', marginBottom: '40px', lineHeight: '1.6' }}>
            {resultCaste.desc}
          </div>
          
          <button 
            onClick={enterGame}
            className="cyber-button"
            style={{
              width: '100%',
              height: '48px',
              fontSize: '16px',
              background: resultCaste.color,
              color: '#fff',
              border: 'none',
              fontWeight: '700'
            }}
          >
            ENTER_TERMINAL
          </button>
        </div>
      )}

      {err ? <div style={{ color: 'var(--terminal-error)', marginTop: '24px', fontSize: '13px', padding: '10px', background: 'rgba(239, 68, 68, 0.1)', borderLeft: '3px solid var(--terminal-error)' }}>[ERROR]: {err}</div> : null}
      
      <div style={{ marginTop: '40px', fontSize: '10px', color: '#475569', textAlign: 'left', borderTop: '1px solid var(--terminal-border)', paddingTop: '10px' }}>
        STATUS: {isRolling ? 'EXECUTING_RANDOM_WALK' : 'IDLE'}<br/>
        ENCRYPTION: RSA_4096_GCM<br/>
        GATEWAY: WALLSTREET_MAIN_GRID
      </div>
    </div>
  )
}
