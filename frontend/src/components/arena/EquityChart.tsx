'use client';

import { useEffect, useRef } from 'react';
import type { IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import type { RunRecord } from '@/lib/types';

interface EquityChartProps {
  runs: RunRecord[];
  playhead: number;
  singleModel?: boolean;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySeries = ISeriesApi<any>;

function toTs(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

export function EquityChart({ runs, playhead, singleModel = false }: EquityChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesMap = useRef<Map<string, AnySeries>>(new Map());
  const readyRef = useRef(false);
  const prevPlayhead = useRef(-1);
  const pendingPlayhead = useRef(playhead);
  const runsRef = useRef(runs);
  runsRef.current = runs;

  function applyPlayhead(bar: number) {
    if (!readyRef.current) return;
    const prev = prevPlayhead.current;
    prevPlayhead.current = bar;

    for (const run of runsRef.current) {
      const series = seriesMap.current.get(run.model_id);
      if (!series) continue;

      if (prev < 0 || Math.abs(bar - prev) > 1) {
        series.setData(run.equity_curve.slice(0, bar + 1).map(eq => ({
          time: toTs(eq.t), value: eq.floating,
        })));
      } else if (bar > prev) {
        const eq = run.equity_curve[bar];
        if (eq) series.update({ time: toTs(eq.t), value: eq.floating });
      }
    }
  }

  const runKey = runs.map(r => r.run_id).join(',');

  useEffect(() => {
    if (!containerRef.current) return;
    readyRef.current = false;
    prevPlayhead.current = -1;
    seriesMap.current.clear();
    let chart: IChartApi | null = null;
    let unmounted = false;

    import('lightweight-charts').then(lc => {
      if (unmounted || !containerRef.current) return;

      chart = lc.createChart(containerRef.current, {
        layout: {
          background: { color: 'transparent' },
          textColor: '#8A93A6',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 10,
        },
        grid: { vertLines: { color: '#1E2636' }, horzLines: { color: '#1E2636' } },
        rightPriceScale: { borderColor: '#1E2636' },
        timeScale: { borderColor: '#1E2636', timeVisible: false },
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      });

      const map = new Map<string, AnySeries>();
      for (const run of runsRef.current) {
        const series = chart.addSeries(lc.LineSeries, {
          color: run.model_color,
          lineWidth: singleModel ? 2 : 1,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        map.set(run.model_id, series);
      }
      seriesMap.current = map;
      chartRef.current = chart;
      readyRef.current = true;
      applyPlayhead(pendingPlayhead.current);

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
      if (chart) chart.remove();
      chartRef.current = null;
      seriesMap.current.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runKey, singleModel]);

  useEffect(() => {
    pendingPlayhead.current = playhead;
    applyPlayhead(playhead);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playhead]);

  return (
    <div ref={containerRef} className="w-full h-full" style={{ minHeight: 1 }} />
  );
}
