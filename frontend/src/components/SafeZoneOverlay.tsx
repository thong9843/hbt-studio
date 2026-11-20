import { useState } from 'react';

export type SafeZonePlatform = 'none' | 'tiktok' | 'shorts' | 'reels';

const LABELS: Record<SafeZonePlatform, string> = {
  none: 'Tắt',
  tiktok: 'TikTok',
  shorts: 'Shorts',
  reels: 'Reels',
};

export function SafeZoneToolbar({
  platform,
  onChange,
}: {
  platform: SafeZonePlatform;
  onChange: (p: SafeZonePlatform) => void;
}) {
  return (
    <div className="flex flex-nowrap items-center justify-center gap-1.5">
      {(['none', 'tiktok', 'shorts', 'reels'] as SafeZonePlatform[]).map((p) => (
        <button
          key={p}
          type="button"
          aria-pressed={platform === p}
          onClick={() => onChange(p)}
          className={`whitespace-nowrap rounded-full border px-2.5 py-1 text-[11.5px] font-semibold transition-colors ${
            platform === p
              ? 'border-primary bg-primary text-on-primary'
              : 'border-line bg-soft text-text-2 hover:bg-soft-2 hover:text-text'
          }`}
        >
          {LABELS[p]}
        </button>
      ))}
    </div>
  );
}

export function SafeZoneOverlay({ platform }: { platform: SafeZonePlatform }) {
  if (platform === 'none') return null;

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 z-10 border-2 border-dashed border-amber-400/60"
    >
      <div className="absolute inset-x-0 top-0 flex h-[12%] items-center justify-center bg-amber-500/15 text-[10px] font-semibold text-amber-200">
        Vùng tránh UI trên ({LABELS[platform]})
      </div>
      <div className="absolute inset-x-0 bottom-0 flex h-[20%] items-center justify-center bg-amber-500/15 text-[10px] font-semibold text-amber-200">
        Vùng tránh mô tả &amp; nút tương tác
      </div>
      <div className="absolute right-0 top-[25%] bottom-[22%] flex w-[14%] items-center justify-center bg-amber-500/10 text-[9px] text-amber-200">
        Icon
      </div>
    </div>
  );
}

export function useSafeZone(initial: SafeZonePlatform = 'none') {
  const [platform, setPlatform] = useState<SafeZonePlatform>(initial);
  return { platform, setPlatform };
}
