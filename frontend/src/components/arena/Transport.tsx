'use client';

import { Play, Pause, SkipBack, SkipForward, ChevronLeft, ChevronRight } from 'lucide-react';
import { useReplayStore, speedToMs } from '@/lib/replay';
import { useEffect, useRef } from 'react';

const SPEEDS = [0.25, 0.5, 1, 2, 4, 8];

export function Transport() {
  const {
    playhead, totalBars, playing, speed,
    setPlaying, setSpeed, setPlayhead, stepForward, stepBack, restart, tick,
  } = useReplayStore();

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Drive the playhead via rAF/timer
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!playing) return;

    const schedule = () => {
      timerRef.current = setTimeout(() => {
        tick();
        schedule();
      }, speedToMs(speed));
    };
    schedule();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [playing, speed, tick]);

  const pct = totalBars > 0 ? (playhead / (totalBars - 1)) * 100 : 0;

  const currentCandle = useReplayStore(s => s.runs[0]?.candles[s.playhead]);
  const barLabel = currentCandle
    ? new Date(currentCandle.t).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' })
    : '--';

  const tradeInfo = useReplayStore(s => {
    const run = s.runs[0];
    if (!run) return '';
    const completed = run.trades.filter(t => t.exit_bar <= s.playhead).length;
    const open = Object.values(s.openTrades).some(Boolean) ? ' + open' : '';
    return `${completed}${open} / ${run.config.target_trades} trades`;
  });

  return (
    <div className="glass flex flex-col gap-2 px-4 py-3">
      {/* Scrubber */}
      <div className="flex items-center gap-3">
        <span className="mono text-[10px] text-[#8A93A6] w-32 flex-shrink-0">{barLabel}</span>
        <div className="relative flex-1 h-1.5 bg-[#1E2636] rounded-full cursor-pointer group"
          onClick={(e) => {
            const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
            const ratio = (e.clientX - rect.left) / rect.width;
            setPlayhead(Math.round(ratio * (totalBars - 1)));
          }}
        >
          <div
            className="h-full bg-[#2A3550] rounded-full relative"
            style={{ width: `${pct}%` }}
          >
            <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-[#E6EAF2] rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        </div>
        <span className="mono text-[10px] text-[#8A93A6] w-24 text-right flex-shrink-0">{tradeInfo}</span>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2 justify-center">
        {/* Restart */}
        <button
          onClick={restart}
          className="w-8 h-8 flex items-center justify-center rounded text-[#8A93A6] hover:text-[#E6EAF2] hover:bg-[#1E2636] transition-colors cursor-pointer"
          title="Restart"
        >
          <SkipBack size={14} />
        </button>

        {/* Step back */}
        <button
          onClick={stepBack}
          className="w-8 h-8 flex items-center justify-center rounded text-[#8A93A6] hover:text-[#E6EAF2] hover:bg-[#1E2636] transition-colors cursor-pointer"
          title="-1 bar"
        >
          <ChevronLeft size={16} />
        </button>

        {/* Play/Pause */}
        <button
          onClick={() => setPlaying(!playing)}
          className="w-10 h-10 flex items-center justify-center rounded-full text-[#06090F] font-bold transition-all cursor-pointer"
          style={{ background: playing ? '#EA3943' : '#16C784', boxShadow: playing ? '0 0 16px #EA394340' : '0 0 16px #16C78440' }}
          title={playing ? 'Pause' : 'Play'}
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>

        {/* Step forward */}
        <button
          onClick={stepForward}
          className="w-8 h-8 flex items-center justify-center rounded text-[#8A93A6] hover:text-[#E6EAF2] hover:bg-[#1E2636] transition-colors cursor-pointer"
          title="+1 bar"
        >
          <ChevronRight size={16} />
        </button>

        {/* Skip to end */}
        <button
          onClick={() => setPlayhead(totalBars - 1)}
          className="w-8 h-8 flex items-center justify-center rounded text-[#8A93A6] hover:text-[#E6EAF2] hover:bg-[#1E2636] transition-colors cursor-pointer"
          title="Jump to end"
        >
          <SkipForward size={14} />
        </button>

        {/* Speed selector */}
        <div className="flex items-center gap-1 ml-3 bg-[#0C111B] border border-[#1E2636] rounded-md p-0.5">
          {SPEEDS.map(s => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`px-2 py-0.5 rounded text-[10px] mono transition-all cursor-pointer ${
                speed === s
                  ? 'bg-[#1E2636] text-[#E6EAF2]'
                  : 'text-[#8A93A6] hover:text-[#E6EAF2]'
              }`}
            >
              {s}×
            </button>
          ))}
        </div>

        {/* Bar counter */}
        <span className="mono text-[10px] text-[#8A93A6] ml-2">
          {playhead + 1} / {totalBars}
        </span>
      </div>
    </div>
  );
}
