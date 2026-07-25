'use client';

interface ModelAvatarProps {
  color: string;
  label: string;
  size?: number;
  isLeader?: boolean;
  isSelected?: boolean;
}

export function ModelAvatar({ color, label, size = 36, isLeader, isSelected }: ModelAvatarProps) {
  const initials = label.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

  return (
    <div
      className="relative flex-shrink-0"
      style={{ width: size, height: size }}
    >
      {/* Glow ring for leader */}
      {isLeader && (
        <div
          className="absolute inset-0 rounded-full animate-pulse"
          style={{
            boxShadow: `0 0 0 2px #F5B43C, 0 0 16px #F5B43C80`,
            borderRadius: '50%',
          }}
        />
      )}
      {isSelected && !isLeader && (
        <div
          className="absolute inset-0 rounded-full"
          style={{
            boxShadow: `0 0 0 2px ${color}`,
            borderRadius: '50%',
          }}
        />
      )}
      <div
        className="w-full h-full rounded-full flex items-center justify-center font-bold text-[#06090F]"
        style={{
          backgroundColor: color,
          fontSize: size * 0.32,
          boxShadow: `0 0 12px ${color}40`,
        }}
      >
        {initials}
      </div>
    </div>
  );
}
