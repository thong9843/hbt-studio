import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api/endpoints';
import type { AppSettings, WatermarkSettings } from '../api/types';

const DEFAULT_WM: WatermarkSettings = {
  enabled: true,
  mode: 'both',
  text: '@HayBietTuot',
  logo_path: 'brand/hbt-logo-mark.png',
  position: 'top-right',
  opacity: 0.35,
};

const POS_LABELS: Record<WatermarkSettings['position'], string> = {
  'top-right': 'Góc trên phải',
  'top-left': 'Góc trên trái',
  'center-subtle': 'Giữa mờ',
};

export function WatermarkControl() {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.getAppSettings(),
  });

  const wm: WatermarkSettings = { ...DEFAULT_WM, ...(settings?.watermark ?? {}) };

  const save = useMutation({
    mutationFn: (nextWm: WatermarkSettings) => {
      const base: AppSettings = settings ?? {
        default_fps: 60,
        theme: { primary: '#146268', accent: '#DE5C48' },
        whisper_model: 'auto',
        whisper_timeout_seconds: 900,
      };
      return api.saveAppSettings({ ...base, watermark: nextWm });
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(['settings'], saved);
    },
  });

  const updateWm = (patch: Partial<WatermarkSettings>) => {
    save.mutate({ ...wm, ...patch });
  };

  return (
    <div className="rounded-xl border border-white/10 bg-[#131720] p-2.5 text-xs text-[#F8FAFC]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="inline-flex cursor-pointer items-center gap-2 font-bold">
          <input
            type="checkbox"
            checked={wm.enabled}
            onChange={(e) => updateWm({ enabled: e.target.checked })}
            className="h-4 w-4 accent-[#D9232E]"
          />
          <span>Watermark bản quyền</span>
          <span className="rounded-md bg-[#FACC15]/15 px-1.5 py-0.5 text-[11px] font-semibold text-[#FACC15]">
            {wm.enabled ? `${wm.text || 'Logo'} · ${POS_LABELS[wm.position]}` : 'Đã tắt'}
          </span>
        </label>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-[11px] font-semibold text-[#94A3B8] hover:text-white"
        >
          {expanded ? 'Thu gọn' : 'Tùy chỉnh'}
        </button>
      </div>

      {expanded && (
        <div className="mt-2.5 grid grid-cols-1 gap-2 border-t border-white/10 pt-2.5 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-[11px] text-[#94A3B8]">Kiểu hiển thị</label>
            <select
              aria-label="Kiểu Watermark"
              value={wm.mode}
              onChange={(e) => updateWm({ mode: e.target.value as WatermarkSettings['mode'] })}
              className="w-full rounded-lg border border-white/15 bg-[#0B0D12] px-2 py-1 text-xs text-white"
            >
              <option value="both">Logo + Chữ (@HayBietTuot)</option>
              <option value="text">Chỉ chữ (@HayBietTuot)</option>
              <option value="logo">Chỉ Logo HBT</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-[11px] text-[#94A3B8]">Vị trí Safe-Zone</label>
            <select
              aria-label="Vị trí Watermark"
              value={wm.position}
              onChange={(e) =>
                updateWm({ position: e.target.value as WatermarkSettings['position'] })
              }
              className="w-full rounded-lg border border-white/15 bg-[#0B0D12] px-2 py-1 text-xs text-white"
            >
              <option value="top-right">Góc trên phải (Chuẩn)</option>
              <option value="top-left">Góc trên trái</option>
              <option value="center-subtle">Giữa khung (Chìm)</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-[11px] text-[#94A3B8]">
              Độ mờ ({Math.round(wm.opacity * 100)}%)
            </label>
            <input
              type="range"
              aria-label="Độ mờ Watermark"
              min={0.15}
              max={0.8}
              step={0.05}
              value={wm.opacity}
              onChange={(e) => updateWm({ opacity: Number(e.target.value) })}
              className="w-full accent-[#FACC15]"
            />
          </div>
        </div>
      )}
    </div>
  );
}
