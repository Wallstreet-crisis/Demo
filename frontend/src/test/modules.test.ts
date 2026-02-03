import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Api } from '../api'

// Mock the global fetch
const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

describe('Contract and News API', () => {
  beforeEach(() => {
    fetchMock.mockClear()
    localStorage.clear()
  })

  it('contractAgentDraft should call correct endpoint with payload', async () => {
    const mockResponse = {
      draft_id: 'draft:123',
      contract_create: { kind: 'LOAN', title: 'Test' },
      explanation: 'AI explanation',
      risk_rating: 'LOW'
    }
    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify(mockResponse),
    })

    const res = await Api.contractAgentDraft({
      actor_id: 'user:alice',
      natural_language: 'Draft a loan contract'
    })

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/contract-agent/draft'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          actor_id: 'user:alice',
          natural_language: 'Draft a loan contract'
        })
      })
    )
    expect(res.draft_id).toBe('draft:123')
  })

  it('contractSign should call correct endpoint', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify({ status: 'SIGNED' }),
    })

    const res = await Api.contractSign('con:abc', { signer: 'user:alice' })

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/contracts/con%3Aabc/sign'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ signer: 'user:alice' })
      })
    )
    expect(res.status).toBe('SIGNED')
  })

  it('newsPropagate should call correct endpoint', async () => {
    const mockReq = {
      variant_id: 'var:123',
      from_actor_id: 'user:alice',
      spend_cash: 100,
      limit: 50
    }
    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify({ delivered: 42 }),
    })

    const res = await Api.newsPropagate(mockReq)

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/news/propagate'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(mockReq)
      })
    )
    expect(res.delivered).toBe(42)
  })

  it('contractGet should call correct endpoint', async () => {
    const mockContract = {
      contract_id: 'con:abc',
      status: 'ACTIVE',
      parties: ['user:alice']
    }
    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify(mockContract),
    })

    const res = await Api.contractGet('con:abc')

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/contracts/con%3Aabc'),
      expect.objectContaining({ method: 'GET' })
    )
    expect(res.contract_id).toBe('con:abc')
  })

  it('hostingStatus should call correct endpoint', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify({ enabled: true, status: 'WORKING' }),
    })

    const res = await Api.hostingStatus('user:alice')

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/hosting/user%3Aalice/status'),
      expect.any(Object)
    )
    expect(res.enabled).toBe(true)
  })

  it('newsStorePurchase should call correct endpoint', async () => {
    const mockReq = {
      buyer_user_id: 'user:alice',
      kind: 'OFFICIAL',
      price_cash: 500,
      symbols: ['GOLD'],
      tags: [],
      initial_text: 'Buy gold'
    }
    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify({ variant_id: 'v:999', kind: 'OFFICIAL' }),
    })

    const res = await Api.newsStorePurchase(mockReq)

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/news/store/purchase'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(mockReq)
      })
    )
    expect(res.variant_id).toBe('v:999')
  })
})
