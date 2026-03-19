export type WsMessageHandler = (payload: unknown) => void

export type WsClientOptions = {
  baseUrl?: string
}

function getWsBaseUrl(httpBaseUrl?: string): string {
  const envBase = import.meta.env.VITE_WS_BASE_URL as string | undefined
  if (envBase) return envBase

  // If user provides API base URL as http(s)://host:port, derive ws(s)
  if (httpBaseUrl && /^https?:\/\//i.test(httpBaseUrl)) {
    return httpBaseUrl.replace(/^http/i, 'ws').replace(/\/$/, '')
  }

  // fallback: same-origin
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}`
}

export class WsClient {
  private ws?: WebSocket
  private wsBaseUrl: string

  constructor(opts?: WsClientOptions) {
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
