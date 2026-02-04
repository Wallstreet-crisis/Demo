import './App.css'

import { Navigate, Route, Routes } from 'react-router-dom'

import Layout from './app/Layout'
import DashboardPage from './pages/DashboardPage'
import AccountPage from './pages/AccountPage'
import ChatPage from './pages/ChatPage'
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

function App() {
  const [bootstrapErr, setBootstrapErr] = useState<string>('')

  const { playerId, casteId } = useAppSession()

  useEffect(() => {
    let canceled = false

    if (!playerId) {
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
  }, [playerId, casteId])

  return (
    <>
      {bootstrapErr ? (
        <div style={{ padding: 12, background: '#fff1f0', border: '1px solid #ffccc7', borderRadius: 8 }}>
          <strong>Bootstrap error:</strong> {bootstrapErr}
        </div>
      ) : null}

      <Routes>
        <Route path="/onboarding" element={<OnboardingPage />} />

        <Route element={<Layout />}>
          <Route
            index
            element={<Navigate to={playerId ? '/dashboard' : '/onboarding'} replace />}
          />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/trade" element={<TradePage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/news" element={<NewsPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/contracts" element={<ContractsPage />} />
          <Route path="/hosting" element={<HostingPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </>
  )
}

export default App
