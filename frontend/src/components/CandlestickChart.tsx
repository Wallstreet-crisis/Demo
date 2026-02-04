import { useMemo, useState, useRef, useEffect } from 'react'
import { type MarketCandleItem } from '../api'

interface CandlestickChartProps {
  candles: MarketCandleItem[]
  height?: number
  width?: number
}

export default function CandlestickChart({ candles, height = 300 }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [chartWidth, setChartWidth] = useState(600)
  const [hoveredCandle, setHoveredCandle] = useState<MarketCandleItem | null>(null)
  const [mouseX, setMouseX] = useState<number | null>(null)
  const [mouseY, setMouseY] = useState<number | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setChartWidth(entry.contentRect.width)
      }
    })
    obs.observe(containerRef.current)
    return () => obs.disconnect()
  }, [])

  const margin = useMemo(() => ({ top: 20, right: 60, bottom: 40, left: 10 }), [])
  const volHeight = 50 // Volume bars height
  
  const chartData = useMemo(() => {
    if (!candles || candles.length === 0) return null
    const width = chartWidth
    
    const minPrice = Math.min(...candles.map(c => c.low))
    const maxPrice = Math.max(...candles.map(c => c.high))
    const maxVol = Math.max(...candles.map(c => c.volume))
    
    // Improve price range calculation to avoid extreme scaling
    const rawPriceRange = maxPrice - minPrice
    const minRange = minPrice * 0.02 // At least 2% range
    const effectivePriceRange = Math.max(rawPriceRange, minRange)
    const pricePadding = effectivePriceRange * 0.1 // 10% padding
    
    const displayMin = minPrice - pricePadding
    const displayMax = maxPrice + pricePadding
    const priceRange = displayMax - displayMin
    
    const chartAreaHeight = height - margin.top - margin.bottom - volHeight - 10
    const scaleY = (price: number) => 
      margin.top + chartAreaHeight - ((price - displayMin) / (priceRange || 1)) * chartAreaHeight
    
    const invertY = (y: number) => 
      displayMin + (margin.top + chartAreaHeight - y) / chartAreaHeight * priceRange
    
    const scaleVol = (vol: number) => 
      height - margin.bottom - (vol / (maxVol || 1)) * volHeight
    
    // Calculate optimal bar width with constraints
    const availableWidth = width - margin.left - margin.right
    const rawBarWidth = availableWidth / Math.max(candles.length, 1)
    const barWidth = Math.min(rawBarWidth, 14) // Limit max width further
    const gap = barWidth * 0.35 // 35% gap for better separation
    const bodyWidth = Math.max(barWidth - gap, 1)
    
    const scaleX = (index: number) => {
      const centerOffset = (availableWidth - (candles.length * barWidth)) / 2
      const offset = centerOffset > 0 ? centerOffset : 0
      return margin.left + offset + index * barWidth
    }
    
    const getIdxFromX = (x: number) => {
      const centerOffset = (availableWidth - (candles.length * barWidth)) / 2
      const offset = centerOffset > 0 ? centerOffset : 0
      return Math.floor((x - margin.left - offset) / barWidth)
    }
    
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
    
    return { width, scaleY, invertY, scaleX, getIdxFromX, scaleVol, barWidth, bodyWidth, gap, displayMin, displayMax, maxVol, ma5, ma20, chartAreaHeight }
  }, [candles, height, chartWidth, margin])

  if (!chartData || chartWidth < 50) return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: '12px' }}>NO_MARKET_DATA</div>

  const { width, scaleY, invertY, scaleX, getIdxFromX, scaleVol, barWidth, bodyWidth, ma5, ma20, chartAreaHeight, displayMin, displayMax } = chartData

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    setMouseX(x)
    setMouseY(y)
    
    const idx = getIdxFromX(x)
    if (idx >= 0 && idx < candles.length) {
      setHoveredCandle(candles[idx])
    } else {
      setHoveredCandle(null)
    }
  }

  const lastCandle = candles[candles.length - 1]
  const currentHoverPrice = (mouseY !== null && mouseY >= margin.top && mouseY <= margin.top + chartAreaHeight) ? invertY(mouseY) : null

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%' }}>
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
        <span style={{ color: '#fbbf24' }}>MA5: {lastCandle && ma5[candles.length - 1] != null ? ma5[candles.length - 1]?.toFixed(2) : '--'}</span>
        <span style={{ color: '#8b5cf6' }}>MA20: {lastCandle && ma20[candles.length - 1] != null ? ma20[candles.length - 1]?.toFixed(2) : '--'}</span>
      </div>

      {/* Floating Tooltip */}
      {hoveredCandle && mouseX !== null && mouseY !== null && (
        <div style={{ 
          position: 'absolute', 
          top: mouseY - 80 < 0 ? mouseY + 20 : mouseY - 100, 
          left: mouseX + 150 > chartWidth ? mouseX - 160 : mouseX + 20, 
          pointerEvents: 'none',
          fontSize: '11px',
          color: '#cbd5e1',
          background: 'rgba(15, 23, 42, 0.95)',
          padding: '8px 12px',
          border: '1px solid #334155',
          boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          zIndex: 100,
          borderRadius: '4px',
          fontFamily: 'monospace',
          backdropFilter: 'blur(4px)'
        }}>
          <div style={{ borderBottom: '1px solid #334155', paddingBottom: '4px', marginBottom: '4px', color: '#94a3b8' }}>
            {new Date(hoveredCandle.bucket_start).toLocaleString()}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'x 15px' }}>
            <span>O: <span style={{ color: '#fff' }}>{hoveredCandle.open.toFixed(2)}</span></span>
            <span>H: <span style={{ color: '#fff' }}>{hoveredCandle.high.toFixed(2)}</span></span>
            <span>L: <span style={{ color: '#fff' }}>{hoveredCandle.low.toFixed(2)}</span></span>
            <span>C: <span style={{ color: '#fff', fontWeight: 'bold' }}>{hoveredCandle.close.toFixed(2)}</span></span>
          </div>
          <div style={{ marginTop: '2px' }}>
            VOL: <span style={{ color: '#94a3b8' }}>{hoveredCandle.volume.toLocaleString()}</span>
          </div>
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
          const price = displayMin + p * (displayMax - displayMin)
          const y = scaleY(price)
          return (
            <g key={`grid-${p}`}>
              <line 
                x1={margin.left} 
                y1={y} 
                x2={width - margin.right} 
                y2={y} 
                stroke="#1e293b" 
                strokeWidth="0.5" 
                strokeDasharray="2 4" 
              />
              <text 
                x={width - margin.right + 8} 
                y={y + 3} 
                fill="#475569" 
                fontSize="10" 
                fontFamily="monospace"
              >
                {price.toFixed(2)}
              </text>
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
        {mouseX !== null && hoveredCandle && (
          <line 
            x1={scaleX(candles.indexOf(hoveredCandle)) + barWidth / 2} 
            y1={margin.top} 
            x2={scaleX(candles.indexOf(hoveredCandle)) + barWidth / 2} 
            y2={height - margin.bottom} 
            stroke="#94a3b8" 
            strokeWidth="0.5" 
            strokeDasharray="3 3" 
          />
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
        {candles.map((c, idx) => {
          const isUp = c.close >= c.open
          const color = isUp ? '#26a69a' : '#ef5350'
          const x = scaleX(idx)
          const volY = scaleVol(c.volume)
          return (
            <rect 
              key={`v-${c.bucket_start}-${idx}`} 
              x={x + (barWidth - bodyWidth) / 2} 
              y={volY} 
              width={bodyWidth} 
              height={Math.max(height - margin.bottom - volY, 1)} 
              fill={color} 
              opacity={hoveredCandle === c ? "0.3" : "0.1"} 
            />
          )
        })}

        {/* MA Lines */}
        <polyline
          fill="none"
          stroke="#fbbf24"
          strokeWidth="1.2"
          opacity="0.8"
          points={ma5.map((val, i) => val !== null ? `${scaleX(i) + barWidth/2},${scaleY(val)}` : '').filter(p => p !== '').join(' ')}
        />
        <polyline
          fill="none"
          stroke="#8b5cf6"
          strokeWidth="1.2"
          opacity="0.8"
          points={ma20.map((val, i) => val !== null ? `${scaleX(i) + barWidth/2},${scaleY(val)}` : '').filter(p => p !== '').join(' ')}
        />

        {/* Candlesticks */}
        {candles.map((c, idx) => {
          const isUp = c.close >= c.open
          const color = isUp ? '#26a69a' : '#ef5350' // More professional colors
          const x = scaleX(idx)
          const centerX = x + barWidth / 2
          const yHigh = scaleY(c.high)
          const yLow = scaleY(c.low)
          const yOpen = scaleY(c.open)
          const yClose = scaleY(c.close)
          const bodyTop = Math.min(yOpen, yClose)
          const bodyHeight = Math.max(Math.abs(yOpen - yClose), 1.5)

          return (
            <g key={`c-${c.bucket_start}-${idx}`}>
              {/* Wick */}
              <line 
                x1={centerX} 
                y1={yHigh} 
                x2={centerX} 
                y2={yLow} 
                stroke={color} 
                strokeWidth="0.8" 
              />
              {/* Body */}
              <rect 
                x={x + (barWidth - bodyWidth) / 2} 
                y={bodyTop} 
                width={bodyWidth} 
                height={bodyHeight} 
                fill={color} 
                stroke={color}
                strokeWidth="0.5"
                fillOpacity={isUp ? "0.8" : "1"}
              />
            </g>
          )
        })}

        {/* Time Labels & Vertical Grid */}
        {candles.length > 0 && Array.from(new Set([0, Math.floor(candles.length / 2), candles.length - 1])).filter(idx => idx >= 0 && idx < candles.length).map(idx => {
          const c = candles[idx];
          if (!c) return null;
          const x = scaleX(idx) + barWidth / 2;
          return (
            <g key={`v-grid-${c.bucket_start}-${idx}`}>
              <line 
                x1={x} 
                y1={margin.top} 
                x2={x} 
                y2={margin.top + chartAreaHeight + volHeight + 10} 
                stroke="#1e293b" 
                strokeWidth="0.5" 
                strokeDasharray="2 4"
              />
              <text x={x} y={height - 10} fill="#475569" fontSize="9" fontFamily="monospace" textAnchor="middle">
                {new Date(c.bucket_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  )
}

