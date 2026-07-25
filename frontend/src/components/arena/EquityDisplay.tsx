'use client';

import { useReplayStore } from '@/lib/replay';
import { RunRecord } from '@/lib/types';

interface EquityDisplayProps {
  run: RunRecord;
}

export function EquityDisplay({ run }: EquityDisplayProps) {
  const equity = useReplayStore(s => s.currentEquity[run.model_id] ?? run.config.starting_equity);
  const startEquity = run.config.starting_equity;
  const pnlAbs = equity - startEquity;
  const pnlPct = (pnlAbs / startEquity) * 100;
  const pnlPos = pnlAbs >= 0;

  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wider text-[#8A93A6] font-medium">Equity</span>
      <span
        className="mono font-bold text-2xl text-[#E6EAF2] tabular-nums leading-none"
        style={{ textShadow: '0 0 24px rgba(230,234,242,0.15)' }}
      >
        ${equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
      <span
        className="mono text-sm font-semibold tabular-nums"
        style={{ color: pnlPos ? '#16C784' : '#EA3943', textShadow: pnlPos ? '0 0 12px rgba(22,199,132,0.4)' : '0 0 12px rgba(234,57,67,0.4)' }}
      >
        {pnlPos ? '+' : ''}{pnlPct.toFixed(2)}% ({pnlPos ? '+' : ''}${pnlAbs.toFixed(2)})
      </span>
    </div>
  );
}
