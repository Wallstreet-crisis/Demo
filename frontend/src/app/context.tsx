import { createContext, useContext } from 'react'

export type AppSession = {
  playerId: string
  setPlayerId: (v: string) => void
  casteId: string
  setCasteId: (v: string) => void
  symbol: string
  setSymbol: (v: string) => void
}

const Ctx = createContext<AppSession | null>(null)

export function useAppSession(): AppSession {
  const v = useContext(Ctx)
  if (!v) throw new Error('AppSessionProvider missing')
  return v
}

export const AppSessionProvider = Ctx.Provider
