import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Api } from '../api'
import { useAppSession } from '../app/context'
import SettingsModal from '../components/SettingsModal'

export default function MainMenuPage() {
  const nav = useNavigate()
  const { setPlayerId: setGlobalPlayerId, setCasteId, setRoomId } = useAppSession()
  const [activeView, setActiveView] = useState<'MAIN' | 'LOCAL' | 'NETWORK'>('MAIN')
  const [networkIp, setNetworkIp] = useState('127.0.0.1:8010')
  const [inputPlayerId, setInputPlayerId] = useState('')
  const [localRooms, setLocalRooms] = useState<any[]>([])
  const [remoteRooms, setRemoteRooms] = useState<any[]>([])
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null)
  const [editingRoomId, setEditingRoomId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  const [isTransitioning, setIsTransitioning] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [networkScanning, setNetworkScanning] = useState(false)

  const isInputValid = inputPlayerId.length >= 3 && inputPlayerId.length <= 20

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
    if (activeView === 'LOCAL') {
      localStorage.removeItem('if_network_target')
      fetchLocalRooms()
      setSelectedRoomId(null)
      setEditingRoomId(null)
    } else if (activeView === 'NETWORK') {
      setRemoteRooms([])
      setSelectedRoomId(null)
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

  const handleRenameSave = async (roomId: string, newName: string) => {
    if (!newName.trim()) return
    try {
      await Api.updateRoomMeta(roomId, newName.trim())
      setEditingRoomId(null)
      fetchLocalRooms()
    } catch (e) {
      console.error('Failed to rename room:', e)
    }
  }

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

  const handleNewSimulation = async () => {
    if (!isInputValid) return
    setIsTransitioning(true)
    
    // UI 淡出动画通常需要 800ms
    // 我们并发启动建房请求和倒计时，等两者都完成了再跳转
    const animationPromise = new Promise(resolve => setTimeout(resolve, 800))
    localStorage.removeItem('if_network_target') // Reset network target to default
    const createRoomPromise = Api.createRoom({ player_id: inputPlayerId })

    try {
      const [, res] = await Promise.all([animationPromise, createRoomPromise])
      if (res.ok && res.room_id) {
        setRoomId(res.room_id)
        setGlobalPlayerId(inputPlayerId)
        setCasteId('' as any)
        nav('/onboarding')
      }
    } catch (e) {
      console.error('Failed to create new room:', e)
      setIsTransitioning(false)
      alert('Failed to initialize new simulation instance.')
    }
  }

  const handleResumeSimulation = () => {
    if (!selectedRoomId || !isInputValid) return
    setIsTransitioning(true)
    localStorage.removeItem('if_network_target') // Reset network target to default
    const animationPromise = new Promise(resolve => setTimeout(resolve, 800))
    const activatePromise = Api.activateRoom(selectedRoomId)
    const bootstrapPromise = activatePromise.then(() => Api.playersBootstrap({ player_id: inputPlayerId }))
    void Promise.all([animationPromise, bootstrapPromise])
      .then(() => {
        setRoomId(selectedRoomId)
        setGlobalPlayerId(inputPlayerId)
        nav('/dashboard')
      })
      .catch((e) => {
        console.error('Failed to resume simulation:', e)
        setIsTransitioning(false)
        alert('Failed to load simulation data for this player in the selected room.')
      })
  }

  const handleJoinNetwork = async () => {
    if (!isInputValid || !networkIp) return
    setNetworkScanning(true)
    
    // Save target before making request so ApiClient uses it
    localStorage.setItem('if_network_target', networkIp)

    try {
      const res = await Api.networkJoinCheck() as any
      if (res.ok && res.rooms && res.rooms.length > 0) {
        setRemoteRooms(res.rooms)
      } else {
        throw new Error('No active sessions found on target server.')
      }
    } catch (e) {
      console.error('Failed to connect to network target:', e)
      localStorage.removeItem('if_network_target')
      setRemoteRooms([])
      alert('Connection failed or no sessions found on remote host.')
    } finally {
      setNetworkScanning(false)
    }
  }

  const handleResumeNetworkSimulation = () => {
    if (!selectedRoomId || !isInputValid || !networkIp) return
    setIsTransitioning(true)
    localStorage.setItem('if_network_target', networkIp)
    const animationPromise = new Promise(resolve => setTimeout(resolve, 800))
    const bootstrapPromise = Api.playersBootstrap({ player_id: inputPlayerId })
    void Promise.all([animationPromise, bootstrapPromise])
      .then(() => {
        setRoomId(selectedRoomId)
        setGlobalPlayerId(inputPlayerId)
        nav('/dashboard')
      })
      .catch((e) => {
        console.error('Failed to join remote simulation:', e)
        localStorage.removeItem('if_network_target')
        setIsTransitioning(false)
        alert('Failed to join remote simulation for this player.')
      })
  }

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
              <div style={{ color: 'var(--terminal-info)', marginBottom: '16px', fontSize: '12px', fontFamily: 'monospace' }}>{'>'} SELECT STARTUP SEQUENCE</div>
              
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '8px', fontFamily: 'monospace' }}>PLAYER_ID</div>
                <input 
                  type="text"
                  value={inputPlayerId}
                  onChange={(e) => setInputPlayerId(e.target.value.toUpperCase())}
                  placeholder="3-20 ALPHANUMERIC"
                  className="cyber-input"
                  style={{
                    width: '100%',
                    height: '44px',
                    background: 'var(--panel-bg)',
                    border: `1px solid ${isInputValid ? 'var(--terminal-border)' : 'var(--terminal-error)'}`,
                    color: 'var(--terminal-text)',
                    padding: '0 16px',
                    fontFamily: 'monospace',
                    fontSize: '16px',
                    boxSizing: 'border-box',
                    letterSpacing: '2px'
                  }}
                />
              </div>

              <MenuButton 
                onClick={handleResumeSimulation} 
                label="RESUME SIMULATION" 
                sub={selectedRoomId ? `Join selected node` : 'No active save found'} 
                disabled={!selectedRoomId || !isInputValid}
              />
              <MenuButton 
                onClick={handleNewSimulation} 
                label="NEW SIMULATION" 
                sub="Initialize fresh instance" 
                disabled={!isInputValid}
              />
              <MenuButton onClick={() => setActiveView('MAIN')} label="RETURN" sub="Back to root" secondary />
            </>
          )}

          {activeView === 'NETWORK' && (
            <>
              <div style={{ color: 'var(--terminal-info)', marginBottom: '16px', fontSize: '12px', fontFamily: 'monospace' }}>{'>'} UPLINK CONFIGURATION</div>
              
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '8px', fontFamily: 'monospace' }}>PLAYER_ID</div>
                <input 
                  type="text"
                  value={inputPlayerId}
                  onChange={(e) => setInputPlayerId(e.target.value.toUpperCase())}
                  placeholder="3-20 ALPHANUMERIC"
                  className="cyber-input"
                  style={{
                    width: '100%',
                    height: '44px',
                    background: 'var(--panel-bg)',
                    border: `1px solid ${isInputValid ? 'var(--terminal-border)' : 'var(--terminal-error)'}`,
                    color: 'var(--terminal-text)',
                    padding: '0 16px',
                    fontFamily: 'monospace',
                    fontSize: '16px',
                    boxSizing: 'border-box',
                    letterSpacing: '2px'
                  }}
                />
              </div>

              {remoteRooms.length > 0 ? (
                <>
                  <div style={{ color: 'var(--terminal-info)', marginBottom: '16px', fontSize: '12px', fontFamily: 'monospace' }}>{'>'} REMOTE NODES FOUND</div>
                  <MenuButton 
                    onClick={handleResumeNetworkSimulation} 
                    label="JOIN SIMULATION" 
                    sub={selectedRoomId ? `Connect to node ${selectedRoomId}` : 'Select a node from list'} 
                    disabled={!selectedRoomId || !isInputValid}
                  />
                  <MenuButton 
                    onClick={() => {
                      setRemoteRooms([])
                      setSelectedRoomId(null)
                    }} 
                    label="RESCAN" 
                    sub="Scan for different IP" 
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
                    disabled={!isInputValid || networkScanning}
                  />
                  <MenuButton onClick={() => setActiveView('MAIN')} label="RETURN" sub="Back to root" secondary />
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Right Reserved Area for Animation / Panels */}
      <div style={{
        flex: 1,
        position: 'relative',
        zIndex: 5,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-start',
        paddingLeft: '40px'
      }}>
        {/* Local Saves List */}
        {activeView === 'LOCAL' && localRooms.length > 0 && (
          <div className="cyber-card" style={{ 
            width: '400px', 
            maxHeight: '60vh', 
            background: 'rgba(15, 23, 42, 0.8)',
            backdropFilter: 'blur(8px)',
            border: '1px solid var(--terminal-border)',
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            overflowY: 'auto'
          }}>
            <div style={{ color: 'var(--terminal-info)', fontSize: '12px', fontFamily: 'monospace', marginBottom: '8px' }}>
              {'>'} AVAILABLE LOCAL NODES
            </div>
            {localRooms.map(room => (
              <div 
                key={room.room_id}
                onClick={() => {
                  if (editingRoomId !== room.room_id) {
                    setSelectedRoomId(room.room_id)
                  }
                }}
                onDoubleClick={() => {
                  if (editingRoomId !== room.room_id && selectedRoomId === room.room_id && isInputValid) {
                    handleResumeSimulation()
                  }
                }}
                style={{
                  padding: '16px',
                  background: selectedRoomId === room.room_id ? 'rgba(59, 130, 246, 0.15)' : 'rgba(0,0,0,0.3)',
                  border: `1px solid ${selectedRoomId === room.room_id ? 'var(--terminal-info)' : 'var(--terminal-border)'}`,
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  position: 'relative'
                }}
              >
                {editingRoomId === room.room_id ? (
                  <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                    <input
                      autoFocus
                      type="text"
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRenameSave(room.room_id, editingName)
                        if (e.key === 'Escape') setEditingRoomId(null)
                      }}
                      className="cyber-input"
                      style={{
                        flex: 1,
                        height: '28px',
                        background: 'var(--panel-bg)',
                        border: '1px solid var(--terminal-info)',
                        color: 'var(--terminal-text)',
                        padding: '0 8px',
                        fontFamily: 'Inter, sans-serif',
                        fontSize: '14px',
                        boxSizing: 'border-box'
                      }}
                    />
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        handleRenameSave(room.room_id, editingName)
                      }}
                      style={{
                        background: 'var(--terminal-info)',
                        color: '#000',
                        border: 'none',
                        padding: '0 12px',
                        cursor: 'pointer',
                        fontWeight: 'bold',
                        fontSize: '12px'
                      }}
                    >
                      SAVE
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setEditingRoomId(null)
                      }}
                      style={{
                        background: 'transparent',
                        color: 'var(--terminal-text)',
                        border: '1px solid var(--terminal-border)',
                        padding: '0 12px',
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      X
                    </button>
                  </div>
                ) : (
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <div style={{ fontSize: '16px', fontWeight: 'bold', color: selectedRoomId === room.room_id ? '#fff' : '#e2e8f0' }}>
                      {room.name}
                    </div>
                    {selectedRoomId === room.room_id && (
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setEditingRoomId(room.room_id)
                            setEditingName(room.name)
                          }}
                          style={{
                            background: 'transparent',
                            border: 'none',
                            color: '#94a3b8',
                            cursor: 'pointer',
                            fontSize: '12px',
                            textDecoration: 'underline'
                          }}
                        >
                          RENAME
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleDeleteSave(room.room_id)
                          }}
                          style={{
                            background: 'transparent',
                            border: 'none',
                            color: 'var(--terminal-error)',
                            cursor: 'pointer',
                            fontSize: '12px',
                            textDecoration: 'underline'
                          }}
                        >
                          DELETE
                        </button>
                      </div>
                    )}
                  </div>
                )}
                <div style={{ fontSize: '11px', color: '#64748b', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>CREATOR:</span>
                    <span style={{ color: '#94a3b8' }}>{room.player_id}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>LAST SYNC:</span>
                    <span style={{ color: '#94a3b8' }}>{room.updated_at ? new Date(room.updated_at).toLocaleString() : '--'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>NODE ID:</span>
                    <span style={{ color: '#94a3b8' }}>{room.room_id.split('_')[1] || room.room_id}</span>
                  </div>
                </div>
                {selectedRoomId === room.room_id && (
                  <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '3px', background: 'var(--terminal-info)' }} />
                )}
              </div>
            ))}
          </div>
        )}

        {/* Remote Saves List */}
        {activeView === 'NETWORK' && remoteRooms.length > 0 && (
          <div className="cyber-card" style={{ 
            width: '400px', 
            maxHeight: '60vh', 
            background: 'rgba(15, 23, 42, 0.8)',
            backdropFilter: 'blur(8px)',
            border: '1px solid var(--terminal-border)',
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            overflowY: 'auto'
          }}>
            <div style={{ color: 'var(--terminal-info)', fontSize: '12px', fontFamily: 'monospace', marginBottom: '8px' }}>
              {'>'} AVAILABLE REMOTE NODES
            </div>
            {remoteRooms.map(room => (
              <div 
                key={room.room_id}
                onClick={() => setSelectedRoomId(room.room_id)}
                onDoubleClick={() => {
                  if (selectedRoomId === room.room_id && isInputValid) {
                    handleResumeNetworkSimulation()
                  }
                }}
                style={{
                  padding: '16px',
                  background: selectedRoomId === room.room_id ? 'rgba(59, 130, 246, 0.15)' : 'rgba(0,0,0,0.3)',
                  border: `1px solid ${selectedRoomId === room.room_id ? 'var(--terminal-info)' : 'var(--terminal-border)'}`,
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  position: 'relative'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                  <div style={{ fontSize: '16px', fontWeight: 'bold', color: selectedRoomId === room.room_id ? '#fff' : '#e2e8f0' }}>
                    {room.name}
                  </div>
                </div>
                <div style={{ fontSize: '11px', color: '#64748b', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>CREATOR:</span>
                    <span style={{ color: '#94a3b8' }}>{room.player_id}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>LAST SYNC:</span>
                    <span style={{ color: '#94a3b8' }}>{room.updated_at ? new Date(room.updated_at).toLocaleString() : '--'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>NODE ID:</span>
                    <span style={{ color: '#94a3b8' }}>{room.room_id.split('_')[1] || room.room_id}</span>
                  </div>
                </div>
                {selectedRoomId === room.room_id && (
                  <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '3px', background: 'var(--terminal-info)' }} />
                )}
              </div>
            ))}
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
  secondary = false
}: { 
  onClick: () => void, 
  label: string, 
  sub: string, 
  disabled?: boolean,
  secondary?: boolean
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
        background: hovered ? 'var(--terminal-border)' : 'var(--panel-bg)',
        borderLeft: `4px solid ${hovered ? baseColor : (disabled ? 'transparent' : 'var(--terminal-border)')}`,
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'all 0.15s ease',
        opacity: disabled ? 0.4 : 1,
        position: 'relative',
        overflow: 'hidden',
        borderRadius: '2px'
      }}
    >
      <div style={{ 
        fontSize: '16px', 
        fontWeight: 600, 
        color: hovered ? '#fff' : (secondary ? '#cbd5e1' : 'var(--terminal-text)'),
        letterSpacing: '0.5px',
        marginBottom: '4px',
        fontFamily: 'Inter, sans-serif'
      }}>
        {label}
      </div>
      <div style={{ 
        fontSize: '12px', 
        color: hovered ? '#94a3b8' : '#64748b',
        fontFamily: 'Inter, sans-serif'
      }}>
        {sub}
      </div>
    </div>
  )
}
