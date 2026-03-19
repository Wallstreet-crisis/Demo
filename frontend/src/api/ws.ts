export type WsMessageHandler = (payload: unknown) => void

export type WsClientConfig = {
  baseUrl?: string
  reconnectIntervalMs?: number
  maxRetries?: number
}

function getWsBaseUrl(baseUrl?: string): string {
  if (baseUrl) return baseUrl.replace(/^http/i, 'ws')
  const override = localStorage.getItem('if_network_target')
  if (override) {
    const httpUrl = override.startsWith('http') ? override : `http://${override}`
    return httpUrl.replace(/^http/i, 'ws')
  }
  const envUrl = import.meta.env.VITE_API_BASE_URL ?? '/api'
  if (envUrl.startsWith('http')) return envUrl.replace(/^http/i, 'ws')
  if (envUrl.startsWith('ws')) return envUrl
  
  // fallback: same-origin
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${envUrl.startsWith('/') ? envUrl : '/' + envUrl}`
}

export class WsClient {
  private ws?: WebSocket
  private wsBaseUrl: string

  constructor(opts?: WsClientConfig) {
    this.wsBaseUrl = getWsBaseUrl(opts?.baseUrl)
  }

  connect(channel: string, handler: WsMessageHandler): void {
    this.close()

    const roomId = localStorage.getItem('if_room_id') || 'default'
    const url = `${this.wsBaseUrl.replace(/\/$/, '')}/ws/${encodeURIComponent(roomId)}/${encodeURIComponent(channel)}`
    this.ws = new WebSocket(url)

    this.ws.onmessage = (ev) => {
      try {
        handler(JSON.parse(ev.data))
      } catch {
        handler(ev.data)
      }
    }

    // server receive loop requires client to send something; keepalive every 15s
    this.ws.onopen = () => {
      const timer = window.setInterval(() => {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
          window.clearInterval(timer)
          return
        }
        this.ws.send('ping')
      }, 15000)
    }
  }

  close(): void {
    if (this.ws) {
      try {
        this.ws.close()
      } catch {
        // ignore
      }
    }
    this.ws = undefined
  }
}
