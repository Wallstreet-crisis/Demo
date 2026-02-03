import { useState } from 'react'
import { Api, ApiError, type ContractAgentDraftResponse } from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'
import CyberWidget from './CyberWidget'

export default function ContractsWidget() {
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
      await Api.contractCreate({
        actor_id: `user:${playerId}`,
        kind: draft.contract_create.kind as string,
        title: draft.contract_create.title as string,
        terms: draft.contract_create.terms as Record<string, unknown>,
        parties: draft.contract_create.parties as string[],
        required_signers: draft.contract_create.required_signers as string[],
        participation_mode: draft.contract_create.participation_mode as string || null,
        invited_parties: draft.contract_create.invited_parties as string[] || null,
      })
      notify('success', 'CONTRACT_ESTABLISHED')
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
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <textarea
          className="cyber-input"
          style={{ 
            width: '100%', 
            minHeight: '80px', 
            fontSize: '11px', 
            background: 'rgba(0,0,0,0.3)',
            resize: 'none'
          }}
          placeholder="DESCRIBE_TERMS: e.g. 'Bet 1000 cash with user:bob on BLUEGOLD > 150'"
          value={naturalLanguage}
          onChange={e => setNaturalLanguage(e.target.value)}
        />
        
        <button 
          className="cyber-button"
          onClick={handleDraft} 
          disabled={loading || !naturalLanguage.trim()}
          style={{ fontSize: '11px', padding: '8px' }}
        >
          {loading ? 'ANALYZING...' : 'GENERATE_DRAFT'}
        </button>

        {draft && (
          <div style={{ 
            marginTop: '10px', 
            padding: '10px', 
            border: '1px solid #52c41a', 
            background: 'rgba(82, 196, 26, 0.05)',
            fontSize: '11px'
          }}>
            <div style={{ fontWeight: 'bold', color: '#52c41a', marginBottom: '5px' }}>DRAFT_READY</div>
            <div style={{ opacity: 0.8, marginBottom: '10px' }}>{draft.explanation}</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '9px', opacity: 0.5 }}>RISK: {draft.risk_rating}</span>
              <button 
                className="cyber-button"
                onClick={handleCreate}
                style={{ fontSize: '9px', padding: '2px 8px', background: '#52c41a', color: '#000' }}
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
