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

const defaultConfig: ApiClientConfig = {
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api',
}

function joinUrl(baseUrl: string, path: string): string {
  const b = (baseUrl ?? '').replace(/\/$/, '')
  const p = (path ?? '').replace(/^\//, '')
  if (!b) return `/${p}`
  return `${b}/${p}`
}

async function readJsonSafe(res: Response): Promise<unknown> {
  const text = await res.text()
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

export class ApiClient {
  private cfg: ApiClientConfig

  constructor(cfg?: Partial<ApiClientConfig>) {
    this.cfg = { ...defaultConfig, ...(cfg ?? {}) }
  }

  url(path: string): string {
    return joinUrl(this.cfg.baseUrl, path)
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
      headers: { 'Content-Type': 'application/json' },
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
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })

    if (!res.ok) {
      const errBody = (await readJsonSafe(res)) as ApiErrorBody | unknown
      const msg = (errBody as ApiErrorBody | undefined)?.detail ?? `HTTP ${res.status}`
      throw new ApiError(res.status, msg, errBody)
    }

    return (await readJsonSafe(res)) as T
  }
}
