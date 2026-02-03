import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

type NotificationType = 'success' | 'error' | 'info'

interface Notification {
  id: string
  type: NotificationType
  message: string
}

interface NotificationContextType {
  notify: (type: NotificationType, message: string) => void
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined)

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([])

  const notify = useCallback((type: NotificationType, message: string) => {
    const id = Math.random().toString(36).slice(2, 9)
    setNotifications((prev) => [...prev, { id, type, message }])
    
    // Auto remove after 4 seconds
    setTimeout(() => {
      setNotifications((prev) => prev.filter((n) => n.id !== id))
    }, 4000)
  }, [])

  return (
    <NotificationContext.Provider value={{ notify }}>
      {children}
      <div
        style={{
          position: 'fixed',
          top: 20,
          right: 20,
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          pointerEvents: 'none',
        }}
      >
        {notifications.map((n) => (
          <div
            key={n.id}
            style={{
              padding: '12px 20px',
              borderRadius: 8,
              color: '#fff',
              background:
                n.type === 'success' ? '#52c41a' : n.type === 'error' ? '#f5222d' : '#1890ff',
              boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              minWidth: 200,
              maxWidth: 400,
              pointerEvents: 'auto',
              animation: 'fadeIn 0.3s ease-out',
              fontSize: 14,
              fontWeight: 500,
            }}
          >
            {n.message}
          </div>
        ))}
      </div>
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateX(20px); }
          to { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </NotificationContext.Provider>
  )
}

export function useNotification() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotification must be used within a NotificationProvider')
  }
  return context
}
