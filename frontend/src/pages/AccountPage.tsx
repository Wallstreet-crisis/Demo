import { useEffect, useState } from 'react'
import { Api, ApiError, type AccountValuationResponse, type PlayerAccountResponse } from '../api'
import { useAppSession } from '../app/context'

export default function AccountPage() {
  const { playerId } = useAppSession()
  const [err, setErr] = useState<string>('')
  const [snap, setSnap] = useState<PlayerAccountResponse | null>(null)
  const [val, setVal] = useState<AccountValuationResponse | null>(null)

  async function refresh(): Promise<void> {
    setErr('')
    try {
      const s = await Api.playerAccount(playerId)
      setSnap(s)
      const v = await Api.accountValuation(s.account_id, 1.0)
      setVal(v)
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playerId])

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Account Snapshot</h3>
        {err ? <div style={{ color: 'crimson' }}>{err}</div> : null}
        <button onClick={refresh}>Refresh</button>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{snap ? JSON.stringify(snap, null, 2) : 'N/A'}</pre>
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Valuation</h3>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{val ? JSON.stringify(val, null, 2) : 'N/A'}</pre>
      </div>
    </div>
  )
}
