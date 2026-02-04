import { useState } from 'react'
import { Api, ApiError, type ContractAgentDraftResponse, type ContractParty } from '../api'
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
      notify('success', 'DRAFT_GENERATED')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!draft) return
    setLoading(true)
    try {
      const parties: ContractParty[] = Array.isArray(draft.contract_create.parties) 
        ? draft.contract_create.parties.map((p: string | ContractParty) => typeof p === 'string' ? { party_id: p, role: 'PARTY' } : p)
        : []

      const res = await Api.contractCreate({
        actor_id: `user:${playerId}`,
        kind: draft.contract_create.kind as string,
        title: draft.contract_create.title as string,
        terms: draft.contract_create.terms as Record<string, unknown>,
        parties: parties,
        required_signers: draft.contract_create.required_signers as string[],
        participation_mode: draft.contract_create.participation_mode as string || null,
        invited_parties: draft.contract_create.invited_parties as string[] || null,
      })
      notify('success', 'CONTRACT_ESTABLISHED')
      
      // Auto-share to chat if established
      try {
        await Api.chatPublicSend({
          sender_id: `user:${playerId}`,
          message_type: 'TEXT',
          content: `建立新契约: #${res.contract_id} (${draft.contract_create.title})`,
          payload: { referenced_contract_id: res.contract_id }
        })
      } catch (e) {
        console.error('Failed to auto-share contract to chat', e)
      }

      setDraft(null)
      setNaturalLanguage('')
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
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <textarea
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
          placeholder="DESCRIBE_TERMS: e.g. 'Bet 1000 cash with user:bob on BLUEGOLD > 150'"
          value={naturalLanguage}
          onChange={e => setNaturalLanguage(e.target.value)}
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
            border: '1px solid var(--terminal-success)', 
            background: 'rgba(16, 185, 129, 0.05)',
            fontSize: '12px',
            borderRadius: '2px'
          }}>
            <div style={{ fontWeight: 'bold', color: 'var(--terminal-success)', marginBottom: '6px', fontSize: '11px' }}>DRAFT_VALIDATED</div>
            <div style={{ color: '#cbd5e1', marginBottom: '12px', lineHeight: '1.4' }}>{draft.explanation}</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10px', color: '#64748b' }}>RISK_LEVEL: <span style={{ color: draft.risk_rating === 'HIGH' ? 'var(--terminal-error)' : 'var(--terminal-success)' }}>{draft.risk_rating}</span></span>
              <button 
                className="cyber-button"
                onClick={handleCreate}
                style={{ fontSize: '11px', padding: '4px 12px', background: 'var(--terminal-success)', borderColor: 'var(--terminal-success)', color: '#fff' }}
              >
                EXECUTE_DEPLOYMENT
              </button>
            </div>
          </div>
        )}
      </div>
    </CyberWidget>
  )
}
