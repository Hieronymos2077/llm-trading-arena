'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Trophy, User, ChevronRight, Activity, Clock, Zap } from 'lucide-react';
import { getModels, getTournaments, getRuns, getHealth, REAL_RUN_ID } from '@/lib/api';
import type { ModelInfo, TournamentRecord, RunRecord } from '@/lib/types';
import { ModelAvatar } from '@/components/ui/ModelAvatar';

const SAMPLE_TOURNAMENT_ID = 'trn_dcdf00ec';

export default function HomePage() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [tournaments, setTournaments] = useState<TournamentRecord[]>([]);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const [health, m, t, r] = await Promise.all([
        getHealth(),
        getModels(),
        getTournaments().catch(() => [] as TournamentRecord[]),
        getRuns().catch(() => [] as RunRecord[]),
      ]);
      setBackendOnline(health);
      setModels(m);
      setTournaments(t);
      setRuns(r);
      setLoading(false);
    }
    load();
  }, []);

  const availableCount = models.filter(m => m.available).length;

  return (
    <div className="min-h-screen bg-[#06090F] grid-bg">
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse 80% 50% at 50% 0%, rgba(22,199,132,0.04) 0%, transparent 70%)',
        }}
      />

      <div className="relative z-10 max-w-5xl mx-auto px-6 py-12">
        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center mb-16"
        >
          <div className="flex items-center justify-center gap-2 mb-3">
            <div className="w-1.5 h-1.5 rounded-full bg-[#16C784] animate-pulse" />
            <span className="text-[10px] uppercase tracking-[0.3em] text-[#8A93A6] font-medium">
              AI Trading Competition
            </span>
            <div className="w-1.5 h-1.5 rounded-full bg-[#16C784] animate-pulse" />
          </div>

          <h1
            className="text-5xl sm:text-6xl font-extrabold tracking-tight mb-4"
            style={{
              background: 'linear-gradient(135deg, #E6EAF2 30%, #8A93A6 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            AI TRADING ARENA
          </h1>

          <p className="text-[#8A93A6] text-lg max-w-xl mx-auto leading-relaxed">
            Watch AI models compete as discretionary traders on real historical data.
            Bar-by-bar replay. Cinematic broadcast.
          </p>

          <div className="flex items-center justify-center gap-2 mt-4">
            <div
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: backendOnline === null ? '#8A93A6' : backendOnline ? '#16C784' : '#EA3943' }}
            />
            <span className="text-[11px] text-[#8A93A6]">
              {backendOnline === null ? 'Connecting…' : backendOnline ? 'Backend online' : 'Demo mode (offline)'}
            </span>
            {!backendOnline && !loading && (
              <span className="text-[11px] text-[#4A5568]">· sample data loaded</span>
            )}
          </div>
        </motion.div>

        {/* Mode cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
          >
            <Link href={`/arena/${SAMPLE_TOURNAMENT_ID}`}>
              <div
                className="glass rounded-2xl p-6 cursor-pointer group transition-all duration-200 hover:border-[#F5B43C] relative overflow-hidden h-full"
                style={{ borderColor: '#1E2636' }}
              >
                <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
                  style={{ background: 'radial-gradient(ellipse at top left, rgba(245,180,60,0.06) 0%, transparent 60%)' }} />

                <div className="flex items-start justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'rgba(245,180,60,0.12)' }}>
                    <Trophy size={20} className="text-[#F5B43C]" />
                  </div>
                  <ChevronRight size={16} className="text-[#4A5568] group-hover:text-[#F5B43C] transition-colors" />
                </div>

                <h2 className="text-lg font-bold text-[#E6EAF2] mb-1">Tournament</h2>
                <p className="text-sm text-[#8A93A6] leading-relaxed mb-4">
                  Multiple AI models race on the same dataset. Live leaderboard, equity race, side-by-side comparison.
                </p>

                <div className="flex items-center gap-2 text-[10px] text-[#4A5568]">
                  <Zap size={10} className="text-[#F5B43C]" />
                  <span>BTC 1h Showdown, Claude vs Gemini vs GPT</span>
                </div>
              </div>
            </Link>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.15 }}
          >
            <Link href={`/arena/${REAL_RUN_ID}`}>
              <div
                className="glass rounded-2xl p-6 cursor-pointer group transition-all duration-200 hover:border-[#7CACF8] relative overflow-hidden h-full"
                style={{ borderColor: '#1E2636' }}
              >
                <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
                  style={{ background: 'radial-gradient(ellipse at top left, rgba(124,172,248,0.06) 0%, transparent 60%)' }} />

                <div className="flex items-start justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'rgba(124,172,248,0.12)' }}>
                    <User size={20} className="text-[#7CACF8]" />
                  </div>
                  <ChevronRight size={16} className="text-[#4A5568] group-hover:text-[#7CACF8] transition-colors" />
                </div>

                <h2 className="text-lg font-bold text-[#E6EAF2] mb-1">Solo Review</h2>
                <p className="text-sm text-[#8A93A6] leading-relaxed mb-4">
                  One model, full commentary log, broadcast mode for narrated screen recordings.
                </p>

                <div className="flex items-center gap-2 text-[10px] text-[#4A5568]">
                  <Activity size={10} className="text-[#7CACF8]" />
                  <span>Claude Haiku on BTC 1h</span>
                </div>
              </div>
            </Link>
          </motion.div>
        </div>

        {/* Launch new */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="mb-10"
        >
          <Link href="/setup">
            <div className="glass rounded-xl px-6 py-4 cursor-pointer flex items-center gap-4 group transition-all hover:border-[#16C784]">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(22,199,132,0.12)' }}>
                <Zap size={16} className="text-[#16C784]" />
              </div>
              <div className="flex-1">
                <div className="font-semibold text-sm text-[#E6EAF2] group-hover:text-[#16C784] transition-colors">
                  Launch New Run
                </div>
                <div className="text-[11px] text-[#8A93A6]">Configure models, dataset, and settings</div>
              </div>
              <ChevronRight size={16} className="text-[#4A5568] group-hover:text-[#16C784] transition-colors" />
            </div>
          </Link>
        </motion.div>

        {/* Model availability */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.25 }}
          className="mb-10"
        >
          <div className="glass rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[#8A93A6]">Model Availability</h3>
              <span className="mono text-[10px] text-[#8A93A6]">
                {availableCount}/{models.length} available
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
              {models.map(m => (
                <div
                  key={m.id}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg transition-colors"
                  style={{ background: m.available ? `${m.color}10` : '#121826' }}
                >
                  <ModelAvatar color={m.color} label={m.label} size={20} />
                  <div className="min-w-0 flex-1">
                    <div className="text-[10px] font-medium truncate" style={{ color: m.available ? m.color : '#8A93A6' }}>
                      {m.label}
                    </div>
                  </div>
                  <div
                    className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                    style={{ background: m.available ? '#16C784' : '#2A3550' }}
                  />
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* History */}
        {(tournaments.length > 0 || runs.length > 0) && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3 }}
          >
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[#8A93A6] mb-3">Recent Activity</h3>
            <div className="flex flex-col gap-2">
              {tournaments.map(t => (
                <Link key={t.tournament_id} href={`/arena/${t.tournament_id}`}>
                  <div className="glass rounded-xl px-4 py-3 flex items-center gap-3 cursor-pointer hover:border-[#2A3550] transition-colors group">
                    <Trophy size={14} className="text-[#F5B43C] flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-[#E6EAF2] truncate">{t.name}</div>
                      <div className="text-[10px] text-[#8A93A6] mono">
                        {t.dataset.symbol} · {t.dataset.timeframe} · {t.model_ids.length} models
                      </div>
                    </div>
                    <StatusPill status={t.status} />
                    <div className="flex items-center gap-1 text-[10px] text-[#4A5568]">
                      <Clock size={9} />
                      <span>{new Date(t.created_at).toLocaleDateString()}</span>
                    </div>
                    <ChevronRight size={14} className="text-[#4A5568] group-hover:text-[#E6EAF2] transition-colors" />
                  </div>
                </Link>
              ))}

              {runs.slice(0, 3).map(r => (
                <Link key={r.run_id} href={`/arena/${r.run_id}`}>
                  <div className="glass rounded-xl px-4 py-3 flex items-center gap-3 cursor-pointer hover:border-[#2A3550] transition-colors group">
                    <ModelAvatar color={r.model_color} label={r.model_label} size={24} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate" style={{ color: r.model_color }}>{r.model_label}</div>
                      <div className="text-[10px] text-[#8A93A6] mono">
                        {r.dataset.symbol} · {r.dataset.timeframe}
                      </div>
                    </div>
                    {r.metrics && (
                      <span
                        className="mono text-sm font-bold"
                        style={{ color: r.metrics.net_pnl_pct >= 0 ? '#16C784' : '#EA3943' }}
                      >
                        {r.metrics.net_pnl_pct >= 0 ? '+' : ''}{r.metrics.net_pnl_pct.toFixed(2)}%
                      </span>
                    )}
                    <StatusPill status={r.status} />
                    <ChevronRight size={14} className="text-[#4A5568] group-hover:text-[#E6EAF2] transition-colors" />
                  </div>
                </Link>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    complete: { bg: 'rgba(22,199,132,0.12)', text: '#16C784' },
    running: { bg: 'rgba(245,180,60,0.12)', text: '#F5B43C' },
    queued: { bg: 'rgba(138,147,166,0.12)', text: '#8A93A6' },
    error: { bg: 'rgba(234,57,67,0.12)', text: '#EA3943' },
  };
  const c = colors[status] ?? colors.queued;
  return (
    <span className="px-2 py-0.5 rounded-full text-[9px] font-semibold uppercase" style={{ background: c.bg, color: c.text }}>
      {status}
    </span>
  );
}
