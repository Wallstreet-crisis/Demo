import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Api } from '../api'

// Mock the global fetch
const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

describe('ApiClient', () => {
  beforeEach(() => {
    fetchMock.mockClear()
    localStorage.clear()
  })

  it('marketQuote should call correct endpoint', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify({ symbol: 'AAPL', last_price: 150 }),
    })

    const res = await Api.marketQuote('AAPL')
    
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/market/quote/AAPL'),
      expect.any(Object)
    )
    expect(res.symbol).toBe('AAPL')
  })

  it('playerAccount should call correct endpoint', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify({ account_id: 'user:alice', cash: 1000 }),
    })

    const res = await Api.playerAccount('alice')
    
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/players/alice/account'),
      expect.any(Object)
    )
    expect(res.account_id).toBe('user:alice')
  })

  it('newsInbox should call correct endpoint with limit', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify({ items: [] }),
    })

    await Api.newsInbox('user:alice', 20)
    
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/news/inbox/user%3Aalice?limit=20'),
      expect.any(Object)
    )
  })

  it('should handle API errors correctly', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      text: async () => JSON.stringify({ detail: 'Invalid symbol' }),
    })

    try {
      await Api.marketQuote('INVALID')
      expect.fail('Should have thrown an error')
    } catch (e) {
      const err = e as { status: number; message: string }
      expect(err.status).toBe(400)
      expect(err.message).toBe('Invalid symbol')
    }
  })
})
