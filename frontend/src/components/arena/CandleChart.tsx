'use client';

import { useEffect, useRef, useState } from 'react';
import type {
  IChartApi, ISeriesApi, UTCTimestamp, SeriesMarker, ISeriesMarkersPluginApi, Time,
} from 'lightweight-charts';
import type { RunRecord, TradeRecord } from '@/lib/types';

interface CandleChartProps {
  run: RunRecord;
  playhead: number;
  showEma?: boolean;
  showBB?: boolean;
}

function toTs(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySeries = ISeriesApi<any>;
type AnyPriceLine = ReturnType<AnySeries['createPriceLine']>;

// ---------------------------------------------------------------------------
// Sound effects via Web Audio API
// ---------------------------------------------------------------------------
function playTradeSound(type: 'open_long' | 'open_short' | 'tp' | 'sl') {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const AC = window.AudioContext || (window as any).webkitAudioContext;
    if (!AC) return;
    const ctx = new AC() as AudioContext;
    const now = ctx.currentTime;

    const note = (freq: number, start: number, duration: number, vol = 0.22, type: OscillatorType = 'sine') => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = type;
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(vol, start + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.001, start + duration);
      osc.start(start);
      osc.stop(start + duration + 0.05);
    };

    if (type === 'open_long') {
      // Ascending two-tone ping (bullish)
      note(440, now, 0.25);
      note(660, now + 0.1, 0.25);
    } else if (type === 'open_short') {
      // Descending two-tone (bearish)
      note(550, now, 0.25);
      note(370, now + 0.1, 0.25);
    } else if (type === 'tp') {
      // Triumphant ascending three notes
      note(523, now, 0.2);
      note(659, now + 0.1, 0.2);
      note(784, now + 0.2, 0.35, 0.28);
    } else {
      // SL: two descending thuds
      note(330, now, 0.25, 0.2, 'triangle');
      note(220, now + 0.13, 0.3, 0.2, 'triangle');
    }
  } catch { /* Audio not available */ }
}

export function CandleChart({ run, playhead, showEma = true, showBB = true }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<AnySeries | null>(null);
  const ema20Ref = useRef<AnySeries | null>(null);
  const ema50Ref = useRef<AnySeries | null>(null);
  const bbUpperRef = useRef<AnySeries | null>(null);
  const bbLowerRef = useRef<AnySeries | null>(null);
  const bbMidRef = useRef<AnySeries | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const entryLineRef = useRef<AnyPriceLine | null>(null);
  const slLineRef = useRef<AnyPriceLine | null>(null);
  const tpLineRef = useRef<AnyPriceLine | null>(null);
  const prevPlayhead = useRef(-1);
  const readyRef = useRef(false);
  const pendingPlayhead = useRef(playhead);
  const prevOpenTradeId = useRef<number | null>(null);

  // Flash overlay state for new trade opens
  const [flashDir, setFlashDir] = useState<'long' | 'short' | null>(null);
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const modelColor = run.model_color;

  function triggerFlash(dir: 'long' | 'short') {
    if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    setFlashDir(dir);
    flashTimerRef.current = setTimeout(() => setFlashDir(null), 700);
  }

  function buildCandles(upTo: number) {
    return run.candles.slice(0, upTo + 1).map(c => ({
      time: toTs(c.t), open: c.o, high: c.h, low: c.l, close: c.c,
    }));
  }

  function buildLine(vals: (number | null)[], upTo: number) {
    return run.candles.slice(0, upTo + 1)
      .map((c, i) => {
        const v = vals[i];
        if (v == null) return null;
        return { time: toTs(c.t), value: v };
      })
      .filter((x): x is { time: UTCTimestamp; value: number } => x !== null);
  }

  function buildMarkers(upTo: number): SeriesMarker<UTCTimestamp>[] {
    const markers: SeriesMarker<UTCTimestamp>[] = [];
    for (const trade of run.trades) {
      if (trade.entry_bar > upTo) break;
      const ec = run.candles[trade.entry_bar];
      if (ec) {
        // Entry arrow: bold, blue for long, red for short
        markers.push({
          time: toTs(ec.t),
          position: trade.direction === 'long' ? 'belowBar' : 'aboveBar',
          color: trade.direction === 'long' ? '#3B82F6' : '#EF4444',
          shape: trade.direction === 'long' ? 'arrowUp' : 'arrowDown',
          text: trade.direction === 'long' ? `▲ L${trade.id}` : `▼ S${trade.id}`,
          size: 2,
        });
      }
      if (trade.exit_bar <= upTo) {
        const xc = run.candles[trade.exit_bar];
        if (xc) {
          const isTP = trade.outcome === 'tp';
          // Exit arrow: arrowDown (for long close) / arrowUp (for short close), outcome colored
          markers.push({
            time: toTs(xc.t),
            position: trade.direction === 'long' ? 'aboveBar' : 'belowBar',
            color: isTP ? '#16C784' : '#EA3943',
            shape: trade.direction === 'long' ? 'arrowDown' : 'arrowUp',
            text: isTP ? `✓TP` : `✕SL`,
            size: 2,
          });
        }
      }
    }
    return markers.sort((a, b) => Number(a.time) - Number(b.time));
  }

  function getOpenTrade(bar: number): TradeRecord | null {
    const eq = run.equity_curve[bar];
    if (!eq?.open_trade_id) return null;
    return run.trades.find(t => t.id === eq.open_trade_id) ?? null;
  }

  function applyPlayhead(bar: number) {
    const candle = candleRef.current;
    if (!candle || !readyRef.current) return;
    const prev = prevPlayhead.current;

    if (prev < 0 || Math.abs(bar - prev) > 1) {
      candle.setData(buildCandles(bar));
      chartRef.current?.timeScale().fitContent();
    } else if (bar > prev) {
      const c = run.candles[bar];
      if (c) candle.update({ time: toTs(c.t), open: c.o, high: c.h, low: c.l, close: c.c });
    }
    prevPlayhead.current = bar;

    if (showEma) {
      ema20Ref.current?.setData(buildLine(run.indicators.ema20, bar));
      ema50Ref.current?.setData(buildLine(run.indicators.ema50, bar));
    } else {
      ema20Ref.current?.setData([]);
      ema50Ref.current?.setData([]);
    }
    if (showBB) {
      bbUpperRef.current?.setData(buildLine(run.indicators.bb_upper, bar));
      bbLowerRef.current?.setData(buildLine(run.indicators.bb_lower, bar));
      bbMidRef.current?.setData(buildLine(run.indicators.bb_mid, bar));
    } else {
      bbUpperRef.current?.setData([]);
      bbLowerRef.current?.setData([]);
      bbMidRef.current?.setData([]);
    }

    markersRef.current?.setMarkers(buildMarkers(bar));

    // Remove old price lines
    if (entryLineRef.current) { try { candle.removePriceLine(entryLineRef.current); } catch { /**/ } entryLineRef.current = null; }
    if (slLineRef.current) { try { candle.removePriceLine(slLineRef.current); } catch { /**/ } slLineRef.current = null; }
    if (tpLineRef.current) { try { candle.removePriceLine(tpLineRef.current); } catch { /**/ } tpLineRef.current = null; }

    const ot = getOpenTrade(bar);

    // Only trigger audio/flash when stepping forward exactly one bar (not on scrub/jump)
    const isForwardStep = prev >= 0 && bar === prev + 1;
    const newOpenId = ot?.id ?? null;
    if (newOpenId !== prevOpenTradeId.current) {
      if (isForwardStep) {
        if (newOpenId !== null && ot) {
          playTradeSound(ot.direction === 'long' ? 'open_long' : 'open_short');
          triggerFlash(ot.direction as 'long' | 'short');
        } else if (prevOpenTradeId.current !== null) {
          const closedTrade = run.trades.find(t => t.id === prevOpenTradeId.current);
          if (closedTrade && closedTrade.exit_bar <= bar) {
            playTradeSound(closedTrade.outcome === 'tp' ? 'tp' : 'sl');
          }
        }
      }
      prevOpenTradeId.current = newOpenId;
    }

    // Draw price lines for open trade (thick and bright)
    if (ot) {
      const entryColor = ot.direction === 'long' ? '#3B82F6' : '#EF4444';
      entryLineRef.current = candle.createPriceLine({
        price: ot.entry_price, color: entryColor,
        lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: `ENTRY (${ot.direction.toUpperCase()})`,
      });
      slLineRef.current = candle.createPriceLine({
        price: ot.stop_loss, color: '#EA3943',
        lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: 'SL',
      });
      tpLineRef.current = candle.createPriceLine({
        price: ot.take_profit, color: '#16C784',
        lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: 'TP',
      });
    }
  }

  useEffect(() => {
    if (!containerRef.current) return;
    readyRef.current = false;
    prevPlayhead.current = -1;
    prevOpenTradeId.current = null;
    let chart: IChartApi | null = null;
    let unmounted = false;

    import('lightweight-charts').then(lc => {
      if (unmounted || !containerRef.current) return;

      chart = lc.createChart(containerRef.current, {
        layout: {
          background: { color: '#0C111B' },
          textColor: '#8A93A6',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
        },
        grid: { vertLines: { color: '#1E2636' }, horzLines: { color: '#1E2636' } },
        crosshair: {
          vertLine: { color: '#2A3550', labelBackgroundColor: '#121826' },
          horzLine: { color: '#2A3550', labelBackgroundColor: '#121826' },
        },
        rightPriceScale: { borderColor: '#1E2636' },
        timeScale: { borderColor: '#1E2636', timeVisible: true, secondsVisible: false },
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      });

      const candle = chart.addSeries(lc.CandlestickSeries, {
        upColor: '#16C784', downColor: '#EA3943',
        borderUpColor: '#16C784', borderDownColor: '#EA3943',
        wickUpColor: '#16C784', wickDownColor: '#EA3943',
      });
      candleRef.current = candle;

      markersRef.current = lc.createSeriesMarkers(candle, []);

      ema20Ref.current = chart.addSeries(lc.LineSeries, { color: '#F5B43C', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      ema50Ref.current = chart.addSeries(lc.LineSeries, { color: '#9B6DFF', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      bbUpperRef.current = chart.addSeries(lc.LineSeries, { color: '#2A3550', lineWidth: 1, priceLineVisible: false, lastValueVisible: false, lineStyle: 2 });
      bbLowerRef.current = chart.addSeries(lc.LineSeries, { color: '#2A3550', lineWidth: 1, priceLineVisible: false, lastValueVisible: false, lineStyle: 2 });
      bbMidRef.current = chart.addSeries(lc.LineSeries, { color: '#1E2636', lineWidth: 1, priceLineVisible: false, lastValueVisible: false, lineStyle: 1 });

      chartRef.current = chart;
      readyRef.current = true;
      applyPlayhead(pendingPlayhead.current);
      chart.timeScale().fitContent();

      const ro = new ResizeObserver(() => {
        if (containerRef.current && chart) {
          chart.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
        }
      });
      ro.observe(containerRef.current);
    });

    return () => {
      unmounted = true;
      readyRef.current = false;
      markersRef.current = null;
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
      if (chart) chart.remove();
      chartRef.current = null;
      candleRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run.run_id]);

  useEffect(() => {
    pendingPlayhead.current = playhead;
    applyPlayhead(playhead);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playhead, showEma, showBB, run.candles.length]);

  // Flash overlay color
  const flashColor = flashDir === 'long'
    ? 'rgba(59, 130, 246, 0.18)'   // blue for long
    : 'rgba(239, 68, 68, 0.18)';   // red for short

  return (
    <div className="relative w-full h-full" style={{ background: '#0C111B' }}>
      <div ref={containerRef} className="w-full h-full" />

      {/* Trade open flash overlay */}
      {flashDir && (
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: flashColor,
            border: `2px solid ${flashDir === 'long' ? '#3B82F6' : '#EF4444'}`,
            borderRadius: 0,
            animation: 'tradeFlash 0.7s ease-out forwards',
          }}
        />
      )}

      <style>{`
        @keyframes tradeFlash {
          0%   { opacity: 1; }
          60%  { opacity: 0.5; }
          100% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
