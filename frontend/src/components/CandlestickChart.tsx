import { useMemo, useState } from 'react'
import { type MarketCandleItem } from '../api'

interface CandlestickChartProps {
  candles: MarketCandleItem[]
  height?: number
  width?: number
}

export default function CandlestickChart({ candles, height = 300, width = 600 }: CandlestickChartProps) {
  const [hoveredCandle, setHoveredCandle] = useState<MarketCandleItem | null>(null)
  const [mouseX, setMouseX] = useState<number | null>(null)
  const [mouseY, setMouseY] = useState<number | null>(null)

  const margin = useMemo(() => ({ top: 20, right: 60, bottom: 40, left: 10 }), [])
  const volHeight = 50 // Volume bars height
  
  const chartData = useMemo(() => {
    if (!candles || candles.length === 0) return null
    
    const minPrice = Math.min(...candles.map(c => c.low))
    const maxPrice = Math.max(...candles.map(c => c.high))
    const maxVol = Math.max(...candles.map(c => c.volume))
    const priceRange = (maxPrice - minPrice) || 1
    
    const chartAreaHeight = height - margin.top - margin.bottom - volHeight - 10
    const scaleY = (price: number) => 
      margin.top + chartAreaHeight - ((price - minPrice) / priceRange) * chartAreaHeight
    
    // Reverse scaleY: y-coordinate to price
    const invertY = (y: number) => 
      minPrice + (margin.top + chartAreaHeight - y) / chartAreaHeight * priceRange
    
    const scaleVol = (vol: number) => 
      height - margin.bottom - (vol / (maxVol || 1)) * volHeight
    
    const barWidth = (width - margin.left - margin.right) / Math.max(candles.length, 1)
    const scaleX = (index: number) => margin.left + index * barWidth
    
    // MA calculations
    const calculateMA = (data: MarketCandleItem[], period: number) => {
      return data.map((_, idx) => {
        if (idx < period - 1) return null
        const sum = data.slice(idx - period + 1, idx + 1).reduce((acc, curr) => acc + curr.close, 0)
        return sum / period
      })
    }
    
    const ma5 = calculateMA(candles, 5)
    const ma20 = calculateMA(candles, 20)
    
    return { scaleY, invertY, scaleX, scaleVol, barWidth, minPrice, maxPrice, maxVol, ma5, ma20, chartAreaHeight }
  }, [candles, height, width, margin])

  if (!chartData) return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: '12px' }}>NO_MARKET_DATA</div>

  const { scaleY, invertY, scaleX, scaleVol, barWidth, minPrice, maxPrice, ma5, ma20, chartAreaHeight } = chartData

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    setMouseX(x)
    setMouseY(y)
    
    const idx = Math.floor((x - margin.left) / barWidth)
    if (idx >= 0 && idx < candles.length) {
      setHoveredCandle(candles[idx])
    } else {
      setHoveredCandle(null)
    }
  }

  const lastCandle = candles[candles.length - 1]
  const currentHoverPrice = (mouseY !== null && mouseY >= margin.top && mouseY <= margin.top + chartAreaHeight) ? invertY(mouseY) : null

  return (
    <div style={{ position: 'relative' }}>
      {/* Legend for MA */}
      <div style={{ 
        position: 'absolute', 
        top: 5, 
        left: margin.left + 5, 
        fontSize: '9px', 
        display: 'flex', 
        gap: '10px',
        pointerEvents: 'none'
      }}>
        <span style={{ color: '#fbbf24' }}>MA5: {lastCandle ? ma5[candles.length - 1]?.toFixed(2) : '--'}</span>
        <span style={{ color: '#8b5cf6' }}>MA20: {lastCandle ? ma20[candles.length - 1]?.toFixed(2) : '--'}</span>
      </div>

      {/* Tooltip Overlay */}
      {hoveredCandle && (
        <div style={{ 
          position: 'absolute', 
          top: 20, 
          left: margin.left, 
          pointerEvents: 'none',
          fontSize: '10px',
          color: '#cbd5e1',
          background: 'rgba(15, 23, 42, 0.9)',
          padding: '4px 8px',
          border: '1px solid #334155',
          display: 'flex',
          gap: '10px',
          zIndex: 10,
          borderRadius: '2px'
        }}>
          <span>O: <span style={{ color: '#fff' }}>{hoveredCandle.open.toFixed(2)}</span></span>
          <span>H: <span style={{ color: '#fff' }}>{hoveredCandle.high.toFixed(2)}</span></span>
          <span>L: <span style={{ color: '#fff' }}>{hoveredCandle.low.toFixed(2)}</span></span>
          <span>C: <span style={{ color: '#fff' }}>{hoveredCandle.close.toFixed(2)}</span></span>
          <span>V: <span style={{ color: '#fff' }}>{hoveredCandle.volume.toLocaleString()}</span></span>
        </div>
      )}

      <svg 
        width="100%" 
        height={height} 
        viewBox={`0 0 ${width} ${height}`} 
        style={{ overflow: 'visible', cursor: 'crosshair' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => { setHoveredCandle(null); setMouseX(null); setMouseY(null); }}
      >
        {/* Horizontal Grid & Price Labels */}
        {[0, 0.25, 0.5, 0.75, 1].map(p => {
          const price = minPrice + p * (maxPrice - minPrice)
          const y = scaleY(price)
          return (
            <g key={p}>
              <line x1={margin.left} y1={y} x2={width - margin.right} y2={y} stroke="#1e293b" strokeWidth="1" strokeDasharray="2 4" />
              <text x={width - margin.right + 5} y={y + 4} fill="#64748b" fontSize="10" fontFamily="monospace">{price.toFixed(2)}</text>
            </g>
          )
        })}

        {/* Current Price Line */}
        {lastCandle && (
          <g>
            <line 
              x1={margin.left} 
              y1={scaleY(lastCandle.close)} 
              x2={width - margin.right} 
              y2={scaleY(lastCandle.close)} 
              stroke="#3b82f6" 
              strokeWidth="1" 
              strokeDasharray="4 2"
            />
            <rect 
              x={width - margin.right} 
              y={scaleY(lastCandle.close) - 8} 
              width={margin.right} 
              height={16} 
              fill="#3b82f6" 
            />
            <text 
              x={width - margin.right + 5} 
              y={scaleY(lastCandle.close) + 4} 
              fill="#fff" 
              fontSize="10" 
              fontWeight="bold"
              fontFamily="monospace"
            >
              {lastCandle.close.toFixed(2)}
            </text>
          </g>
        )}

        {/* Crosshair X & Y */}
        {mouseX !== null && mouseX >= margin.left && mouseX <= width - margin.right && (
          <line x1={mouseX} y1={margin.top} x2={mouseX} y2={height - margin.bottom} stroke="#475569" strokeWidth="1" strokeDasharray="3 3" />
        )}
        {mouseY !== null && mouseY >= margin.top && mouseY <= margin.top + chartAreaHeight && (
          <g>
            <line x1={margin.left} y1={mouseY} x2={width - margin.right} y2={mouseY} stroke="#475569" strokeWidth="1" strokeDasharray="3 3" />
            <rect x={width - margin.right} y={mouseY - 8} width={margin.right} height={16} fill="#475569" />
            <text x={width - margin.right + 5} y={mouseY + 4} fill="#fff" fontSize="10" fontFamily="monospace">
              {currentHoverPrice?.toFixed(2)}
            </text>
          </g>
        )}

        {/* Volume Bars */}
        {candles.map((c, i) => {
          const isUp = c.close >= c.open
          const color = isUp ? '#10b981' : '#ef4444'
          const x = scaleX(i)
          const volY = scaleVol(c.volume)
          return (
            <rect key={`v-${i}`} x={x + barWidth * 0.2} y={volY} width={barWidth * 0.6} height={height - margin.bottom - volY} fill={color} opacity="0.15" />
          )
        })}

        {/* MA Lines */}
        <polyline
          fill="none"
          stroke="#fbbf24"
          strokeWidth="1"
          points={ma5.map((val, i) => val !== null ? `${scaleX(i) + barWidth/2},${scaleY(val)}` : '').filter(p => p !== '').join(' ')}
        />
        <polyline
          fill="none"
          stroke="#8b5cf6"
          strokeWidth="1"
          points={ma20.map((val, i) => val !== null ? `${scaleX(i) + barWidth/2},${scaleY(val)}` : '').filter(p => p !== '').join(' ')}
        />

        {/* Candlesticks */}
        {candles.map((c, i) => {
          const isUp = c.close >= c.open
          const color = isUp ? '#10b981' : '#ef4444'
          const x = scaleX(i)
          const centerX = x + barWidth / 2
          const yHigh = scaleY(c.high)
          const yLow = scaleY(c.low)
          const yOpen = scaleY(c.open)
          const yClose = scaleY(c.close)
          const bodyTop = Math.min(yOpen, yClose)
          const bodyHeight = Math.max(Math.abs(yOpen - yClose), 1)

          return (
            <g key={`c-${i}`}>
              <line x1={centerX} y1={yHigh} x2={centerX} y2={yLow} stroke={color} strokeWidth="1" />
              <rect x={x + barWidth * 0.1} y={bodyTop} width={barWidth * 0.8} height={bodyHeight} fill={color} />
            </g>
          )
        })}

        {/* Time Labels */}
        {candles.length > 0 && Array.from(new Set([0, Math.floor(candles.length / 2), candles.length - 1])).filter(idx => idx >= 0 && idx < candles.length).map(idx => {
          const c = candles[idx];
          if (!c) return null;
          return (
            <text key={`chart-time-label-${c.bucket_start}-${idx}`} x={scaleX(idx)} y={height - 10} fill="#64748b" fontSize="9" fontFamily="monospace" textAnchor="middle">
              {new Date(c.bucket_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </text>
          );
        })}
      </svg>
    </div>
  )
}

