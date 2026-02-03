import './App.css'

import { Navigate, Route, Routes } from 'react-router-dom'

import Layout from './app/Layout'
import { AppSessionProvider } from './app/context'
import AccountPage from './pages/AccountPage'
import ChatPage from './pages/ChatPage'
import MarketPage from './pages/MarketPage'
import NewsPage from './pages/NewsPage'
import NotFoundPage from './pages/NotFoundPage'
import TradePage from './pages/TradePage'

import { useEffect, useState } from 'react'
import { Api, ApiError } from './api'

function App() {
  const [bootstrapErr, setBootstrapErr] = useState<string>('')

  const [playerId, setPlayerId] = useState<string>(() => {
    const key = 'if.playerId'
    const existing = window.localStorage.getItem(key)
    if (existing) return existing

    const id = `p_${crypto.randomUUID().slice(0, 8)}`
    window.localStorage.setItem(key, id)
    return id
  })
  const [symbol, setSymbol] = useState<string>('BLUEGOLD')

  useEffect(() => {
    const key = 'if.playerId'
    window.localStorage.setItem(key, playerId)
  }, [playerId])

  useEffect(() => {
    let canceled = false

    Api.playersBootstrap({ player_id: playerId })
      .then(() => {
        if (canceled) return
        setBootstrapErr('')
      })
      .catch((e) => {
        if (canceled) return
        if (e instanceof ApiError) setBootstrapErr(`${e.status}: ${e.message}`)
        else setBootstrapErr(e instanceof Error ? e.message : String(e))
      })

    return () => {
      canceled = true
    }
  }, [playerId])

  return (
    <AppSessionProvider value={{ playerId, setPlayerId, symbol, setSymbol }}>
      {bootstrapErr ? (
        <div style={{ padding: 12, background: '#fff1f0', border: '1px solid #ffccc7', borderRadius: 8 }}>
          <strong>Bootstrap error:</strong> {bootstrapErr}
        </div>
      ) : null}

      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/market" replace />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/trade" element={<TradePage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/news" element={<NewsPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </AppSessionProvider>
  )
}

export default App
