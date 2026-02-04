import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Api, ApiError } from '../api'
import { useAppSession } from '../app/context'
import { CASTES, type CasteId } from '../app/constants'

const PLAYER_ID_RE = /^[a-zA-Z0-9_]{3,20}$/

export default function OnboardingPage() {
  const nav = useNavigate()
  const { setPlayerId: setGlobalPlayerId, setCasteId: setGlobalCasteId } = useAppSession()

  const [err, setErr] = useState<string>('')
  const [playerId, setPlayerId] = useState<string>('')
  const [isRolling, setIsRolling] = useState(false)
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncProgress, setSyncSyncProgress] = useState(0)
  const [resultCaste, setResultCaste] = useState<(typeof CASTES)[number] | null>(null)
  const [rollIndex, setRollIndex] = useState(0)

  useEffect(() => {
    let timer: number
    if (isRolling) {
      timer = window.setInterval(() => {
        setRollIndex((prev) => (prev + 1) % CASTES.length)
      }, 80)
    }
    return () => clearInterval(timer)
  }, [isRolling])

  useEffect(() => {
    let timer: number
    if (isSyncing) {
      timer = window.setInterval(() => {
        setSyncSyncProgress(prev => {
          if (prev >= 100) {
            clearInterval(timer)
            return 100
          }
          return prev + Math.random() * 15
        })
      }, 200)
    }
    return () => clearInterval(timer)
  }, [isSyncing])

  const canSubmit = useMemo(() => {
    return PLAYER_ID_RE.test(playerId) && !isRolling && !isSyncing
  }, [playerId, isRolling, isSyncing])

  async function startLottery() {
    setErr('')
    if (!PLAYER_ID_RE.test(playerId)) {
      setErr('INVALID_PROTOCOL: ID_FORMAT_ERROR (3-20 CHARS, ALPHANUMERIC)')
      return
    }

    setIsRolling(true)
    setResultCaste(null)

    // 模拟抽取过程
    setTimeout(async () => {
      try {
        // 先尝试获取现有玩家信息
        const existing = await Api.playerAccount(playerId).catch(() => null)
        
        if (existing && existing.caste_id) {
          const found = CASTES.find(c => c.id === existing.caste_id)
          if (found) {
            setIsRolling(false)
            setResultCaste(found)
            setGlobalPlayerId(playerId)
            setGlobalCasteId(found.id as CasteId)
            return
          }
        }

        setIsRolling(false)
        
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
        setResultCaste(selected)
        setIsSyncing(true)
        setSyncSyncProgress(0)
        
        await Api.playersBootstrap({
          player_id: playerId,
          caste_id: selected.id,
        })
        
        // 等待进度条走完
        setTimeout(() => {
          setGlobalPlayerId(playerId)
          setGlobalCasteId(selected.id as CasteId)
        }, 1500)
      } catch (e) {
        setIsRolling(false)
        setIsSyncing(false)
        if (e instanceof ApiError) setErr(`GATEWAY_ERROR_${e.status}: ${e.message}`)
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
      boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Background decoration */}
      <div style={{ 
        position: 'absolute', 
        top: 0, left: 0, right: 0, height: '2px', 
        background: isRolling ? 'var(--terminal-info)' : (isSyncing ? 'var(--terminal-success)' : 'var(--terminal-border)'),
        transition: 'background 0.3s'
      }} />

      <h2 style={{ color: '#fff', fontSize: '20px', marginBottom: '8px', letterSpacing: '1px' }}>CITIZEN_REGISTRATION</h2>
      <div style={{ color: '#64748b', fontSize: '11px', marginBottom: '30px', fontFamily: 'monospace' }}>
        CENTRAL_GRID // AUTH_PROTOCOL_v4.2.0
      </div>
      
      {!resultCaste ? (
        <div style={{ marginTop: '20px' }}>
          <div style={{ marginBottom: '24px', fontSize: '13px', color: '#94a3b8', lineHeight: '1.5' }}>
            INPUT IDENTIFICATION CODE TO INITIATE<br/>
            NEURAL LINK ALLOCATION
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', alignItems: 'center' }}>
            <input 
              value={playerId} 
              onChange={(e) => setPlayerId(e.target.value.toUpperCase())} 
              placeholder="ENTER_ID_CODE"
              disabled={isRolling}
              className="cyber-input"
              style={{
                fontSize: '20px',
                textAlign: 'center',
                width: '100%',
                height: '56px',
                letterSpacing: '4px',
                fontFamily: 'monospace',
                background: 'rgba(0,0,0,0.2)'
              }}
            />
            
            <div style={{ 
              height: '70px', 
              display: 'flex', 
              flexDirection: 'column',
              alignItems: 'center', 
              justifyContent: 'center',
              fontSize: '18px',
              fontWeight: '700',
              color: isRolling ? 'var(--terminal-info)' : '#1e293b',
              border: '1px solid var(--terminal-border)',
              width: '100%',
              background: 'rgba(15, 23, 42, 0.5)',
              borderRadius: '2px',
              transition: 'all 0.2s',
              fontFamily: 'monospace'
            }}>
              <div style={{ fontSize: '10px', opacity: 0.5, marginBottom: '4px' }}>TARGET_CASTE_POOL</div>
              {isRolling ? CASTES[rollIndex].label.toUpperCase() : '--- STANDBY ---'}
            </div>

            <button 
              onClick={startLottery} 
              disabled={!canSubmit}
              className="cyber-button"
              style={{
                width: '100%',
                height: '52px',
                fontSize: '14px',
                background: canSubmit ? 'var(--terminal-info)' : 'transparent',
                borderColor: canSubmit ? 'var(--terminal-info)' : '#1e293b',
                color: canSubmit ? '#fff' : '#475569',
                fontWeight: '800',
                letterSpacing: '1px'
              }}
            >
              {isRolling ? 'EXECUTING_ALLOCATION...' : 'START_LINK_SEQUENCE'}
            </button>
          </div>
        </div>
      ) : (
        <div style={{ marginTop: '20px', animation: 'fadeIn 0.5s ease-out' }}>
          <div style={{ fontSize: '12px', color: 'var(--terminal-success)', marginBottom: '8px', fontWeight: 'bold' }}>
            [ ACCESS_GRANTED ]
          </div>
          
          <div style={{ 
            fontSize: '32px', 
            fontWeight: '900', 
            color: resultCaste.color,
            margin: '20px 0 10px 0',
            letterSpacing: '2px',
            textShadow: `0 0 20px ${resultCaste.color}44`
          }}>
            {resultCaste.label.split(' ')[0]}
          </div>
          
          <div style={{ color: '#94a3b8', fontSize: '13px', marginBottom: '30px', minHeight: '40px', lineHeight: '1.6' }}>
            {resultCaste.desc}
          </div>

          {isSyncing && (
            <div style={{ marginBottom: '30px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#64748b', marginBottom: '6px', fontFamily: 'monospace' }}>
                <span>ESTABLISHING_SECURE_CHANNEL</span>
                <span>{Math.round(syncProgress)}%</span>
              </div>
              <div style={{ width: '100%', height: '4px', background: '#0f172a', borderRadius: '2px', overflow: 'hidden' }}>
                <div style={{ 
                  width: `${syncProgress}%`, 
                  height: '100%', 
                  background: resultCaste.color,
                  transition: 'width 0.3s ease-out'
                }} />
              </div>
            </div>
          )}
          
          <button 
            onClick={enterGame}
            disabled={isSyncing && syncProgress < 100}
            className="cyber-button"
            style={{
              width: '100%',
              height: '52px',
              fontSize: '14px',
              background: (isSyncing && syncProgress < 100) ? 'transparent' : resultCaste.color,
              borderColor: resultCaste.color,
              color: '#fff',
              fontWeight: '800',
              letterSpacing: '1px',
              opacity: (isSyncing && syncProgress < 100) ? 0.3 : 1,
              boxShadow: (isSyncing && syncProgress < 100) ? 'none' : `0 0 20px ${resultCaste.color}33`
            }}
          >
            {(isSyncing && syncProgress < 100) ? 'SYNCING_WITH_MARKET...' : 'INITIALIZE_TERMINAL'}
          </button>
        </div>
      )}

      {err ? (
        <div style={{ 
          color: 'var(--terminal-error)', 
          marginTop: '24px', 
          fontSize: '11px', 
          padding: '12px', 
          background: 'rgba(239, 68, 68, 0.05)', 
          border: '1px solid rgba(239, 68, 68, 0.2)',
          textAlign: 'left',
          fontFamily: 'monospace'
        }}>
          <span style={{ fontWeight: 'bold' }}>[!] ERROR_DETECTED:</span> {err}
        </div>
      ) : null}
      
      <div style={{ marginTop: '40px', fontSize: '9px', color: '#475569', textAlign: 'left', borderTop: '1px solid var(--terminal-border)', paddingTop: '15px', fontFamily: 'monospace', lineHeight: '1.8' }}>
        LINK_STATUS: {isRolling ? 'RANDOMIZING' : (isSyncing ? 'SYNCHRONIZING' : 'STABLE')}<br/>
        ENCRYPTION: AES_256_E2EE<br/>
        LOCATION: SECTOR_7_DISTRICT_B
      </div>
    </div>
  )
}
