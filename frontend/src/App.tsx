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

import { useState } from 'react'

function App() {
  const [playerId, setPlayerId] = useState<string>('alice')
  const [symbol, setSymbol] = useState<string>('BLUEGOLD')

  return (
    <AppSessionProvider value={{ playerId, setPlayerId, symbol, setSymbol }}>
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
