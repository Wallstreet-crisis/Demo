export type WsMessageHandler = (payload: unknown) => void
export type WsStatusHandler = (status: 'connecting' | 'connected' | 'disconnected') => void

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
  private cfg?: WsClientConfig
  private _channel?: string
  private _handler?: WsMessageHandler
  private _statusHandler?: WsStatusHandler
  private _retryCount = 0
  private _retryTimer?: number
  private _keepaliveTimer?: number
  private _intentionalClose = false
  // 连接代际计数器，用于丢弃过期重连
  private _connectGeneration = 0
  // 微任务批处理：高频消息合并为一次回调，减少 React 渲染次数
  private _msgQueue: unknown[] = []
  private _flushScheduled = false

  constructor(opts?: WsClientConfig) {
    this.cfg = opts
  }

  private get _reconnectMs(): number {
    return this.cfg?.reconnectIntervalMs ?? 3000
  }

  private get _maxRetries(): number {
    return this.cfg?.maxRetries ?? 30
  }

  private get currentWsBaseUrl(): string {
    return getWsBaseUrl(this.cfg?.baseUrl)
  }

  connect(channel: string, handler: WsMessageHandler, statusHandler?: WsStatusHandler): void {
    // 增加代际，丢弃任何旧连接的重连尝试
    this._connectGeneration++
    const myGen = this._connectGeneration
    
    this._intentionalClose = false
    this._channel = channel
    this._handler = handler
    this._statusHandler = statusHandler
    this._retryCount = 0
    this._doConnect(myGen)
  }

  private _doConnect(expectedGen: number): void {
    this._cleanup()
    if (!this._channel || !this._handler) return
    // 如果代际已过期，丢弃此次连接
    if (this._connectGeneration !== expectedGen) return

    this._statusHandler?.('connecting')

    const roomId = localStorage.getItem('if_room_id') || 'default'
    const url = `${this.currentWsBaseUrl.replace(/\/$/, '')}/ws/${encodeURIComponent(roomId)}/${encodeURIComponent(this._channel)}`
    const ws = new WebSocket(url)
    this.ws = ws

    ws.onmessage = (ev) => {
      let parsed: unknown
      try {
        parsed = JSON.parse(ev.data)
      } catch {
        parsed = ev.data
      }
      // 微任务批处理：同一事件循环内的多条消息合并到一个微任务中回调，
      // React 18 会将同一同步块内的多次 setState 自动批量渲染。
      this._msgQueue.push(parsed)
      if (!this._flushScheduled) {
        this._flushScheduled = true
        queueMicrotask(() => {
          const batch = this._msgQueue.splice(0)
          this._flushScheduled = false
          const h = this._handler
          if (!h) return
          for (const msg of batch) {
            h(msg)
          }
        })
      }
    }

    ws.onopen = () => {
      this._retryCount = 0
      this._statusHandler?.('connected')
      this._keepaliveTimer = window.setInterval(() => {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
          if (this._keepaliveTimer) window.clearInterval(this._keepaliveTimer)
          return
        }
        this.ws.send('ping')
      }, 15000)
    }

    ws.onclose = () => {
      this._clearKeepalive()
      if (this._intentionalClose) return
      // 如果代际已过期，不再重连
      if (this._connectGeneration !== expectedGen) return
      this._statusHandler?.('disconnected')
      this._scheduleReconnect(expectedGen)
    }

    ws.onerror = () => {
      // onclose will fire after onerror, reconnect is handled there
    }
  }

  private _scheduleReconnect(expectedGen: number): void {
    if (this._intentionalClose) return
    if (this._connectGeneration !== expectedGen) return
    if (this._retryCount >= this._maxRetries) {
      console.warn(`[WsClient] Max retries (${this._maxRetries}) reached, giving up.`)
      return
    }
    // exponential backoff: base * 2^retry, capped at 30s
    const delay = Math.min(30000, this._reconnectMs * Math.pow(1.5, this._retryCount))
    this._retryCount++
    this._retryTimer = window.setTimeout(() => {
      // 再次检查代际，防止重连前已切换频道
      if (this._connectGeneration !== expectedGen) return
      this._doConnect(expectedGen)
    }, delay)
  }

  private _clearKeepalive(): void {
    if (this._keepaliveTimer) {
      window.clearInterval(this._keepaliveTimer)
      this._keepaliveTimer = undefined
    }
  }

  private _cleanup(): void {
    this._clearKeepalive()
    if (this._retryTimer) {
      window.clearTimeout(this._retryTimer)
      this._retryTimer = undefined
    }
    if (this.ws) {
      try { this.ws.close() } catch { /* ignore */ }
      this.ws = undefined
    }
  }

  close(): void {
    this._intentionalClose = true
    this._cleanup()
    this._channel = undefined
    this._handler = undefined
    this._statusHandler = undefined
    this._retryCount = 0
  }
}
