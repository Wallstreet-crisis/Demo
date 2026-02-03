import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Api, ApiError } from '../api'

const PLAYER_ID_RE = /^[a-zA-Z0-9_]{3,20}$/

export default function OnboardingPage() {
  const nav = useNavigate()

  const [err, setErr] = useState<string>('')
  const [playerId, setPlayerId] = useState<string>('')
  const [casteId, setCasteId] = useState<string>('')
  const [initialCash, setInitialCash] = useState<string>('')

  const canSubmit = useMemo(() => {
    if (!PLAYER_ID_RE.test(playerId)) return false
    if (initialCash.trim() === '') return true
    const n = Number(initialCash)
    return Number.isFinite(n) && n >= 0
  }, [playerId, initialCash])

  async function submit(): Promise<void> {
    setErr('')

    if (!PLAYER_ID_RE.test(playerId)) {
      setErr('player_id must match ^[a-zA-Z0-9_]{3,20}$')
      return
    }

    const cash = initialCash.trim() === '' ? undefined : Number(initialCash)
    if (cash !== undefined && (!Number.isFinite(cash) || cash < 0)) {
      setErr('initial_cash must be a non-negative number')
      return
    }

    try {
      await Api.playersBootstrap({
        player_id: playerId,
        caste_id: casteId.trim() ? casteId.trim() : undefined,
        initial_cash: cash,
      })

      window.localStorage.setItem('if.playerId', playerId)
      if (casteId.trim()) window.localStorage.setItem('if.casteId', casteId.trim())
      else window.localStorage.removeItem('if.casteId')
      if (cash !== undefined) window.localStorage.setItem('if.initialCash', String(cash))
      else window.localStorage.removeItem('if.initialCash')

      nav('/market', { replace: true })
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="card" style={{ textAlign: 'left' }}>
      <h3 style={{ marginTop: 0 }}>Create / Select Player</h3>

      <div style={{ color: '#666' }}>
        First time here: choose a <code>player_id</code>.
      </div>

      <div style={{ marginTop: 12, display: 'grid', gap: 10, maxWidth: 520 }}>
        <label style={{ display: 'grid', gap: 6 }}>
          <div>player_id</div>
          <input value={playerId} onChange={(e) => setPlayerId(e.target.value)} placeholder="alice" />
          <div style={{ fontSize: 12, color: '#888' }}>Allowed: a-z A-Z 0-9 _ , length 3-20</div>
        </label>

        <label style={{ display: 'grid', gap: 6 }}>
          <div>caste_id (optional)</div>
          <input value={casteId} onChange={(e) => setCasteId(e.target.value)} placeholder="wealthy | middle | common" />
        </label>

        <label style={{ display: 'grid', gap: 6 }}>
          <div>initial_cash (optional)</div>
          <input value={initialCash} onChange={(e) => setInitialCash(e.target.value)} placeholder="10000" />
          <div style={{ fontSize: 12, color: '#888' }}>If omitted, backend default applies.</div>
        </label>

        <button onClick={submit} disabled={!canSubmit}>
          Enter
        </button>

        {err ? <div style={{ color: 'crimson' }}>{err}</div> : null}
      </div>
    </div>
  )
}
