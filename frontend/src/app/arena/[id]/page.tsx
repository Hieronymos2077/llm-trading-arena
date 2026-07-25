'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ChevronLeft, LayoutGrid } from 'lucide-react';
import { getTournament, getTournamentRuns, getRun } from '@/lib/api';
import type { RunRecord, TournamentRecord } from '@/lib/types';
import { useReplayStore } from '@/lib/replay';
import { CandleChart } from '@/components/arena/CandleChart';
import { EquityChart } from '@/components/arena/EquityChart';
import { Transport } from '@/components/arena/Transport';
import { Leaderboard } from '@/components/arena/Leaderboard';
import { CommentaryLog } from '@/components/arena/CommentaryLog';
import { OpenTradeCard } from '@/components/arena/OpenTradeCard';
import { EquityDisplay } from '@/components/arena/EquityDisplay';
import { ModelAvatar } from '@/components/ui/ModelAvatar';
import { StatBadge } from '@/components/ui/StatBadge';

export default function ArenaPage() {
  const { id } = useParams<{ id: string }>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tournament, setTournament] = useState<TournamentRecord | null>(null);
  const [broadcastMode, setBroadcastMode] = useState(false);
  const [hiddenModels, setHiddenModels] = useState<Set<string>>(new Set());
  const [showEma, setShowEma] = useState(true);
  const [showBB, setShowBB] = useState(true);
  const [runStatus, setRunStatus] = useState<string>('complete');
  const [runProgress, setRunProgress] = useState<{ trades_done: number; target: number; bars_processed?: number; bars_total?: number; decisions_made?: number } | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { runs, setRuns, updateRuns, focusModelId, setFocusModel, playhead, setPlayhead, totalBars, following, setFollowing } = useReplayStore();
  const isTournament = id.startsWith('trn_');

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    async function load() {
      try {
        if (isTournament) {
          const [trn, runList] = await Promise.all([
            getTournament(id),
            getTournamentRuns(id),
          ]);
          setTournament(trn);
          const validRuns = runList.filter(r => r.candles && r.candles.length > 0);
          setRuns(validRuns.length > 0 ? validRuns : runList);
          const status = trn.status ?? 'complete';
          setRunStatus(status);
          if (status === 'queued' || status === 'running') {
            // Start at warmup bars since candles may already be present
            const firstDecisionBar = runList[0]?.decisions[0]?.bar ?? 60;
            setTimeout(() => setPlayhead(firstDecisionBar), 50);
          } else {
            const firstDecisionBar = runList[0]?.decisions[0]?.bar ?? 60;
            setTimeout(() => setPlayhead(firstDecisionBar), 50);
          }
        } else {
          const run = await getRun(id);
          setRuns([run]);
          setRunStatus(run.status ?? 'complete');
          if (run.progress) setRunProgress({
            trades_done: run.progress.trades_done,
            target: run.progress.target,
            bars_processed: run.progress.bars_processed,
            bars_total: run.progress.bars_total,
            decisions_made: run.progress.decisions_made,
          });
          const firstDecisionBar = run.decisions[0]?.bar ?? 60;
          // Only jump to first decision bar on initial load
          if (run.candles && run.candles.length > 0) {
            setTimeout(() => setPlayhead(firstDecisionBar), 50);
          }
        }
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id, isTournament, setRuns, setPlayhead, stopPolling]);

  // Polling while status is queued/running
  useEffect(() => {
    if (loading) return;
    if (runStatus === 'complete' || runStatus === 'error') {
      stopPolling();
      return;
    }

    stopPolling(); // clear any existing interval first
    pollIntervalRef.current = setInterval(async () => {
      try {
        if (isTournament) {
          const [trn, runList] = await Promise.all([
            getTournament(id),
            getTournamentRuns(id),
          ]);
          setTournament(trn);
          const validRuns = runList.filter(r => r.candles && r.candles.length > 0);
          if (validRuns.length > 0) updateRuns(validRuns);
          const newStatus = trn.status ?? 'complete';
          setRunStatus(newStatus);
          const progress = trn.progress;
          if (progress) setRunProgress({ trades_done: progress.models_done ?? 0, target: progress.models_total ?? 1 });
          if (newStatus === 'complete' || newStatus === 'error') stopPolling();
        } else {
          const run = await getRun(id);
          updateRuns([run]);
          const newStatus = run.status ?? 'complete';
          setRunStatus(newStatus);
          if (run.progress) setRunProgress({
            trades_done: run.progress.trades_done,
            target: run.progress.target,
            bars_processed: run.progress.bars_processed,
            bars_total: run.progress.bars_total,
            decisions_made: run.progress.decisions_made,
          });
          if (newStatus === 'complete' || newStatus === 'error') {
            stopPolling();
            setFollowing(false);
          }
        }
      } catch {
        // ignore transient errors during poll
      }
    }, 2500);

    return stopPolling;
  }, [loading, runStatus, isTournament, id, updateRuns, stopPolling]);

  const toggleModel = useCallback((modelId: string) => {
    setHiddenModels(prev => {
      const next = new Set(prev);
      if (next.has(modelId)) next.delete(modelId);
      else next.add(modelId);
      return next;
    });
  }, []);

  const focusRun = runs.find(r => r.model_id === focusModelId) ?? runs[0];

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#06090F]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full border-2 border-[#16C784] border-t-transparent animate-spin" />
          <span className="text-[#8A93A6] text-sm">Loading arena…</span>
        </div>
      </div>
    );
  }

  if (error || !focusRun) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#06090F]">
        <div className="text-center">
          <p className="text-[#EA3943] mb-4">{error ?? 'Run not found'}</p>
          <Link href="/" className="text-[#8A93A6] hover:text-[#E6EAF2] transition-colors">← Back to home</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-[#06090F] overflow-hidden">
      {/* Header */}
      {!broadcastMode && (
        <header className="flex-shrink-0 flex items-center gap-3 px-4 py-2 border-b border-[#1E2636] bg-[#0C111B]">
          <Link href="/" className="text-[#8A93A6] hover:text-[#E6EAF2] transition-colors cursor-pointer">
            <ChevronLeft size={18} />
          </Link>

          <div className="flex items-center gap-2">
            {isTournament ? (
              <>
                <LayoutGrid size={14} className="text-[#F5B43C]" />
                <span className="font-bold text-sm text-[#E6EAF2]">
                  {tournament?.name ?? 'Tournament'}
                </span>
              </>
            ) : (
              <>
                <ModelAvatar color={focusRun.model_color} label={focusRun.model_label} size={22} />
                <span className="font-bold text-sm" style={{ color: focusRun.model_color }}>
                  {focusRun.model_label}
                </span>
              </>
            )}
          </div>

          <div className="flex items-center gap-4 ml-4">
            <span className="mono text-[10px] text-[#4A5568]">
              {focusRun.dataset.symbol} · {focusRun.dataset.timeframe} · {focusRun.dataset.bar_count} bars
            </span>
            {(runStatus === 'running' || runStatus === 'queued') && (
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#F5B43C] animate-pulse" />
                <span className="mono text-[10px] text-[#F5B43C]">
                  {runStatus === 'queued' ? 'QUEUED' : 'COMPUTING'}
                  {runProgress && runProgress.bars_processed != null && runProgress.bars_total
                    ? ` · bar ${runProgress.bars_processed}/${runProgress.bars_total}`
                    : ''}
                  {runProgress?.decisions_made != null
                    ? ` · ${runProgress.decisions_made} decisions`
                    : ''}
                  {runProgress
                    ? ` · ${runProgress.trades_done}/${runProgress.target} trades`
                    : ''}
                </span>
                {following && runStatus === 'running' && (
                  <button
                    onClick={() => setFollowing(false)}
                    className="mono text-[9px] text-[#4A5568] hover:text-[#8A93A6] underline cursor-pointer"
                    title="Stop following latest bar"
                  >
                    LIVE
                  </button>
                )}
                {!following && runStatus === 'running' && (
                  <button
                    onClick={() => setFollowing(true)}
                    className="mono text-[9px] text-[#4A5568] hover:text-[#F5B43C] underline cursor-pointer"
                    title="Follow latest bar"
                  >
                    FOLLOW
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="ml-auto flex items-center gap-3">
            {/* Indicator toggles */}
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={showEma}
                onChange={e => setShowEma(e.target.checked)}
                className="w-3 h-3 accent-[#F5B43C]"
              />
              <span className="text-[10px] text-[#8A93A6]">EMA</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={showBB}
                onChange={e => setShowBB(e.target.checked)}
                className="w-3 h-3 accent-[#7CACF8]"
              />
              <span className="text-[10px] text-[#8A93A6]">BB</span>
            </label>

            {!isTournament && (
              <button
                onClick={() => setBroadcastMode(true)}
                className="px-3 py-1 text-[10px] rounded border border-[#2A3550] text-[#8A93A6] hover:text-[#E6EAF2] hover:border-[#E6EAF2] transition-colors cursor-pointer"
              >
                Broadcast
              </button>
            )}
          </div>
        </header>
      )}

      {/* Broadcast exit bar */}
      {broadcastMode && (
        <div className="fixed top-2 right-2 z-50">
          <button
            onClick={() => setBroadcastMode(false)}
            className="px-3 py-1.5 text-[10px] glass rounded text-[#8A93A6] hover:text-[#E6EAF2] transition-colors cursor-pointer"
          >
            Exit Broadcast
          </button>
        </div>
      )}

      {/* Main arena layout */}
      <div className="flex-1 flex gap-0 overflow-hidden">
        {/* Left: Candle chart area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Chart */}
          <div className="flex-1 relative overflow-hidden">
            {focusRun && (
              <CandleChart
                run={focusRun}
                playhead={playhead}
                showEma={showEma}
                showBB={showBB}
              />
            )}

            {/* Model selector for tournament */}
            {isTournament && !broadcastMode && (
              <div className="absolute bottom-3 left-3 flex gap-2">
                {runs.map(r => (
                  <button
                    key={r.model_id}
                    onClick={() => setFocusModel(r.model_id)}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg glass text-[10px] cursor-pointer transition-all"
                    style={focusModelId === r.model_id
                      ? { borderColor: r.model_color, color: r.model_color, boxShadow: `0 0 12px ${r.model_color}30` }
                      : { color: '#8A93A6' }
                    }
                  >
                    <div className="w-2 h-2 rounded-full" style={{ background: r.model_color }} />
                    <span className="font-medium">{r.model_label.split(' ').slice(-2).join(' ')}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Transport */}
          {!broadcastMode && (
            <div className="flex-shrink-0">
              <Transport />
            </div>
          )}
        </div>

        {/* Right rail */}
        {!broadcastMode && (
          <div className="w-72 xl:w-80 flex-shrink-0 flex flex-col gap-2 p-2 border-l border-[#1E2636] overflow-y-auto bg-[#0C111B]">

            {/* Tournament: leaderboard at top */}
            {isTournament ? (
              <>
                <Leaderboard
                  focusModelId={focusModelId}
                  onFocusModel={setFocusModel}
                  showToggles
                  hiddenModels={hiddenModels}
                  onToggleModel={toggleModel}
                />

                {/* Equity race chart */}
                <div className="glass rounded-xl flex flex-col overflow-hidden">
                  <div className="px-4 py-2 border-b border-[#1E2636]">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-[#8A93A6]">Equity Race</span>
                  </div>
                  <div className="h-40">
                    <EquityChart runs={runs.filter(r => !hiddenModels.has(r.model_id))} playhead={playhead} />
                  </div>
                </div>

                {/* Focus model stats */}
                {focusRun && (
                  <div className="glass rounded-xl p-4 flex flex-col gap-3">
                    <div className="flex items-center gap-2">
                      <ModelAvatar color={focusRun.model_color} label={focusRun.model_label} size={28} />
                      <div>
                        <div className="text-xs font-bold" style={{ color: focusRun.model_color }}>{focusRun.model_label}</div>
                        <div className="text-[9px] text-[#8A93A6] mono">{focusRun.model_id}</div>
                      </div>
                    </div>
                    <EquityDisplay run={focusRun} />
                    <FinalStats run={focusRun} />
                  </div>
                )}

                {/* Open trade */}
                {focusRun && (
                  <OpenTradeCard modelId={focusRun.model_id} modelColor={focusRun.model_color} />
                )}

                {/* Commentary */}
                {focusRun && (
                  <div className="flex-1 min-h-0" style={{ minHeight: 200 }}>
                    <CommentaryLog modelId={focusRun.model_id} />
                  </div>
                )}
              </>
            ) : (
              /* Solo layout */
              <>
                {/* Model nameplate */}
                <div
                  className="glass rounded-xl p-4 flex flex-col gap-3"
                  style={{ borderColor: `${focusRun.model_color}30` }}
                >
                  <div className="flex items-center gap-3">
                    <ModelAvatar color={focusRun.model_color} label={focusRun.model_label} size={36} />
                    <div>
                      <div className="font-bold text-sm" style={{ color: focusRun.model_color }}>
                        {focusRun.model_label}
                      </div>
                      <div className="text-[10px] text-[#8A93A6] mono">{focusRun.model_provider}</div>
                    </div>
                  </div>
                  <EquityDisplay run={focusRun} />
                  <FinalStats run={focusRun} />
                </div>

                {/* Solo equity chart */}
                <div className="glass rounded-xl overflow-hidden">
                  <div className="px-4 py-2 border-b border-[#1E2636]">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-[#8A93A6]">Equity Curve</span>
                  </div>
                  <div className="h-36">
                    <EquityChart runs={[focusRun]} playhead={playhead} singleModel />
                  </div>
                </div>

                {/* Open trade */}
                <OpenTradeCard modelId={focusRun.model_id} modelColor={focusRun.model_color} />

                {/* Commentary */}
                <div className="flex-1 min-h-0" style={{ minHeight: 240 }}>
                  <CommentaryLog modelId={focusRun.model_id} />
                </div>
              </>
            )}
          </div>
        )}

        {/* Broadcast mode: just transport at bottom */}
        {broadcastMode && (
          <div className="fixed bottom-0 left-0 right-0 p-2">
            <Transport />
          </div>
        )}
      </div>
    </div>
  );
}

function FinalStats({ run }: { run: RunRecord }) {
  const completedTrades = useReplayStore(s => s.completedTrades[run.model_id] ?? []);
  const wins = completedTrades.filter(t => t.outcome === 'tp').length;
  const winRate = completedTrades.length > 0 ? (wins / completedTrades.length) * 100 : 0;
  const totalPnl = completedTrades.reduce((sum, t) => sum + t.pnl_abs, 0);

  return (
    <div className="grid grid-cols-3 gap-2 pt-1 border-t border-[#1E2636]">
      <StatBadge label="Trades" value={completedTrades.length} />
      <StatBadge label="Win %" value={`${winRate.toFixed(1)}%`} positive={winRate >= 50 ? true : winRate < 40 ? false : null} />
      <StatBadge label="P&L" value={`$${totalPnl.toFixed(0)}`} positive={totalPnl >= 0} />
    </div>
  );
}
