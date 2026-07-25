'use client';

interface StatBadgeProps {
  label: string;
  value: string | number;
  positive?: boolean | null;
  mono?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function StatBadge({ label, value, positive, mono = true, size = 'md' }: StatBadgeProps) {
  const color =
    positive === true ? 'text-[#16C784]' :
    positive === false ? 'text-[#EA3943]' :
    'text-[#E6EAF2]';

  const sizeClasses = {
    sm: 'text-xs gap-0.5',
    md: 'text-sm gap-1',
    lg: 'text-base gap-1',
  }[size];

  return (
    <div className={`flex flex-col ${sizeClasses}`}>
      <span className="text-[#8A93A6] uppercase tracking-wider text-[10px] font-medium">{label}</span>
      <span className={`${color} font-semibold ${mono ? 'mono' : ''} leading-tight`}>{value}</span>
    </div>
  );
}

export function PnlValue({ value, prefix = '', suffix = '' }: { value: number; prefix?: string; suffix?: string }) {
  const pos = value >= 0;
  return (
    <span className={pos ? 'glow-up' : 'glow-down'}>
      {prefix}{pos ? '+' : ''}{value.toFixed(2)}{suffix}
    </span>
  );
}
