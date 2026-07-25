'use client';

import { useEffect, useRef } from 'react';
import { MessageSquare, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { useReplayStore } from '@/lib/replay';

interface CommentaryLogProps {
  modelId: string;
}

export function CommentaryLog({ modelId }: CommentaryLogProps) {
  const decisions = useReplayStore(s => s.visibleDecisions[modelId] ?? []);
  const run = useReplayStore(s => s.runs.find(r => r.model_id === modelId));
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom as new decisions appear
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [decisions.length]);

  const recent = decisions.slice(-50);

  return (
    <div className="glass rounded-xl flex flex-col overflow-hidden h-full">
      <div className="px-4 py-2.5 border-b border-[#1E2636] flex items-center gap-2 flex-shrink-0">
        <MessageSquare size={14} className="text-[#8A93A6]" />
        <span className="text-xs font-semibold uppercase tracking-wider text-[#8A93A6]">Commentary</span>
        <span className="ml-auto mono text-[10px] text-[#4A5568]">{decisions.length} decisions</span>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
        {recent.length === 0 && (
          <div className="text-[#4A5568] text-xs text-center py-4">Replay to see decisions…</div>
        )}
        {recent.map((d, i) => {
          const isLong = d.action === 'long';
          const isShort = d.action === 'short';
          const isFlat = d.action === 'flat';

          const Icon = isLong ? TrendingUp : isShort ? TrendingDown : Minus;
          const color = isLong ? '#16C784' : isShort ? '#EA3943' : '#8A93A6';

          const barTime = run?.candles[d.bar]
            ? new Date(run.candles[d.bar].t).toLocaleString('en-US', {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                hour12: false, timeZone: 'UTC',
              })
            : d.time.slice(0, 16).replace('T', ' ');

          return (
            <div
              key={`${d.bar}-${i}`}
              className="flex gap-2 text-[11px] leading-relaxed"
            >
              <div className="flex-shrink-0 w-4 h-4 mt-0.5 flex items-center justify-center rounded" style={{ color }}>
                <Icon size={11} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="mono text-[9px] text-[#4A5568]">{barTime}</span>
                  <span className="font-semibold" style={{ color }}>{d.action.toUpperCase()}</span>
                  {d.confidence > 0 && (
                    <span className="mono text-[9px] text-[#4A5568]">{(d.confidence * 100).toFixed(0)}%</span>
                  )}
                </div>
                <p className="text-[#8A93A6] break-words">{d.rationale}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
