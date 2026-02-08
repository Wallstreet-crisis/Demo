import { createContext, useContext, useState } from 'react'
import type { CasteId } from './constants'

const PLAYER_ID_RE = /^[a-zA-Z0-9_]{3,20}$/

export type AppSession = {
  playerId: string
  setPlayerId: (v: string) => void
  casteId: CasteId | ''
  setCasteId: (v: CasteId | '') => void
  symbol: string
  setSymbol: (v: string) => void
  aiHosting: boolean
  setAiHosting: (v: boolean) => void
}

const Ctx = createContext<AppSession | null>(null)

export function useAppSession(): AppSession {
  const v = useContext(Ctx)
  if (!v) throw new Error('AppSessionProvider missing')
  return v
}

export function AppSessionProvider({ children }: { children: React.ReactNode }) {
  const [playerId, setPlayerIdState] = useState<string>(() => {
    const raw = localStorage.getItem('if_player_id') || ''
    const v = raw.trim()
    if (!v) return ''
    if (!PLAYER_ID_RE.test(v)) {
      localStorage.removeItem('if_player_id')
      return ''
    }
    return v
  })
  const [casteId, setCasteIdState] = useState<CasteId | ''>(() => (localStorage.getItem('if_caste_id') as CasteId) || '')
  const [symbol, setSymbolState] = useState<string>(() => localStorage.getItem('if_symbol') || 'WST')
  const [aiHosting, setAiHostingState] = useState<boolean>(false)

  const setPlayerId = (v: string) => {
    const vv = String(v ?? '').trim()
    if (vv && !PLAYER_ID_RE.test(vv)) return
    setPlayerIdState(vv)
    if (vv) localStorage.setItem('if_player_id', vv)
    else localStorage.removeItem('if_player_id')
  }

  const setCasteId = (v: CasteId | '') => {
    setCasteIdState(v)
    if (v) localStorage.setItem('if_caste_id', v)
    else localStorage.removeItem('if_caste_id')
  }

  const setSymbol = (v: string) => {
    setSymbolState(v)
    if (v) localStorage.setItem('if_symbol', v)
    else localStorage.removeItem('if_symbol')
  }

  const setAiHosting = (v: boolean) => {
    setAiHostingState(v)
  }

  return (
    <Ctx.Provider value={{ playerId, setPlayerId, casteId, setCasteId, symbol, setSymbol, aiHosting, setAiHosting }}>
      {children}
    </Ctx.Provider>
  )
}
