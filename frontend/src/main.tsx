import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App'
import { NotificationProvider } from './app/NotificationContext'
import { AppSessionProvider } from './app/context'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AppSessionProvider>
        <NotificationProvider>
          <App />
        </NotificationProvider>
      </AppSessionProvider>
    </BrowserRouter>
  </StrictMode>,
)
