import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Api } from '../api'
import { useAppSession } from '../app/context'
import SettingsModal from '../components/SettingsModal'

export default function MainMenuPage() {
  const nav = useNavigate()
  const { setPlayerId: setGlobalPlayerId, setCasteId, setRoomId } = useAppSession()
  const [activeView, setActiveView] = useState<'MAIN' | 'LOCAL' | 'NETWORK'>('MAIN')
  const [networkIp, setNetworkIp] = useState('127.0.0.1:8000')
  const [inputPlayerId, setInputPlayerId] = useState('')
  const [localRooms, setLocalRooms] = useState<any[]>([])
  const [remoteRooms, setRemoteRooms] = useState<any[]>([])
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null)
  const [isTransitioning, setIsTransitioning] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [networkScanning, setNetworkScanning] = useState(false)
  const [roomTimeLimitEnabled, setRoomTimeLimitEnabled] = useState(false)
  const [roomTimeLimitMinutes, setRoomTimeLimitMinutes] = useState('30')
  const [availableScenarios, setAvailableScenarios] = useState<any[]>([])
  const [selectedScenario, setSelectedScenario] = useState<string>('')

  const isInputValid = inputPlayerId.length >= 3 && inputPlayerId.length <= 20

  const fetchGlobalScenarios = async () => {
    try {
      const data = await Api.globalStudioNewsScenarios()
      setAvailableScenarios(data)
    } catch (e) {
      console.error('Failed to load global scenarios:', e)
    }
  }

  const syncRoomEditorFromMeta = (room: any) => {
    const settings = room?.game_settings || {}
    setRoomTimeLimitEnabled(!!settings.time_limit_seconds)
    setRoomTimeLimitMinutes(String(Math.max(5, Math.round((settings.time_limit_seconds || 1800) / 60))))
    setSelectedScenario(settings.scenario_id || '')
  }

  const buildRoomGameSettings = () => {
    const minutes = Number(roomTimeLimitMinutes)
    const game_settings: any = {
      scenario_id: selectedScenario || undefined,
    }
    if (roomTimeLimitEnabled && Number.isFinite(minutes) && minutes > 0) {
      game_settings.time_limit_seconds = Math.round(minutes * 60)
    } else {
      game_settings.time_limit_seconds = null
    }
    return game_settings
  }

  const fetchLocalRooms = async () => {
    try {
      const res = await Api.listLocalRooms() as any
      if (res.rooms) {
        setLocalRooms(res.rooms)
      } else {
        setLocalRooms([])
      }
    } catch (e) {
      console.error('Failed to list local rooms:', e)
      setLocalRooms([])
    }
  }

  useEffect(() => {
    setActiveLocalView('IDLE')
    if (activeView === 'LOCAL') {
      localStorage.removeItem('if_network_target')
      fetchLocalRooms()
      fetchGlobalScenarios()
      setSelectedRoomId(null)
    } else if (activeView === 'NETWORK') {
      setRemoteRooms([])
      setSelectedRoomId(null)
      setNetworkConnected(false)
    }
  }, [activeView])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showSettings) {
          setShowSettings(false)
        } else if (activeView !== 'MAIN') {
          setActiveView('MAIN')
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeView, showSettings])

  const handleDeleteSave = async (roomId: string) => {
    if (!window.confirm('Are you sure you want to permanently delete this simulation data?')) return
    try {
      await Api.deleteRoom(roomId)
      if (selectedRoomId === roomId) {
        setSelectedRoomId(null)
      }
      fetchLocalRooms()
    } catch (e) {
      console.error('Failed to delete room:', e)
    }
  }

  const [activeLocalView, setActiveLocalView] = useState<'IDLE' | 'LOAD' | 'CREATE' | 'EDIT' | 'JOIN'>('IDLE')
  const [networkConnected, setNetworkConnected] = useState(false)
  
  const handleCreateNewSimulation = async () => {
    setIsTransitioning(true)
    const animationPromise = new Promise(resolve => setTimeout(resolve, 800))
    if (activeView === 'LOCAL') {
      localStorage.removeItem('if_network_target')
    }
    const game_settings = buildRoomGameSettings()
    
    // 我们暂时使用 HOST 作为创建者标识
    const createRoomPromise = Api.createRoom({ player_id: 'HOST', game_settings })

    try {
      const [, res] = await Promise.all([animationPromise, createRoomPromise])
      if (res.ok && res.room_id) {
        setIsTransitioning(false)
        if (activeView === 'LOCAL') {
          fetchLocalRooms()
          setSelectedRoomId(res.room_id)
          setActiveLocalView('JOIN') // 直接进入加入界面
        } else {
          // Network link
          handleJoinNetwork()
          setActiveLocalView('LOAD')
        }
      }
    } catch (e) {
      console.error('Failed to create new room:', e)
      setIsTransitioning(false)
      alert('Failed to initialize new simulation instance.')
    }
  }

  const handleUpdateRoomSettings = async () => {
    if (!selectedRoomId) return
    const room = (activeView === 'LOCAL' ? localRooms : remoteRooms).find(r => r.room_id === selectedRoomId)
    if (!room) return

    const game_settings = buildRoomGameSettings()

    try {
      const res = await Api.updateRoomMeta(selectedRoomId, room.name, game_settings)
      if (res.ok) {
        setActiveLocalView('LOAD')
        if (activeView === 'LOCAL') fetchLocalRooms()
        else handleJoinNetwork()
      }
    } catch (e) {
      console.error('Failed to update room settings:', e)
      alert('Failed to save room settings updates.')
    }
  }

  const handleJoinSelectedSimulation = async () => {
    if (!selectedRoomId || !isInputValid) return
    setIsTransitioning(true)
    if (activeView === 'LOCAL') {
      localStorage.removeItem('if_network_target')
    } else {
      localStorage.setItem('if_network_target', networkIp)
    }
    
    setRoomId(selectedRoomId)
    
    try {
      const animationPromise = new Promise(resolve => setTimeout(resolve, 800))
      const activatePromise = Api.activateRoom(selectedRoomId)
      
      const [, activateRes] = await Promise.all([animationPromise, activatePromise])
      if (!activateRes.ok) throw new Error('Room activation failed')
      
      setGlobalPlayerId(inputPlayerId)
      setCasteId('' as any)
      nav('/onboarding')
    } catch (e: any) {
      console.error('Failed to resume simulation:', e)
      setRoomId('default')
      setIsTransitioning(false)
      const detail = e?.body?.detail || e?.message || 'Unknown error'
      alert(`Failed to load simulation: ${detail}`)
    }
  }

  const handleJoinNetwork = async () => {
    if (!networkIp) return
    setNetworkScanning(true)
    localStorage.setItem('if_network_target', networkIp)

    try {
      const res = await Api.networkJoinCheck() as any
      if (res.ok) {
        setRemoteRooms(res.rooms || [])
        setNetworkConnected(true)
        fetchGlobalScenarios()
      } else {
        throw new Error('Connection rejected by remote host.')
      }
    } catch (e) {
      console.error('Failed to connect to network target:', e)
      localStorage.removeItem('if_network_target')
      setRemoteRooms([])
      setNetworkConnected(false)
      alert('Connection failed or rejected by remote host.')
    } finally {
      setNetworkScanning(false)
    }
  }

  const renderRoomSettings = (isEdit = false) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginBottom: '24px' }}>
      {/* 模块1: 基础环境配置 */}
      <div style={{ 
        padding: '16px', 
        border: '1px solid var(--terminal-border)', 
        background: 'rgba(15, 23, 42, 0.4)',
        position: 'relative'
      }}>
        <div style={{ 
          position: 'absolute', 
          top: '-8px', 
          left: '12px', 
          background: 'var(--terminal-bg)', 
          padding: '0 8px', 
          fontSize: '10px', 
          color: '#64748b',
          fontFamily: 'monospace' 
        }}>
          {isEdit ? '01_ENVIRONMENT_STABILITY // EDIT' : '01_ENVIRONMENT_STABILITY // CREATE'}
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '14px', color: '#fff', marginBottom: '16px', cursor: 'pointer' }}>
          <div style={{ 
            width: '18px', 
            height: '18px', 
            border: '1px solid var(--terminal-info)', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            background: roomTimeLimitEnabled ? 'var(--terminal-info)' : 'transparent',
            transition: 'all 0.2s'
          }}>
            <input
              type="checkbox"
              style={{ display: 'none' }}
              checked={roomTimeLimitEnabled}
              onChange={(e) => setRoomTimeLimitEnabled(e.target.checked)}
            />
            {roomTimeLimitEnabled && <div style={{ width: '8px', height: '8px', background: '#000' }} />}
          </div>
          <span style={{ letterSpacing: '1px', fontWeight: 600 }}>AUTO-SETTLEMENT PROTOCOL</span>
        </label>

        <div style={{ 
          opacity: roomTimeLimitEnabled ? 1 : 0.3, 
          pointerEvents: roomTimeLimitEnabled ? 'auto' : 'none',
          transition: 'all 0.3s ease' 
        }}>
          <div style={{ fontSize: '11px', color: 'var(--terminal-info)', marginBottom: '8px', fontFamily: 'monospace' }}>{'>'} DURATION_MINUTES</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <input
              type="range"
              min="5"
              max="180"
              step="5"
              value={roomTimeLimitMinutes}
              onChange={(e) => setRoomTimeLimitMinutes(e.target.value)}
              style={{ flex: 1, accentColor: 'var(--terminal-info)' }}
            />
            <div style={{ 
              width: '60px', 
              textAlign: 'right', 
              fontFamily: 'monospace', 
              fontSize: '18px', 
              color: 'var(--terminal-info)',
              textShadow: '0 0 10px rgba(59, 130, 246, 0.5)'
            }}>
              {roomTimeLimitMinutes}m
            </div>
          </div>
        </div>
      </div>

      {/* 模块3: 剧本选择与设计 */}
      <div style={{ 
        padding: '16px', 
        border: '1px solid var(--terminal-border)', 
        background: 'rgba(15, 23, 42, 0.4)',
        position: 'relative'
      }}>
        <div style={{ 
          position: 'absolute', 
          top: '-8px', 
          left: '12px', 
          background: 'var(--terminal-bg)', 
          padding: '0 8px', 
          fontSize: '10px', 
          color: '#64748b',
          fontFamily: 'monospace' 
        }}>
          03_SIMULATION_BLUEPRINT
        </div>

        <div style={{ marginBottom: '16px' }}>
          <div style={{ fontSize: '11px', color: 'var(--terminal-info)', marginBottom: '8px', fontFamily: 'monospace' }}>{'>'} SELECT_ACTIVE_SCENARIO</div>
          <select 
            className="cyber-input"
            value={selectedScenario}
            onChange={(e) => setSelectedScenario(e.target.value)}
            style={{
              width: '100%',
              height: '40px',
              background: 'rgba(0,0,0,0.3)',
              border: '1px solid var(--terminal-border)',
              color: '#fff',
              padding: '0 12px',
              fontFamily: 'monospace',
              fontSize: '13px'
            }}
          >
            <option value="">DEFAULT_SIMULATION (SEED DATA)</option>
            {availableScenarios.map(s => (
              <option key={s.id} value={s.id}>{s.name.toUpperCase()}</option>
            ))}
          </select>
        </div>

        <div 
          onClick={() => nav('/studio/news')}
          style={{
            padding: '12px',
            border: '1px dashed rgba(59, 130, 246, 0.4)',
            background: 'rgba(59, 130, 246, 0.05)',
            cursor: 'pointer',
            transition: 'all 0.2s',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            color: 'var(--terminal-info)'
          }}
          onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(59, 130, 246, 0.15)'}
          onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(59, 130, 246, 0.05)'}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ fontSize: '20px' }}>⚒</div>
            <div>
              <div style={{ fontSize: '12px', fontWeight: 'bold', letterSpacing: '1px' }}>SCENARIO DESIGNER</div>
              <div style={{ fontSize: '10px', color: '#64748b' }}>Create or modify simulation cards</div>
            </div>
          </div>
          <div style={{ fontSize: '12px' }}>LAUNCH_STUDIO_EXE →</div>
        </div>
      </div>
    </div>
  )

  return (
    <div style={{
      width: '100vw',
      height: '100vh',
      backgroundColor: 'var(--terminal-bg)',
      color: 'var(--terminal-text)',
      display: 'flex',
      flexDirection: 'row',
      position: 'relative',
      overflow: 'hidden',
      opacity: isTransitioning ? 0 : 1,
      transition: 'opacity 0.8s ease-in-out',
    }}>
      {/* Background Cyber Grid */}
      <div style={{
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        backgroundImage: `
          linear-gradient(var(--terminal-border) 1px, transparent 1px),
          linear-gradient(90deg, var(--terminal-border) 1px, transparent 1px)
        `,
        backgroundSize: '40px 40px',
        backgroundPosition: 'center center',
        zIndex: 0,
        pointerEvents: 'none',
        opacity: 0.15,
        transform: 'perspective(500px) rotateX(60deg) translateY(-100px) translateZ(-200px)',
      }} />

      {/* Decorative Scanline */}
      <div style={{
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        background: 'linear-gradient(to bottom, rgba(255,255,255,0), rgba(255,255,255,0) 50%, rgba(0,0,0,0.1) 50%, rgba(0,0,0,0.1))',
        backgroundSize: '100% 4px',
        zIndex: 1,
        pointerEvents: 'none',
      }} />

      {/* Vignette */}
      <div style={{
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        background: 'radial-gradient(circle at center, transparent 0%, var(--terminal-bg) 100%)',
        zIndex: 2,
        pointerEvents: 'none',
      }} />

      {/* Left Menu Area */}
      <div style={{ 
        width: '500px',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: '0 60px',
        position: 'relative', 
        zIndex: 10,
        background: 'linear-gradient(to right, var(--terminal-bg) 40%, rgba(15, 23, 42, 0.8) 80%, transparent 100%)',
        boxSizing: 'border-box'
      }}>
        <h1 style={{
          fontSize: '3.5rem',
          fontWeight: 900,
          margin: '0 0 8px 0',
          letterSpacing: '-1px',
          color: 'var(--terminal-text)',
          textShadow: '0 0 20px rgba(59, 130, 246, 0.3)',
          lineHeight: '1',
          fontFamily: 'Inter, sans-serif'
        }}>
          INFORMATION<br />
          <span style={{ color: 'var(--terminal-info)' }}>FRONTIER</span>
        </h1>
        <div style={{
          fontSize: '13px',
          color: '#64748b',
          marginBottom: '60px',
          letterSpacing: '2px',
          fontFamily: 'monospace'
        }}>
          BUILD 0.2.0 // EARLY ACCESS
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', width: '100%' }}>
          {activeView === 'MAIN' && (
            <>
              <MenuButton onClick={() => setActiveView('LOCAL')} label="LOCAL NODE" sub="Single Player / Host" />
              <MenuButton onClick={() => setActiveView('NETWORK')} label="NETWORK LINK" sub="Multiplayer / Join" />
              <MenuButton onClick={() => {}} label="TRAINING MANUAL" sub="Interactive Tutorial" disabled />
              <MenuButton onClick={() => setShowSettings(true)} label="SYSTEM CONFIG" sub="LLM & Preferences" />
              <MenuButton onClick={() => window.close()} label="TERMINATE" sub="Exit System" />
            </>
          )}

          {activeView === 'LOCAL' && (
            <>
              <div style={{ color: 'var(--terminal-info)', marginBottom: '16px', fontSize: '12px', fontFamily: 'monospace' }}>{'>'} LOCAL_NODE_CONTROLLER</div>
              <MenuButton 
                onClick={() => {
                  setActiveLocalView('CREATE')
                  setSelectedRoomId(null)
                }} 
                label="INITIALIZE NEW" 
                sub="Spin up fresh simulation" 
                active={activeLocalView === 'CREATE'}
              />
              <MenuButton 
                onClick={() => {
                  setActiveLocalView('LOAD')
                  setSelectedRoomId(null)
                  fetchLocalRooms()
                }} 
                label="BROWSE SAVES" 
                sub="Access stored node archives" 
                active={activeLocalView === 'LOAD' || activeLocalView === 'JOIN' || activeLocalView === 'EDIT'}
              />
              <MenuButton onClick={() => setActiveView('MAIN')} label="RETURN" sub="Back to root" secondary />
            </>
          )}

          {activeView === 'NETWORK' && (
            <>
              <div style={{ color: 'var(--terminal-info)', marginBottom: '16px', fontSize: '12px', fontFamily: 'monospace' }}>{'>'} UPLINK_CONTROLLER</div>

              {networkConnected ? (
                <>
                  <div style={{ color: '#22c55e', marginBottom: '16px', fontSize: '12px', fontFamily: 'monospace' }}>{'>'} LINK_ESTABLISHED: {networkIp}</div>
                  <MenuButton 
                    onClick={() => {
                      setActiveLocalView('CREATE')
                      setSelectedRoomId(null)
                    }} 
                    label="CREATE REMOTE" 
                    sub="Spin up node on host" 
                    active={activeLocalView === 'CREATE'}
                  />
                  <MenuButton 
                    onClick={() => {
                      setActiveLocalView('LOAD')
                      setSelectedRoomId(null)
                    }} 
                    label="REMOTE NODES" 
                    sub="Browse active simulation nodes" 
                    active={activeLocalView === 'LOAD' || activeLocalView === 'JOIN' || activeLocalView === 'EDIT'}
                  />
                  <MenuButton 
                    onClick={() => {
                      setRemoteRooms([])
                      setSelectedRoomId(null)
                      setNetworkConnected(false)
                      setActiveLocalView('IDLE')
                      localStorage.removeItem('if_network_target')
                    }} 
                    label="DISCONNECT" 
                    sub="Sever uplink and return" 
                    secondary
                  />
                </>
              ) : (
                <>
                  <div style={{ marginBottom: '24px' }}>
                    <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '8px', fontFamily: 'monospace' }}>TARGET_IP:PORT</div>
                    <input 
                      type="text"
                      value={networkIp}
                      onChange={(e) => setNetworkIp(e.target.value)}
                      className="cyber-input"
                      style={{
                        width: '100%',
                        height: '44px',
                        background: 'var(--panel-bg)',
                        border: '1px solid var(--terminal-border)',
                        color: 'var(--terminal-text)',
                        padding: '0 16px',
                        fontFamily: 'monospace',
                        fontSize: '16px',
                        boxSizing: 'border-box'
                      }}
                    />
                  </div>

                  <MenuButton 
                    onClick={handleJoinNetwork} 
                    label={networkScanning ? "SCANNING..." : "INITIATE UPLINK"} 
                    sub="Connect to remote host" 
                    disabled={networkScanning || !networkIp}
                  />
                  <MenuButton onClick={() => setActiveView('MAIN')} label="RETURN" sub="Back to root" secondary />
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Right Workspace Area */}
      <div style={{
        flex: 1,
        position: 'relative',
        zIndex: 5,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px'
      }}>
        {activeLocalView !== 'IDLE' && (
          <div className="cyber-card" style={{ 
            width: '640px',
            maxHeight: '85vh', 
            background: 'rgba(15, 23, 42, 0.9)',
            backdropFilter: 'blur(20px)',
            border: '1px solid var(--terminal-border)',
            padding: '40px',
            display: 'flex',
            flexDirection: 'column',
            position: 'relative',
            boxShadow: '0 0 60px rgba(0,0,0,0.6)',
            overflow: 'hidden'
          }}>
            {/* 窗口头部装饰 */}
            <div style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center',
              marginBottom: '32px',
              paddingBottom: '16px',
              borderBottom: '2px solid rgba(59, 130, 246, 0.2)'
            }}>
              <div style={{ color: 'var(--terminal-info)', fontSize: '14px', fontFamily: 'monospace', fontWeight: 'bold', letterSpacing: '4px' }}>
                {activeLocalView === 'LOAD' && !selectedRoomId && '>> ARCHIVE_BROWSER'}
                {activeLocalView === 'CREATE' && '>> NODE_INITIALIZER'}
                {activeLocalView === 'EDIT' && '>> PROTOCOL_CONFIGURATOR'}
                {activeLocalView === 'JOIN' && '>> AUTHENTICATION_TERMINAL'}
                {activeLocalView === 'LOAD' && selectedRoomId && '>> AUTHENTICATION_TERMINAL'}
              </div>
              <button 
                onClick={() => {
                  setActiveLocalView('IDLE')
                  setSelectedRoomId(null)
                }}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#64748b',
                  cursor: 'pointer',
                  fontSize: '18px',
                  fontFamily: 'monospace',
                  transition: 'color 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = 'var(--terminal-error)'}
                onMouseLeave={(e) => e.currentTarget.style.color = '#64748b'}
              >
                [X]
              </button>
            </div>

            {/* 窗口主体内容 */}
            <div style={{ flex: 1, overflowY: 'auto', paddingRight: '8px', scrollbarWidth: 'thin' }}>
              {/* 1. 列表模式 */}
              {activeLocalView === 'LOAD' && !selectedRoomId && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {(activeView === 'LOCAL' ? localRooms : remoteRooms).length === 0 ? (
                    <div style={{ padding: '60px 0', textAlign: 'center', color: '#64748b', fontStyle: 'italic', fontFamily: 'monospace' }}>
                      {'>'} NO_ACTIVE_NODES_DETECTED
                    </div>
                  ) : (activeView === 'LOCAL' ? localRooms : remoteRooms).map(room => (
                    <div 
                      key={room.room_id}
                      onClick={() => setSelectedRoomId(room.room_id)}
                      onDoubleClick={() => {
                        setSelectedRoomId(room.room_id)
                        setActiveLocalView('JOIN')
                      }}
                      style={{
                        padding: '20px',
                        background: selectedRoomId === room.room_id ? 'rgba(59, 130, 246, 0.15)' : 'rgba(0,0,0,0.3)',
                        border: `1px solid ${selectedRoomId === room.room_id ? 'var(--terminal-info)' : 'var(--terminal-border)'}`,
                        cursor: 'pointer',
                        transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                        position: 'relative'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <div style={{ fontSize: '18px', fontWeight: 'bold', color: selectedRoomId === room.room_id ? '#fff' : '#e2e8f0', fontFamily: 'monospace' }}>
                          {room.name}
                        </div>
                        <div style={{ display: 'flex', gap: '16px' }}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              setSelectedRoomId(room.room_id)
                              syncRoomEditorFromMeta(room)
                              setActiveLocalView('EDIT')
                            }}
                            style={{ background: 'transparent', border: 'none', color: 'var(--terminal-info)', cursor: 'pointer', fontSize: '12px', textDecoration: 'underline', fontFamily: 'monospace' }}
                          >
                            CONFIG
                          </button>
                          {activeView === 'LOCAL' && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                handleDeleteSave(room.room_id)
                              }}
                              style={{ background: 'transparent', border: 'none', color: 'var(--terminal-error)', cursor: 'pointer', fontSize: '12px', textDecoration: 'underline', fontFamily: 'monospace' }}
                            >
                              PURGE
                            </button>
                          )}
                        </div>
                      </div>
                      <div style={{ fontSize: '11px', color: '#64748b', display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '8px', fontFamily: 'monospace' }}>
                        <div>CREATOR: <span style={{ color: '#94a3b8' }}>{room.player_id}</span></div>
                        <div>TIME_LIMIT: <span style={{ color: '#94a3b8' }}>{room.game_settings?.time_limit_seconds ? `${Math.round(room.game_settings.time_limit_seconds / 60)} MIN` : 'UNLIMITED'}</span></div>
                        <div>LAST_SYNC: <span style={{ color: '#94a3b8' }}>{room.updated_at ? new Date(room.updated_at).toLocaleString() : '--'}</span></div>
                        <div>NODE_ID: <span style={{ color: '#94a3b8' }}>{room.room_id.split('_')[1] || room.room_id}</span></div>
                      </div>
                      {selectedRoomId === room.room_id && (
                        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '4px', background: 'var(--terminal-info)', boxShadow: '0 0 10px var(--terminal-info)' }} />
                      )}
                    </div>
                  ))}
                  
                  {selectedRoomId && (
                    <div style={{ marginTop: '30px' }}>
                      <MenuButton 
                        onClick={() => setActiveLocalView('JOIN')} 
                        label="ESTABLISH UPLINK" 
                        sub="Begin synchronization sequence" 
                      />
                    </div>
                  )}
                </div>
              )}

              {/* 2. 创建/编辑模式 */}
              {(activeLocalView === 'CREATE' || activeLocalView === 'EDIT') && (
                <div style={{ padding: '4px' }}>
                  {renderRoomSettings(activeLocalView === 'EDIT')}
                  <div style={{ marginTop: '32px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <MenuButton 
                      onClick={activeLocalView === 'CREATE' ? handleCreateNewSimulation : handleUpdateRoomSettings} 
                      label={activeLocalView === 'CREATE' ? "COMMENCE INITIALIZATION" : "APPLY_CONFIG_PATCH"} 
                      sub={activeLocalView === 'CREATE' ? "Deploy new simulation environment" : "Update node protocol"} 
                    />
                    <MenuButton onClick={() => setActiveLocalView('LOAD')} label="ABORT_OPERATION" sub="Discard changes and return" secondary />
                  </div>
                </div>
              )}

              {/* 3. 加入模式 */}
              {(activeLocalView === 'JOIN' || (activeLocalView === 'LOAD' && selectedRoomId)) && (
                <div style={{ maxWidth: '440px', margin: '40px auto' }}>
                  <div style={{ marginBottom: '32px' }}>
                    <div style={{ fontSize: '12px', color: 'var(--terminal-info)', marginBottom: '12px', fontFamily: 'monospace', textAlign: 'center', letterSpacing: '2px' }}>AUTHENTICATING PLAYER_ID</div>
                    <input 
                      autoFocus
                      type="text"
                      value={inputPlayerId}
                      onChange={(e) => setInputPlayerId(e.target.value.toUpperCase())}
                      placeholder="ENTER_ID"
                      className="cyber-input"
                      style={{
                        width: '100%',
                        height: '60px',
                        background: 'rgba(0,0,0,0.5)',
                        border: `2px solid ${isInputValid ? 'var(--terminal-info)' : 'var(--terminal-error)'}`,
                        color: 'var(--terminal-text)',
                        padding: '0 20px',
                        fontFamily: 'monospace',
                        fontSize: '28px',
                        boxSizing: 'border-box',
                        letterSpacing: '8px',
                        textAlign: 'center',
                        textShadow: isInputValid ? '0 0 10px rgba(59, 130, 246, 0.5)' : 'none'
                      }}
                    />
                    <div style={{ display: 'flex', justifyContent: 'center', marginTop: '12px' }}>
                      {!isInputValid ? (
                         <div style={{ fontSize: '10px', color: 'var(--terminal-error)', fontFamily: 'monospace' }}>
                           !! ERROR: ID_LENGTH_VIOLATION [3-20] !!
                         </div>
                      ) : (
                         <div style={{ fontSize: '10px', color: '#22c55e', fontFamily: 'monospace' }}>
                           READY_FOR_SYNCHRONIZATION
                         </div>
                      )}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <MenuButton 
                      onClick={handleJoinSelectedSimulation} 
                      label="ESTABLISH_LINK" 
                      sub="Authorize and connect" 
                      disabled={!isInputValid}
                    />
                    <MenuButton onClick={() => { setActiveLocalView('LOAD'); setSelectedRoomId(null); }} label="BROWSER_BACK" sub="Return to archive list" secondary />
                  </div>
                </div>
              )}
            </div>

            {/* 窗口底部装饰 */}
            <div style={{ 
              marginTop: '32px', 
              fontSize: '10px', 
              color: 'rgba(148,163,184,0.3)', 
              fontFamily: 'monospace',
              display: 'flex',
              justifyContent: 'space-between',
              borderTop: '1px solid rgba(148,163,184,0.1)',
              paddingTop: '16px'
            }}>
              <div style={{ display: 'flex', gap: '20px' }}>
                <span>SYS_REF: {activeView}::{activeLocalView}</span>
                <span>ENC: AES_256_GCM</span>
              </div>
              <span>CONNECTION_STATUS: STABLE</span>
            </div>
          </div>
        )}

        {/* 装饰性背景，当没有窗口打开时显示 */}
        {activeLocalView === 'IDLE' && (
          <div style={{ 
            textAlign: 'center', 
            opacity: 0.15, 
            pointerEvents: 'none',
            userSelect: 'none'
          }}>
            <div style={{ fontSize: '180px', color: 'var(--terminal-info)', textShadow: '0 0 30px rgba(59, 130, 246, 0.3)' }}>❂</div>
            <div style={{ fontSize: '16px', fontFamily: 'monospace', marginTop: '30px', letterSpacing: '8px', color: 'var(--terminal-info)' }}>
              AWAITING_COMMAND_INPUT
            </div>
          </div>
        )}
      </div>

      {showSettings && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          zIndex: 100,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          backdropFilter: 'blur(8px)'
        }}>
          <SettingsModal actorId="host" open={showSettings} onClose={() => setShowSettings(false)} />
        </div>
      )}
    </div>
  )
}

function MenuButton({ 
  onClick, 
  label, 
  sub, 
  disabled = false,
  secondary = false,
  active = false
}: { 
  onClick: () => void, 
  label: string, 
  sub: string, 
  disabled?: boolean,
  secondary?: boolean,
  active?: boolean
}) {
  const [hovered, setHovered] = useState(false)

  const baseColor = secondary ? '#94a3b8' : 'var(--terminal-info)'

  return (
    <div 
      onClick={disabled ? undefined : onClick}
      onMouseEnter={() => !disabled && setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '16px 24px',
        background: active ? 'rgba(59, 130, 246, 0.1)' : (hovered ? 'var(--terminal-border)' : 'var(--panel-bg)'),
        borderLeft: `4px solid ${active ? 'var(--terminal-info)' : (hovered ? baseColor : (disabled ? 'transparent' : 'var(--terminal-border)'))}`,
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'all 0.15s ease',
        opacity: disabled ? 0.4 : 1,
        position: 'relative',
        overflow: 'hidden',
        borderRadius: '2px',
        marginBottom: '4px'
      }}
    >
      <div style={{ 
        fontSize: '16px', 
        fontWeight: 600, 
        color: active ? 'var(--terminal-info)' : (hovered ? '#fff' : (secondary ? '#cbd5e1' : 'var(--terminal-text)')),
        letterSpacing: '0.5px',
        marginBottom: '4px',
        fontFamily: 'Inter, sans-serif'
      }}>
        {label}
      </div>
      <div style={{ 
        fontSize: '12px', 
        color: active ? 'rgba(59, 130, 246, 0.7)' : (hovered ? '#94a3b8' : '#64748b'),
        fontFamily: 'Inter, sans-serif'
      }}>
        {sub}
      </div>
      {active && (
        <div style={{ 
          position: 'absolute', 
          right: '16px', 
          top: '50%', 
          transform: 'translateY(-50%)',
          color: 'var(--terminal-info)',
          fontSize: '12px'
        }}>
          ACTIVE_SESSION ►
        </div>
      )}
    </div>
  )
}
