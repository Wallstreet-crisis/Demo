import { describe, it, expect } from 'vitest'

// Simple mock of the valuation logic if we were to extract it
function calculateEstimatedValue(orderType: string, lastPrice: number | null, inputPrice: string, quantity: string): number {
  const p = orderType === 'MARKET' ? (lastPrice ?? 0) : Number(inputPrice)
  const q = Number(quantity)
  if (isNaN(p) || isNaN(q)) return 0
  return p * q
}

function canSubmitOrder(
  side: 'BUY' | 'SELL',
  orderType: 'LIMIT' | 'MARKET',
  price: string,
  quantity: string,
  estimatedValue: number,
  availableCash: number,
  availablePos: number
): boolean {
  const q = Number(quantity)
  if (isNaN(q) || q <= 0) return false
  if (orderType === 'LIMIT') {
    const p = Number(price)
    if (isNaN(p) || p <= 0) return false
  }
  if (side === 'BUY' && estimatedValue > availableCash) return false
  if (side === 'SELL' && q > availablePos) return false
  return true
}

describe('Trade Logic', () => {
  describe('calculateEstimatedValue', () => {
    it('should calculate market order value correctly', () => {
      expect(calculateEstimatedValue('MARKET', 150, '', '10')).toBe(1500)
    })

    it('should calculate limit order value correctly', () => {
      expect(calculateEstimatedValue('LIMIT', 150, '145', '10')).toBe(1450)
    })

    it('should return 0 for invalid inputs', () => {
      expect(calculateEstimatedValue('LIMIT', 150, 'abc', '10')).toBe(0)
    })
  })

  describe('canSubmitOrder', () => {
    it('should allow valid buy order', () => {
      expect(canSubmitOrder('BUY', 'LIMIT', '100', '5', 500, 1000, 0)).toBe(true)
    })

    it('should reject buy order with insufficient cash', () => {
      expect(canSubmitOrder('BUY', 'LIMIT', '100', '15', 1500, 1000, 0)).toBe(false)
    })

    it('should allow valid sell order', () => {
      expect(canSubmitOrder('SELL', 'MARKET', '', '5', 500, 0, 10)).toBe(true)
    })

    it('should reject sell order with insufficient positions', () => {
      expect(canSubmitOrder('SELL', 'MARKET', '', '15', 1500, 0, 10)).toBe(false)
    })

    it('should reject zero quantity', () => {
      expect(canSubmitOrder('BUY', 'MARKET', '', '0', 0, 1000, 0)).toBe(false)
    })
  })
})
