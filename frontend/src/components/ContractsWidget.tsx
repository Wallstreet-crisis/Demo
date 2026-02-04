import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Api, ApiError, type ContractAgentDraftResponse, type ContractParty, type ContractBriefResponse } from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'
import CyberWidget from './CyberWidget'

export default function ContractsWidget({ isFocused }: { isFocused?: boolean }) {
  void isFocused
  const { playerId } = useAppSession()
  const { notify } = useNotification()
  const [loading, setLoading] = useState(false)
  const [naturalLanguage, setNaturalLanguage] = useState('')
  const [draft, setDraft] = useState<ContractAgentDraftResponse | null>(null)
  const [isEditingDraft, setIsEditingDraft] = useState(false)
  const [editedDraftJson, setEditedDraftJson] = useState('')
  const [aiEditInstruction, setAiEditInstruction] = useState('')
  const [versionHistory, setVersionHistory] = useState<string[]>([])

  // Mentions state (replicated from ChatWidget)
  const [showMentionList, setShowMentionList] = useState(false)
  const [mentionType, setMentionType] = useState<'PLAYER' | 'CONTRACT' | null>(null)
  const [mentionQuery, setMentionQuery] = useState('')
  const [mentionIndex, setMentionIndex] = useState(0)
  const [players, setPlayers] = useState<string[]>([])
  const [contracts, setContracts] = useState<ContractBriefResponse[]>([])
  
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const fetchMentionsData = useCallback(async () => {
    if (!playerId) return
    try {
      const [pRes, cRes] = await Promise.all([
        Api.listPlayers(50),
        Api.listContracts(playerId, 50)
      ])
      setPlayers(pRes.items)
      setContracts(cRes.items)
    } catch (e) {
      console.error('Mention data fetch failed', e)
    }
  }, [playerId])

  useEffect(() => {
    if (isFocused) {
      fetchMentionsData()
    }
  }, [isFocused, fetchMentionsData])

  const handleInputChange = (val: string) => {
    setNaturalLanguage(val)
    const cursor = inputRef.current?.selectionStart || 0

    // Detect @ for players
    const lastAt = val.lastIndexOf('@', cursor - 1)
    if (lastAt !== -1 && (lastAt === 0 || val[lastAt - 1] === ' ')) {
      const query = val.slice(lastAt + 1, cursor)
      if (!query.includes(' ')) {
        setMentionType('PLAYER')
        setMentionQuery(query)
        setMentionIndex(0)
        setShowMentionList(true)
        return
      }
    }

    // Detect # for contracts
    const lastHash = val.lastIndexOf('#', cursor - 1)
    if (lastHash !== -1 && (lastHash === 0 || val[lastHash - 1] === ' ')) {
      const query = val.slice(lastHash + 1, cursor)
      if (!query.includes(' ')) {
        setMentionType('CONTRACT')
        setMentionQuery(query)
        setMentionIndex(0)
        setShowMentionList(true)
        return
      }
    }

    setShowMentionList(false)
  }

  const filteredItems = useMemo(() => {
    if (mentionType === 'PLAYER') {
      return players.filter(p => p.toLowerCase().includes(mentionQuery.toLowerCase()));
    } else if (mentionType === 'CONTRACT') {
      return contracts.filter(c => c.title.toLowerCase().includes(mentionQuery.toLowerCase()) || c.contract_id.includes(mentionQuery));
    }
    return [];
  }, [mentionType, players, contracts, mentionQuery]);

  const selectMention = (item: string | ContractBriefResponse) => {
    const cursor = inputRef.current?.selectionStart || 0
    let replacement = ''
    let startIdx = 0

    if (mentionType === 'PLAYER') {
      replacement = `@${item} `
      startIdx = naturalLanguage.lastIndexOf('@', cursor - 1)
    } else {
      const c = item as ContractBriefResponse
      replacement = `#${c.contract_id} `
      startIdx = naturalLanguage.lastIndexOf('#', cursor - 1)
    }

    const newVal = naturalLanguage.slice(0, startIdx) + replacement + naturalLanguage.slice(cursor)
    setNaturalLanguage(newVal)
    setShowMentionList(false)
    inputRef.current?.focus()
  }

  const handleDraft = async () => {
    if (!naturalLanguage.trim()) return
    setDraft(null)
    setLoading(true)
    try {
      const res = await Api.contractAgentDraft({
        actor_id: `user:${playerId}`,
        natural_language: naturalLanguage
      })
      setDraft(res)
      setEditedDraftJson(JSON.stringify(res.contract_create, null, 2))
      setIsEditingDraft(false)
      setAiEditInstruction('')
      setVersionHistory([JSON.stringify(res.contract_create, null, 2)])
      notify('success', 'DRAFT_GENERATED')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  const handleAppendAiEdit = async () => {
    if (!draft || !playerId) return
    const instruction = aiEditInstruction.trim()
    if (!instruction) return
    setLoading(true)
    try {
      let base: Record<string, unknown>
      try {
        base = JSON.parse(editedDraftJson || '{}')
      } catch {
        notify('error', 'INVALID_JSON_FORMAT')
        return
      }

      const res = await Api.contractAgentAppendEdit({
        actor_id: `user:${playerId}`,
        base_contract_create: base,
        instruction,
      })

      setDraft(res)
      const nextJson = JSON.stringify(res.contract_create, null, 2)
      setEditedDraftJson(nextJson)
      setIsEditingDraft(false)
      setAiEditInstruction('')
      setVersionHistory(prev => [...prev, nextJson])
      notify('success', 'AI_EDIT_APPLIED')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  const rollbackVersion = (idx: number) => {
    const v = versionHistory[idx]
    if (!v) return
    setEditedDraftJson(v)
    setIsEditingDraft(true)
  }

  const handleCreate = async () => {
    if (!draft) return
    setLoading(true)
    try {
      let finalContractCreate = draft.contract_create
      if (isEditingDraft) {
        try {
          finalContractCreate = JSON.parse(editedDraftJson)
        } catch {
          notify('error', 'INVALID_JSON_FORMAT')
          setLoading(false)
          return
        }
      }

      const parties: ContractParty[] = Array.isArray(finalContractCreate.parties) 
        ? finalContractCreate.parties.map((p: string | ContractParty) => typeof p === 'string' ? { party_id: p, role: 'PARTY' } : p)
        : []

      const res = await Api.contractCreate({
        actor_id: `user:${playerId}`,
        kind: finalContractCreate.kind as string,
        title: finalContractCreate.title as string,
        terms: finalContractCreate.terms as Record<string, unknown>,
        parties: parties,
        required_signers: finalContractCreate.required_signers as string[],
        participation_mode: finalContractCreate.participation_mode as string || null,
        invited_parties: finalContractCreate.invited_parties as string[] || null,
      })
      notify('success', 'CONTRACT_ESTABLISHED')
      
      // Auto-share to chat if established
      try {
        await Api.chatPublicSend({
          sender_id: `user:${playerId}`,
          message_type: 'TEXT',
          content: `建立新契约: #${res.contract_id} (${finalContractCreate.title})`,
          payload: { referenced_contract_id: res.contract_id }
        })
      } catch (e) {
        console.error('Failed to auto-share contract to chat', e)
      }

      setDraft(null)
      setNaturalLanguage('')
      setIsEditingDraft(false)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <CyberWidget 
      title="SMART_CONTRACT_AGENT" 
      subtitle="AI_LEGAL_PROCUREMENT"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', position: 'relative' }}>
        {/* Mention List UI (replicated from ChatWidget) */}
        {showMentionList && (
          <div style={{
            position: 'absolute',
            bottom: '100%',
            left: 0,
            right: 0,
            background: 'rgba(10, 15, 25, 0.98)',
            border: '1px solid var(--terminal-info)',
            boxShadow: '0 -5px 25px rgba(59, 130, 246, 0.4)',
            zIndex: 2000,
            maxHeight: '150px',
            overflowY: 'auto',
            marginBottom: '8px',
            borderRadius: '4px',
            backdropFilter: 'blur(8px)'
          }} className="custom-scrollbar">
            {mentionType === 'PLAYER' ? (
              (filteredItems as string[]).map((p, idx) => {
                const isSelected = mentionIndex === idx;
                return (
                  <div 
                    key={p} 
                    onClick={() => selectMention(p)}
                    style={{ 
                      padding: '8px 12px', 
                      cursor: 'pointer', 
                      borderBottom: '1px solid rgba(59, 130, 246, 0.1)',
                      fontSize: '11px',
                      background: isSelected ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
                      color: isSelected ? '#fff' : '#cbd5e1',
                    }}
                  >
                    @{p}
                  </div>
                );
              })
            ) : (
              (filteredItems as ContractBriefResponse[]).map((c, idx) => {
                const isSelected = mentionIndex === idx;
                return (
                  <div 
                    key={c.contract_id} 
                    onClick={() => selectMention(c)}
                    style={{ 
                      padding: '8px 12px', 
                      cursor: 'pointer', 
                      borderBottom: '1px solid rgba(59, 130, 246, 0.1)',
                      background: isSelected ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
                      color: isSelected ? '#fff' : '#cbd5e1',
                    }}
                  >
                    #{c.title} ({c.contract_id.slice(0, 8)})
                  </div>
                );
              })
            )}
          </div>
        )}

        <textarea
          ref={inputRef}
          className="cyber-input"
          style={{ 
            width: '100%', 
            minHeight: isFocused ? '120px' : '60px', 
            fontSize: '12px', 
            background: 'var(--terminal-bg)',
            resize: 'none',
            border: '1px solid var(--terminal-border)',
            padding: '10px',
            transition: 'height 0.3s'
          }}
          placeholder="DESCRIBE_TERMS: e.g. 'Bet 1000 cash with @bob on #BLUEGOLD > 150'"
          value={naturalLanguage}
          onChange={e => handleInputChange(e.target.value)}
          onKeyDown={e => {
            if (showMentionList && filteredItems.length > 0) {
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                setMentionIndex(prev => (prev + 1) % filteredItems.length);
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setMentionIndex(prev => (prev - 1 + filteredItems.length) % filteredItems.length);
              } else if (e.key === 'Enter' || e.key === 'Tab') {
                e.preventDefault();
                selectMention(filteredItems[mentionIndex]);
              } else if (e.key === 'Escape') {
                setShowMentionList(false);
              }
              return;
            }
          }}
        />
        
        {isFocused && (
          <button 
            className="cyber-button"
            onClick={handleDraft} 
            disabled={loading || !naturalLanguage.trim()}
            style={{ 
              fontSize: '12px', 
              padding: '10px',
              background: 'var(--terminal-info)',
              borderColor: 'var(--terminal-info)',
              color: '#fff',
              fontWeight: '600'
            }}
          >
            {loading ? 'ANALYZING_PROTOCOL...' : 'GENERATE_LEGAL_DRAFT'}
          </button>
        )}

        {!isFocused && !draft && (
          <div style={{ fontSize: '10px', color: '#64748b', textAlign: 'center', opacity: 0.6 }}>
            [ZOOM_TO_ENGAGE_AI_DRAFTING]
          </div>
        )}

        {draft && (
          <div style={{ 
            marginTop: '5px', 
            padding: '12px', 
            border: `1px solid ${isEditingDraft ? 'var(--terminal-warn)' : 'var(--terminal-success)'}`, 
            background: 'rgba(16, 185, 129, 0.05)',
            fontSize: '12px',
            borderRadius: '2px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <div style={{ fontWeight: 'bold', color: isEditingDraft ? 'var(--terminal-warn)' : 'var(--terminal-success)', fontSize: '11px' }}>
                {isEditingDraft ? 'MANUAL_EDIT_MODE' : 'DRAFT_VALIDATED'}
              </div>
              <button 
                onClick={() => setIsEditingDraft(!isEditingDraft)}
                style={{ fontSize: '9px', background: 'transparent', border: '1px solid #64748b', color: '#64748b', padding: '2px 6px', cursor: 'pointer' }}
              >
                {isEditingDraft ? 'VIEW_EXPLANATION' : 'EDIT_JSON'}
              </button>
            </div>

            {isEditingDraft ? (
              <textarea
                className="cyber-input"
                style={{ 
                  width: '100%', minHeight: '150px', fontSize: '11px', fontFamily: 'monospace',
                  background: '#000', color: '#52c41a', padding: '8px', border: '1px solid var(--terminal-warn)'
                }}
                value={editedDraftJson}
                onChange={e => setEditedDraftJson(e.target.value)}
              />
            ) : (
              <div style={{ color: '#cbd5e1', marginBottom: '12px', lineHeight: '1.4' }}>{draft.explanation}</div>
            )}

            <div style={{ display: 'grid', gap: '8px', marginTop: '10px' }}>
              <input
                className="cyber-input"
                value={aiEditInstruction}
                onChange={e => setAiEditInstruction(e.target.value)}
                placeholder="AI 追加编辑指令（会把当前 JSON 作为上下文）..."
                style={{
                  height: '34px',
                  background: 'rgba(15, 23, 42, 0.8)',
                  border: '1px solid rgba(59, 130, 246, 0.3)',
                }}
                disabled={loading}
              />
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', justifyContent: 'space-between' }}>
                <button
                  className="cyber-button"
                  onClick={handleAppendAiEdit}
                  disabled={loading || !aiEditInstruction.trim()}
                  style={{ fontSize: '11px', padding: '4px 12px', background: 'var(--terminal-info)', borderColor: 'var(--terminal-info)', color: '#fff' }}
                >
                  AI 追加编辑
                </button>
                {versionHistory.length > 1 && (
                  <select
                    value={''}
                    onChange={e => {
                      const v = e.target.value
                      if (!v) return
                      const idx = Number(v)
                      if (Number.isFinite(idx)) rollbackVersion(idx)
                      e.currentTarget.value = ''
                    }}
                    style={{
                      background: 'rgba(15, 23, 42, 0.8)',
                      color: '#cbd5e1',
                      border: '1px solid rgba(100, 116, 139, 0.5)',
                      padding: '6px 8px',
                      fontSize: '11px',
                      borderRadius: '2px'
                    }}
                  >
                    <option value="">回滚版本...</option>
                    {versionHistory.map((_, idx) => (
                      <option key={idx} value={String(idx)}>v{idx + 1}</option>
                    ))}
                  </select>
                )}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '12px' }}>
              <span style={{ fontSize: '10px', color: '#64748b' }}>RISK_LEVEL: <span style={{ color: draft.risk_rating === 'HIGH' ? 'var(--terminal-error)' : 'var(--terminal-success)' }}>{draft.risk_rating}</span></span>
              <button 
                className="cyber-button"
                onClick={handleCreate}
                style={{ fontSize: '11px', padding: '4px 12px', background: 'var(--terminal-success)', borderColor: 'var(--terminal-success)', color: '#fff' }}
              >
                {isEditingDraft ? 'SAVE_AND_EXECUTE' : 'EXECUTE_DEPLOYMENT'}
              </button>
            </div>
          </div>
        )}
      </div>
    </CyberWidget>
  )
}
