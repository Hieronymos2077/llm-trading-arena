'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { ChevronLeft, Trophy, User, Check } from 'lucide-react';
import Link from 'next/link';
import { getModels, getSymbols, getDatasets, startSoloRun, startTournament } from '@/lib/api';
import type { DatasetMeta } from '@/lib/api';
import type { ModelInfo, DatasetSpec } from '@/lib/types';
import { ModelAvatar } from '@/components/ui/ModelAvatar';

type Mode = 'solo' | 'tournament';

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'];

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState<'mode' | 'models' | 'data' | 'config'>('mode');
  const [mode, setMode] = useState<Mode>('tournament');
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [limit, setLimit] = useState(1500);
  const [source, setSource] = useState<'binance' | 'mt5' | 'csv'>('csv');
  const [datasets, setDatasets] = useState<DatasetMeta[]>([]);
  const [csvDatasetId, setCsvDatasetId] = useState('');
  const [symbolSearch, setSymbolSearch] = useState('');
  const [startingEquity, setStartingEquity] = useState(10000);
  const [riskPct, setRiskPct] = useState(1.0);
  const [targetTrades, setTargetTrades] = useState(50);
  const [allowShort, setAllowShort] = useState(true);
  const [trigger, setTrigger] = useState<'signals' | 'cadence'>('signals');
  const [launching, setLaunching] = useState(false);

  useEffect(() => {
    getModels().then(setModels);
    getDatasets().then(ds => {
      setDatasets(ds);
      if (ds.length > 0) {
        // Prefer XAU/GOLD (volatile), else most-recently-added (last in list), else first
        const preferred =
          ds.find(d => d.symbol.toUpperCase().includes('XAU') || d.symbol.toUpperCase().includes('GOLD')) ??
          ds[ds.length - 1];
        setCsvDatasetId(preferred.dataset_id);
        setSymbol(preferred.symbol);
        setTimeframe(preferred.timeframe);
      } else {
        setSource('binance');
        getSymbols('binance').then(setSymbols);
      }
    });
  }, []);

  useEffect(() => {
    if (source === 'binance' || source === 'mt5') getSymbols(source).then(setSymbols);
  }, [source]);

  const toggleModel = (id: string) => {
    setSelectedModels(prev =>
      prev.includes(id) ? prev.filter(m => m !== id) : [...prev, id]
    );
  };

  const canProceed = () => {
    if (step === 'mode') return true;
    if (step === 'models') return selectedModels.length > 0 && (mode === 'tournament' ? selectedModels.length >= 2 : selectedModels.length === 1);
    if (step === 'data') return source === 'csv' ? !!csvDatasetId : symbol.length > 0;
    return true;
  };

  const next = () => {
    if (step === 'mode') setStep('models');
    else if (step === 'models') setStep('data');
    else if (step === 'data') setStep('config');
  };

  const launch = async () => {
    setLaunching(true);
    try {
      const dataset: DatasetSpec = source === 'csv'
        ? { source: 'csv', symbol, timeframe, limit, csv_dataset_id: csvDatasetId }
        : { source, symbol, timeframe, limit };
      const config = {
        starting_equity: startingEquity,
        risk_per_trade_pct: riskPct,
        target_trades: targetTrades,
        allow_short: allowShort,
        decision_trigger: trigger,
        decision_cadence: 3,
        lookback: 120,
        max_trade_bars: 60,
        indicators: [
          'ema10','ema20','ema30','ema50','ema100','ema200',
          'sma10','sma20','sma30','sma50','sma100','sma200',
          'rsi14','stoch_k','stoch_d','cci20','adx14','plus_di','minus_di',
          'ao','momentum10','williams_r14','macd','macd_signal','macd_hist',
          'atr14','bb_upper','bb_mid','bb_lower',
          'ichimoku_tenkan','ichimoku_kijun','ichimoku_senkou_a','ichimoku_senkou_b',
          'pivot_p','pivot_r1','pivot_r2','pivot_s1','pivot_s2',
        ],
      };

      if (mode === 'tournament') {
        const { tournament_id } = await startTournament({ model_ids: selectedModels, dataset, config });
        router.push(`/arena/${tournament_id}`);
      } else {
        const { run_id } = await startSoloRun({ model_id: selectedModels[0], dataset, config });
        router.push(`/arena/${run_id}`);
      }
    } catch (e) {
      alert(`Launch failed: ${e}`);
      setLaunching(false);
    }
  };

  const steps = ['mode', 'models', 'data', 'config'];
  const stepIdx = steps.indexOf(step);

  return (
    <div className="min-h-screen bg-[#06090F] grid-bg flex flex-col">

      <header className="relative z-10 px-6 py-4 border-b border-[#1E2636] flex items-center gap-3">
        <Link href="/" className="text-[#8A93A6] hover:text-[#E6EAF2] transition-colors cursor-pointer">
          <ChevronLeft size={18} />
        </Link>
        <span className="font-bold text-sm text-[#E6EAF2]">Setup New Run</span>

        {/* Step indicators */}
        <div className="flex items-center gap-1 ml-auto">
          {steps.map((s, i) => (
            <div key={s} className="flex items-center gap-1">
              <div
                className="w-2 h-2 rounded-full transition-colors"
                style={{ background: i <= stepIdx ? '#16C784' : '#1E2636' }}
              />
              {i < steps.length - 1 && <div className="w-4 h-px" style={{ background: i < stepIdx ? '#16C784' : '#1E2636' }} />}
            </div>
          ))}
        </div>
      </header>

      <div className="relative z-10 flex-1 flex items-start justify-center py-12 px-6">
        <motion.div
          key={step}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.25 }}
          className="w-full max-w-2xl"
        >
          {/* Mode */}
          {step === 'mode' && (
            <div>
              <h2 className="text-2xl font-bold text-[#E6EAF2] mb-2">Choose Mode</h2>
              <p className="text-[#8A93A6] text-sm mb-6">How do you want to run?</p>
              <div className="grid grid-cols-2 gap-4">
                {([
                  { id: 'tournament' as Mode, icon: Trophy, label: 'Tournament', desc: 'Multiple models race on the same data', color: '#F5B43C' },
                  { id: 'solo' as Mode, icon: User, label: 'Solo', desc: 'One model, deep review & commentary', color: '#7CACF8' },
                ]).map(({ id, icon: Icon, label, desc, color }) => (
                  <button
                    key={id}
                    onClick={() => setMode(id)}
                    className="glass rounded-2xl p-5 text-left cursor-pointer transition-all"
                    style={mode === id ? { borderColor: color, boxShadow: `0 0 20px ${color}20` } : {}}
                  >
                    <div className="w-9 h-9 rounded-xl flex items-center justify-center mb-3" style={{ background: `${color}18` }}>
                      <Icon size={18} style={{ color }} />
                    </div>
                    <div className="font-bold text-[#E6EAF2] mb-1">{label}</div>
                    <div className="text-[11px] text-[#8A93A6]">{desc}</div>
                    {mode === id && (
                      <div className="mt-3 flex items-center gap-1 text-[10px] font-semibold" style={{ color }}>
                        <Check size={10} />
                        Selected
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Models */}
          {step === 'models' && (
            <div>
              <h2 className="text-2xl font-bold text-[#E6EAF2] mb-2">
                Select {mode === 'tournament' ? 'Models (2+)' : 'Model'}
              </h2>
              <p className="text-[#8A93A6] text-sm mb-6">
                {mode === 'tournament' ? 'Choose at least 2 models to compete' : 'Choose 1 model to review'}
              </p>
              <div className="grid grid-cols-2 gap-2">
                {models.map(m => {
                  const isSelected = selectedModels.includes(m.id);
                  return (
                    <button
                      key={m.id}
                      onClick={() => {
                        if (mode === 'solo') setSelectedModels(isSelected ? [] : [m.id]);
                        else toggleModel(m.id);
                      }}
                      className="glass rounded-xl p-3 flex items-center gap-3 cursor-pointer transition-all text-left"
                      style={isSelected ? { borderColor: m.color, boxShadow: `0 0 16px ${m.color}20` } : {}}
                    >
                      <ModelAvatar color={m.color} label={m.label} size={28} isSelected={isSelected} />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold truncate" style={{ color: isSelected ? m.color : '#E6EAF2' }}>
                          {m.label}
                        </div>
                        <div className="flex items-center gap-1 mt-0.5">
                          <div className="w-1 h-1 rounded-full" style={{ background: m.available ? '#16C784' : '#4A5568' }} />
                          <span className="text-[9px]" style={{ color: m.available ? '#16C784' : '#4A5568' }}>
                            {m.available ? 'Available' : 'No key'}
                          </span>
                        </div>
                      </div>
                      {isSelected && <Check size={12} style={{ color: m.color }} />}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Data */}
          {step === 'data' && (
            <div>
              <h2 className="text-2xl font-bold text-[#E6EAF2] mb-2">Data Source</h2>
              <p className="text-[#8A93A6] text-sm mb-6">Configure the market data for the run</p>

              <div className="glass rounded-xl p-5 flex flex-col gap-4">
                {/* Source selector */}
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-[#8A93A6] mb-2 block">Source</label>
                  <div className="flex gap-1.5">
                    {([['csv', 'MT5 / CSV'], ['binance', 'Binance'], ['mt5', 'MT5 live']] as const).map(([s, lbl]) => (
                      <button
                        key={s}
                        onClick={() => setSource(s)}
                        className="px-3 py-1.5 rounded-lg text-[10px] mono font-medium cursor-pointer transition-colors"
                        style={source === s
                          ? { background: 'rgba(22,199,132,0.15)', color: '#16C784', border: '1px solid rgba(22,199,132,0.4)' }
                          : { background: '#121826', color: '#8A93A6', border: '1px solid #1E2636' }
                        }
                      >
                        {lbl}
                      </button>
                    ))}
                  </div>
                </div>

                {source === 'csv' ? (
                  <div>
                    <label className="text-[10px] uppercase tracking-wider text-[#8A93A6] mb-2 block">Dataset</label>
                    {datasets.length === 0 ? (
                      <div className="text-[11px] text-[#8A93A6] py-2">No CSV datasets found. Upload one (or switch to Binance).</div>
                    ) : (
                      <div className="grid grid-cols-2 gap-1.5">
                        {datasets.map(d => (
                          <button
                            key={d.dataset_id}
                            onClick={() => { setCsvDatasetId(d.dataset_id); setSymbol(d.symbol); setTimeframe(d.timeframe); }}
                            className="px-3 py-2 rounded-lg text-left cursor-pointer transition-colors"
                            style={csvDatasetId === d.dataset_id
                              ? { background: 'rgba(22,199,132,0.15)', border: '1px solid rgba(22,199,132,0.4)' }
                              : { background: '#121826', border: '1px solid #1E2636' }
                            }
                          >
                            <div className="text-xs font-semibold mono" style={{ color: csvDatasetId === d.dataset_id ? '#16C784' : '#E6EAF2' }}>{d.symbol}</div>
                            <div className="text-[9px] text-[#8A93A6] mono">{d.timeframe} · {d.bar_count.toLocaleString()} bars</div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    <div>
                      <label className="text-[10px] uppercase tracking-wider text-[#8A93A6] mb-2 block">Symbol</label>
                      <input
                        type="text"
                        placeholder="Search symbols…"
                        value={symbolSearch}
                        onChange={e => setSymbolSearch(e.target.value.toUpperCase())}
                        className="w-full px-3 py-1.5 mb-2 rounded-lg text-xs mono bg-[#121826] border border-[#1E2636] text-[#E6EAF2] placeholder-[#4A5568] outline-none focus:border-[#2A3550]"
                      />
                      {(() => {
                        const base = symbols.length > 0 ? symbols : ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'];
                        const filtered = symbolSearch ? base.filter(s => s.includes(symbolSearch)) : base;
                        const visible = filtered.slice(0, 50);
                        return (
                          <>
                            <div className="grid grid-cols-4 gap-1.5 max-h-48 overflow-y-auto pr-1">
                              {visible.map(s => (
                                <button
                                  key={s}
                                  onClick={() => setSymbol(s)}
                                  className="px-2 py-1.5 rounded-lg text-[10px] mono font-medium cursor-pointer transition-colors"
                                  style={symbol === s
                                    ? { background: 'rgba(22,199,132,0.15)', color: '#16C784', border: '1px solid rgba(22,199,132,0.4)' }
                                    : { background: '#121826', color: '#8A93A6', border: '1px solid #1E2636' }
                                  }
                                >
                                  {s.replace('USDT', '')}
                                </button>
                              ))}
                            </div>
                            <div className="text-[9px] text-[#4A5568] mt-1">
                              {filtered.length > 50
                                ? `Showing 50 of ${filtered.length}, type to narrow`
                                : symbols.length > 0
                                  ? `${filtered.length} of ${symbols.length} symbols`
                                  : ''}
                            </div>
                          </>
                        );
                      })()}
                    </div>

                    <div>
                      <label className="text-[10px] uppercase tracking-wider text-[#8A93A6] mb-2 block">Timeframe</label>
                      <div className="flex gap-1.5 flex-wrap">
                        {TIMEFRAMES.map(tf => (
                          <button
                            key={tf}
                            onClick={() => setTimeframe(tf)}
                            className="px-3 py-1.5 rounded-lg text-[10px] mono font-medium cursor-pointer transition-colors"
                            style={timeframe === tf
                              ? { background: 'rgba(22,199,132,0.15)', color: '#16C784', border: '1px solid rgba(22,199,132,0.4)' }
                              : { background: '#121826', color: '#8A93A6', border: '1px solid #1E2636' }
                            }
                          >
                            {tf}
                          </button>
                        ))}
                      </div>
                    </div>
                  </>
                )}

                <div>
                  <label className="text-[10px] uppercase tracking-wider text-[#8A93A6] mb-2 block">
                    Bars, {limit.toLocaleString()}{source === 'csv' ? ' (most recent window of the dataset)' : ''}
                  </label>
                  <input
                    type="range" min={200} max={5000} step={100}
                    value={limit}
                    onChange={e => setLimit(Number(e.target.value))}
                    className="w-full accent-[#16C784]"
                  />
                  <div className="flex justify-between text-[9px] text-[#4A5568] mt-1">
                    <span>200</span><span>5000</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Config */}
          {step === 'config' && (
            <div>
              <h2 className="text-2xl font-bold text-[#E6EAF2] mb-2">Configuration</h2>
              <p className="text-[#8A93A6] text-sm mb-6">Tune risk and run parameters</p>

              <div className="glass rounded-xl p-5 flex flex-col gap-4">
                <Slider label="Starting Equity" value={startingEquity} min={1000} max={100000} step={1000} format={v => `$${v.toLocaleString()}`} onChange={setStartingEquity} />
                <Slider label="Risk per Trade %" value={riskPct} min={0.1} max={5} step={0.1} format={v => `${v.toFixed(1)}%`} onChange={setRiskPct} />
                <Slider label="Target Trades" value={targetTrades} min={10} max={100} step={5} format={v => `${v}`} onChange={setTargetTrades} />

                <div>
                  <label className="text-[10px] uppercase tracking-wider text-[#8A93A6] mb-2 block">Decision Trigger</label>
                  <div className="flex gap-2">
                    {(['signals', 'cadence'] as const).map(t => (
                      <button key={t} onClick={() => setTrigger(t)}
                        className="px-3 py-1.5 rounded-lg text-[10px] font-medium cursor-pointer transition-colors capitalize"
                        style={trigger === t
                          ? { background: 'rgba(22,199,132,0.15)', color: '#16C784', border: '1px solid rgba(22,199,132,0.4)' }
                          : { background: '#121826', color: '#8A93A6', border: '1px solid #1E2636' }
                        }
                      >{t}</button>
                    ))}
                  </div>
                </div>

                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={allowShort}
                    onChange={e => setAllowShort(e.target.checked)}
                    className="w-4 h-4 accent-[#16C784]"
                  />
                  <span className="text-sm text-[#E6EAF2]">Allow Short Positions</span>
                </label>
              </div>
            </div>
          )}

          {/* Nav buttons */}
          <div className="flex items-center gap-3 mt-8">
            {stepIdx > 0 && (
              <button
                onClick={() => {
                  const s = steps[stepIdx - 1];
                  setStep(s as typeof step);
                }}
                className="px-4 py-2 rounded-xl text-sm text-[#8A93A6] border border-[#1E2636] hover:border-[#2A3550] hover:text-[#E6EAF2] transition-colors cursor-pointer"
              >
                Back
              </button>
            )}
            {step !== 'config' ? (
              <button
                onClick={next}
                disabled={!canProceed()}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all cursor-pointer"
                style={canProceed()
                  ? { background: '#16C784', color: '#06090F', boxShadow: '0 0 20px rgba(22,199,132,0.3)' }
                  : { background: '#1A2236', color: '#4A5568', cursor: 'not-allowed' }
                }
              >
                Continue
              </button>
            ) : (
              <button
                onClick={launch}
                disabled={launching}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all cursor-pointer"
                style={{ background: '#16C784', color: '#06090F', boxShadow: '0 0 20px rgba(22,199,132,0.3)', opacity: launching ? 0.6 : 1 }}
              >
                {launching ? 'Launching…' : 'Launch Run'}
              </button>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step, format, onChange }: {
  label: string; value: number; min: number; max: number; step: number;
  format: (v: number) => string; onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-[10px] uppercase tracking-wider text-[#8A93A6]">{label}</label>
        <span className="mono text-xs text-[#E6EAF2]">{format(value)}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-[#16C784]"
      />
    </div>
  );
}
