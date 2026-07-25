'use client';

import { TrendingUp, TrendingDown, Clock } from 'lucide-react';
import { useReplayStore } from '@/lib/replay';

interface OpenTradeCardProps {
  modelId: string;
  modelColor: string;
}

export function OpenTradeCard({ modelId, modelColor }: OpenTradeCardProps) {
  const trade = useReplayStore(s => s.openTrades[modelId]);
  const playhead = useReplayStore(s => s.playhead);
  const run = useReplayStore(s => s.runs.find(r => r.model_id === modelId));

  if (!trade || !run) {
    return (
      <div className="glass rounded-xl px-4 py-3 flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-[#2A3550]" />
        <span className="text-xs text-[#4A5568]">No open position</span>
      </div>
    );
  }

  const isLong = trade.direction === 'long';
  const barsHeld = playhead - trade.entry_bar;
  const currentPrice = run.candles[playhead]?.c ?? trade.entry_price;
  const floatingPnl = isLong
    ? (currentPrice - trade.entry_price) * (trade.risk_amount / (trade.entry_price - trade.stop_loss))
    : (trade.entry_price - currentPrice) * (trade.risk_amount / (trade.stop_loss - trade.entry_price));
  const floatingPct = (floatingPnl / (run.equity_curve[trade.entry_bar]?.equity ?? run.config.starting_equity)) * 100;
  const pnlPos = floatingPnl >= 0;

  return (
    <div
      className="glass rounded-xl px-4 py-3 flex flex-col gap-2"
      style={{ borderColor: `${modelColor}30`, boxShadow: `0 0 16px ${modelColor}15` }}
    >
      <div className="flex items-center gap-2">
        <div
          className="w-6 h-6 rounded-full flex items-center justify-center"
          style={{ background: `${modelColor}20`, color: modelColor }}
        >
          {isLong ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
        </div>
        <span className="text-xs font-bold" style={{ color: modelColor }}>
          {isLong ? 'LONG' : 'SHORT'} #{trade.id}
        </span>
        <div className="flex items-center gap-1 ml-auto text-[#8A93A6] text-[10px] mono">
          <Clock size={10} />
          {barsHeld}B
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[10px]">
        <div>
          <span className="text-[#4A5568]">ENTRY</span>
          <div className="mono text-[#E6EAF2]">${trade.entry_price.toFixed(1)}</div>
        </div>
        <div>
          <span className="text-[#4A5568]">CURRENT</span>
          <div className="mono text-[#E6EAF2]">${currentPrice.toFixed(1)}</div>
        </div>
        <div>
          <span className="text-[#EA3943] text-[9px]">SL</span>
          <div className="mono text-[#EA3943]">${trade.stop_loss.toFixed(1)}</div>
        </div>
        <div>
          <span className="text-[#16C784] text-[9px]">TP</span>
          <div className="mono text-[#16C784]">${trade.take_profit.toFixed(1)}</div>
        </div>
      </div>

      <div className="border-t border-[#1E2636] pt-2 flex items-center justify-between">
        <span className="text-[10px] text-[#8A93A6]">Float P&amp;L</span>
        <span
          className="mono text-sm font-bold"
          style={{ color: pnlPos ? '#16C784' : '#EA3943' }}
        >
          {pnlPos ? '+' : ''}{floatingPct.toFixed(2)}%
          <span className="text-[10px] ml-1 opacity-70">
            (${floatingPnl >= 0 ? '+' : ''}{floatingPnl.toFixed(2)})
          </span>
        </span>
      </div>
    </div>
  );
}
