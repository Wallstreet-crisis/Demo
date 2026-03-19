export type ApiErrorBody = {
  detail?: string
}

export class ApiError extends Error {
  status: number
  body?: unknown

  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export type ApiClientConfig = {
  baseUrl: string
}

function getBaseUrl(): string {
  const override = localStorage.getItem('if_network_target')
  if (override) {
    return override.startsWith('http') ? override : `http://${override}`
  }
  return import.meta.env.VITE_API_BASE_URL ?? '/api'
}

const defaultConfig: ApiClientConfig = {
  get baseUrl() {
    return getBaseUrl()
  }
}

function joinUrl(baseUrl: string, path: string): string {
  const b = (baseUrl ?? '').replace(/\/$/, '')
  const p = (path ?? '').replace(/^\//, '')
  if (!b) return `/${p}`
  return `${b}/${p}`
}

async function readJsonSafe(res: Response): Promise<unknown> {
  const contentType = res.headers.get('content-type')
  const text = await res.text()
  const looksLikeHtml = /^\s*</.test(text) && /<html|<!doctype\s+html/i.test(text)
  if ((contentType && contentType.includes('text/html')) || looksLikeHtml) {
    const snippet = text.slice(0, 200)
    const url = res.url || '(unknown url)'
    // 增加诊断建议
    const advice = url.includes('localhost:5173/api') 
      ? '检测到请求发往了 Vite 开发服务器但未被转发。请确保后端已启动在 8010 端口，并重启 Vite 以加载最新 proxy 配置。'
      : '请检查 VITE_API_BASE_URL 配置是否正确。'
    
    throw new ApiError(
      res.status,
      `API 返回了 HTML 而不是 JSON。${advice} url=${url} status=${res.status} content-type=${contentType ?? '(none)'} snippet=${JSON.stringify(snippet)}`,
    )
  }
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

export class ApiClient {
  private cfg?: Partial<ApiClientConfig>

  constructor(cfg?: Partial<ApiClientConfig>) {
    this.cfg = cfg
  }

  get baseUrl(): string {
    return this.cfg?.baseUrl ?? getBaseUrl()
  }

  url(path: string): string {
    return joinUrl(this.baseUrl, path)
  }

  async get<T>(path: string, query?: Record<string, string | number | boolean | undefined>): Promise<T> {
    const url = new URL(this.url(path), window.location.origin)
    if (query) {
      for (const [k, v] of Object.entries(query)) {
        if (v === undefined) continue
        url.searchParams.set(k, String(v))
      }
    }

    const res = await fetch(url.toString(), {
      method: 'GET',
      headers: { 
        'Content-Type': 'application/json',
        'X-Room-Id': localStorage.getItem('if_room_id') || 'default'
      },
    })

    if (!res.ok) {
      const body = (await readJsonSafe(res)) as ApiErrorBody | unknown
      const msg = (body as ApiErrorBody | undefined)?.detail ?? `HTTP ${res.status}`
      throw new ApiError(res.status, msg, body)
    }

    return (await readJsonSafe(res)) as T
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(this.url(path), {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'X-Room-Id': localStorage.getItem('if_room_id') || 'default'
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })

    if (!res.ok) {
      const errBody = (await readJsonSafe(res)) as ApiErrorBody | unknown
      const msg = (errBody as ApiErrorBody | undefined)?.detail ?? `HTTP ${res.status}`
      throw new ApiError(res.status, msg, errBody)
    }

    return (await readJsonSafe(res)) as T
  }

  async delete<T>(path: string): Promise<T> {
    const res = await fetch(this.url(path), {
      method: 'DELETE',
      headers: { 
        'Content-Type': 'application/json',
        'X-Room-Id': localStorage.getItem('if_room_id') || 'default'
      },
    })

    if (!res.ok) {
      const errBody = (await readJsonSafe(res)) as ApiErrorBody | unknown
      const msg = (errBody as ApiErrorBody | undefined)?.detail ?? `HTTP ${res.status}`
      throw new ApiError(res.status, msg, errBody)
    }

    return (await readJsonSafe(res)) as T
  }
}
