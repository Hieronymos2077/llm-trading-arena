'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { Trophy } from 'lucide-react';
import { useReplayStore } from '@/lib/replay';
import { ModelAvatar } from '@/components/ui/ModelAvatar';

interface LeaderboardProps {
  focusModelId: string | null;
  onFocusModel: (id: string) => void;
  showToggles?: boolean;
  hiddenModels?: Set<string>;
  onToggleModel?: (id: string) => void;
}

export function Leaderboard({ focusModelId, onFocusModel, showToggles, hiddenModels, onToggleModel }: LeaderboardProps) {
  const leaderboard = useReplayStore(s => s.leaderboard);
  const runs = useReplayStore(s => s.runs);
  const completedTrades = useReplayStore(s => s.completedTrades);

  const runMap = Object.fromEntries(runs.map(r => [r.model_id, r]));

  return (
    <div className="glass rounded-xl overflow-hidden flex flex-col">
      <div className="px-4 py-2.5 border-b border-[#1E2636] flex items-center gap-2">
        <Trophy size={14} className="text-[#F5B43C]" />
        <span className="text-xs font-semibold uppercase tracking-wider text-[#8A93A6]">Leaderboard</span>
      </div>

      <AnimatePresence>
        {leaderboard.map((entry, idx) => {
          const run = runMap[entry.modelId];
          if (!run) return null;

          const isLeader = idx === 0;
          const isFocused = focusModelId === entry.modelId;
          const isHidden = hiddenModels?.has(entry.modelId);
          const trades = completedTrades[entry.modelId] ?? [];
          const wins = trades.filter(t => t.outcome === 'tp').length;
          const winRate = trades.length > 0 ? (wins / trades.length) * 100 : 0;
          const pnlPos = entry.pnlPct >= 0;

          return (
            <motion.div
              key={entry.modelId}
              layout
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: isHidden ? 0.4 : 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25, type: 'spring', damping: 20 }}
              className={`flex items-center gap-3 px-4 py-3 border-b border-[#1E2636] cursor-pointer transition-colors hover:bg-[#121826] ${isFocused ? 'bg-[#121826]' : ''}`}
              style={isLeader ? {
                background: 'linear-gradient(90deg, rgba(245,180,60,0.06) 0%, transparent 100%)',
              } : {}}
              onClick={() => onFocusModel(entry.modelId)}
            >
              {/* Rank */}
              <div className="w-5 flex-shrink-0 text-center">
                {isLeader ? (
                  <Trophy size={14} className="text-[#F5B43C] mx-auto" />
                ) : (
                  <span className="mono text-xs text-[#8A93A6]">{idx + 1}</span>
                )}
              </div>

              {/* Avatar */}
              <ModelAvatar
                color={run.model_color}
                label={run.model_label}
                size={28}
                isLeader={isLeader}
                isSelected={isFocused}
              />

              {/* Label */}
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold truncate" style={isLeader ? { color: '#F5B43C' } : { color: '#E6EAF2' }}>
                  {run.model_label}
                </div>
                <div className="text-[10px] text-[#8A93A6] mono">
                  {trades.length} trades · {winRate.toFixed(0)}% W
                </div>
              </div>

              {/* PnL */}
              <div className="text-right flex-shrink-0">
                <div
                  className="mono text-sm font-bold"
                  style={{ color: pnlPos ? '#16C784' : '#EA3943' }}
                >
                  {pnlPos ? '+' : ''}{entry.pnlPct.toFixed(2)}%
                </div>
                <div className="mono text-[10px] text-[#8A93A6]">
                  ${entry.equity.toFixed(0)}
                </div>
              </div>

              {/* Toggle visibility */}
              {showToggles && onToggleModel && (
                <button
                  onClick={(e) => { e.stopPropagation(); onToggleModel(entry.modelId); }}
                  className="w-5 h-5 rounded border border-[#2A3550] flex items-center justify-center cursor-pointer hover:border-[#E6EAF2] transition-colors"
                  title={isHidden ? 'Show' : 'Hide'}
                >
                  {!isHidden && (
                    <div className="w-2 h-2 rounded-sm" style={{ background: run.model_color }} />
                  )}
                </button>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
