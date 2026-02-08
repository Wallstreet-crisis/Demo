import './App.css'

import { Navigate, Route, Routes } from 'react-router-dom'

import Layout from './app/Layout'
import DashboardPage from './pages/DashboardPage'
import AccountPage from './pages/AccountPage'
import ChatPage from './pages/ChatPage'
import ContractDetailPage from './pages/ContractDetailPage'
import ContractsPage from './pages/ContractsPage'
import HostingPage from './pages/HostingPage'
import MarketPage from './pages/MarketPage'
import NewsPage from './pages/NewsPage'
import NotFoundPage from './pages/NotFoundPage'
import OnboardingPage from './pages/OnboardingPage'
import TradePage from './pages/TradePage'

import { useEffect, useState } from 'react'
import { Api, ApiError } from './api'
import { useAppSession } from './app/context'

const PLAYER_ID_RE = /^[a-zA-Z0-9_]{3,20}$/

function App() {
  const [bootstrapErr, setBootstrapErr] = useState<string>('')

  const { playerId, casteId } = useAppSession()
  const playerIdOk = !!playerId && PLAYER_ID_RE.test(playerId)

  useEffect(() => {
    let canceled = false

    if (!playerIdOk) {
      return () => {
        canceled = true
      }
    }

    const initialCashRaw = window.localStorage.getItem('if.initialCash')
    const initialCash = initialCashRaw ? Number(initialCashRaw) : undefined

    Api.playersBootstrap({
      player_id: playerId,
      caste_id: casteId || undefined,
      initial_cash: Number.isFinite(initialCash) ? initialCash : undefined,
    })
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
  }, [playerIdOk, playerId, casteId])

  return (
    <>
      {bootstrapErr ? (
        <div style={{ padding: 12, background: '#fff1f0', border: '1px solid #ffccc7', borderRadius: 8 }}>
          <strong>Bootstrap error:</strong> {bootstrapErr}
        </div>
      ) : null}

      <Routes>
        <Route path="/onboarding" element={<OnboardingPage />} />

        <Route element={playerIdOk ? <Layout /> : <Navigate to="/onboarding" replace />}>
          <Route
            index
            element={<Navigate to={playerIdOk ? '/dashboard' : '/onboarding'} replace />}
          />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/trade" element={<TradePage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/news" element={<NewsPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/contracts" element={<ContractsPage />} />
          <Route path="/contracts/:contractId" element={<ContractDetailPage />} />
          <Route path="/hosting" element={<HostingPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </>
  )
}

export default App
