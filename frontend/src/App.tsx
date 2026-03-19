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
import MainMenuPage from './pages/MainMenuPage'

import { useAppSession } from './app/context'

const PLAYER_ID_RE = /^[a-zA-Z0-9_]{3,20}$/

function App() {
  const { playerId } = useAppSession()
  const playerIdOk = !!playerId && PLAYER_ID_RE.test(playerId)

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/menu" replace />} />
      <Route path="/menu" element={<MainMenuPage />} />
      <Route path="/onboarding" element={<OnboardingPage />} />

      <Route element={playerIdOk ? <Layout /> : <Navigate to="/menu" replace />}>
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
  )
}

export default App
