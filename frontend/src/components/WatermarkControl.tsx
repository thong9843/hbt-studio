import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api/endpoints';
import type { AppSettings, WatermarkSettings } from '../api/types';

const DEFAULT_WM: WatermarkSettings = {
  enabled: true,
  mode: 'logo',
  text: '@HayBietTuot',
  logo_path: 'brand/hbt-logo-mark.png',
  position: 'top-right',
  opacity: 0.4,
};

const POS_LABELS: Record<WatermarkSettings['position'], string> = {
  'top-right': 'Góc trên phải',
  'top-left': 'Góc trên trái',
  'center-subtle': 'Giữa mờ',
};

function modeSummary(wm: WatermarkSettings): string {
  if (wm.mode === 'logo') return 'Logo HBT Studio';
  if (wm.mode === 'text') return wm.text || '@HayBietTuot';
  return `Logo + ${wm.text || '@HayBietTuot'}`;
}

export function useWatermarkSettings() {
  const queryClient = useQueryClient();
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

  return { wm, updateWm, isSaving: save.isPending };
}

export function WatermarkControl() {
  const [expanded, setExpanded] = useState(false);
  const { wm, updateWm } = useWatermarkSettings();

  return (
    <div className="rounded-inner border border-[#C7D2FE] bg-gradient-to-r from-[#EEF2FF] to-[#F5F3FF] p-3 text-xs text-slate-900 shadow-sm dark:border-indigo-400/30 dark:from-[#1E1B4B] dark:to-[#1E1B4B] dark:text-slate-100">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="inline-flex cursor-pointer items-center gap-2 font-bold">
          <input
            type="checkbox"
            checked={wm.enabled}
            onChange={(e) => updateWm({ enabled: e.target.checked })}
            className="h-4 w-4 accent-indigo-600"
          />
          <span>Watermark bản quyền</span>
          <span
            className={`rounded-pill px-2 py-0.5 text-[11px] font-bold ${
              wm.enabled
                ? 'bg-indigo-600 text-white dark:bg-indigo-500'
                : 'bg-slate-200 text-slate-600 dark:bg-white/10 dark:text-slate-300'
            }`}
          >
            {wm.enabled ? `${modeSummary(wm)} · ${POS_LABELS[wm.position]}` : 'Đã tắt'}
          </span>
        </label>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="rounded-lg border border-indigo-300/70 bg-white/80 px-2.5 py-1 text-[11px] font-bold text-indigo-700 transition hover:bg-white dark:border-indigo-400/30 dark:bg-white/10 dark:text-indigo-200 dark:hover:bg-white/15"
        >
          {expanded ? 'Thu gọn' : 'Tùy chỉnh'}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 grid grid-cols-1 gap-2.5 border-t border-indigo-200/80 pt-3 dark:border-indigo-400/20 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-slate-600 dark:text-indigo-200">
              Kiểu hiển thị
            </label>
            <select
              aria-label="Kiểu Watermark"
              value={wm.mode}
              onChange={(e) => updateWm({ mode: e.target.value as WatermarkSettings['mode'] })}
              className="w-full rounded-lg border border-indigo-200 bg-white px-2 py-1.5 text-xs font-semibold text-slate-900 dark:border-indigo-400/30 dark:bg-slate-900 dark:text-white"
            >
              <option value="both">Logo + Chữ (@HayBietTuot)</option>
              <option value="text">Chỉ chữ (@HayBietTuot)</option>
              <option value="logo">Chỉ Logo HBT</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-slate-600 dark:text-indigo-200">
              Vị trí Safe-Zone
            </label>
            <select
              aria-label="Vị trí Watermark"
              value={wm.position}
              onChange={(e) =>
                updateWm({ position: e.target.value as WatermarkSettings['position'] })
              }
              className="w-full rounded-lg border border-indigo-200 bg-white px-2 py-1.5 text-xs font-semibold text-slate-900 dark:border-indigo-400/30 dark:bg-slate-900 dark:text-white"
            >
              <option value="top-right">Góc trên phải (Chuẩn)</option>
              <option value="top-left">Góc trên trái</option>
              <option value="center-subtle">Giữa khung (Chìm)</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-slate-600 dark:text-indigo-200">
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
              className="w-full accent-indigo-600"
            />
          </div>
        </div>
      )}
    </div>
  );
}
