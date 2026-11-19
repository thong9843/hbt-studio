import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api/endpoints';
import type { AppSettings, WatermarkSettings } from '../api/types';
import { vi } from '../i18n/vi';
import { StudioSelect, type StudioSelectOption } from './ui/StudioSelect';
import { Switch } from './ui/Switch';

const DEFAULT_WM: WatermarkSettings = {
  enabled: true,
  mode: 'logo',
  text: '@HayBietTuot',
  logo_path: 'brand/hbt-logo-mark.png',
  position: 'bottom-right',
  opacity: 0.4,
};

const POS_LABELS: Record<WatermarkSettings['position'], string> = {
  'bottom-right': 'Góc dưới phải',
  'bottom-left': 'Góc dưới trái',
  'top-right': 'Góc trên phải',
  'top-left': 'Góc trên trái',
  'center-subtle': 'Giữa mờ',
};

const MODE_OPTIONS: StudioSelectOption[] = [
  { value: 'both', label: 'Logo + Chữ (@HayBietTuot)' },
  { value: 'text', label: 'Chỉ chữ (@HayBietTuot)' },
  { value: 'logo', label: 'Chỉ Logo HBT' },
];

const POSITION_OPTIONS: StudioSelectOption[] = [
  { value: 'bottom-right', label: 'Góc dưới phải (Chuẩn)' },
  { value: 'bottom-left', label: 'Góc dưới trái' },
  { value: 'top-right', label: 'Góc trên phải' },
  { value: 'top-left', label: 'Góc trên trái' },
  { value: 'center-subtle', label: 'Giữa khung (Chìm)' },
];

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
  const W = vi.watermark;

  return (
    <div className="rounded-inner border border-border-subtle bg-surface-card p-3.5 text-xs text-text shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex min-w-0 flex-wrap items-center gap-2.5">
          <Switch
            checked={wm.enabled}
            onChange={(checked) => updateWm({ enabled: checked })}
            label={W.title}
          />
          <span className="font-bold text-text">{W.title}</span>
          <span className={wm.enabled ? 'ui-wm-badge' : 'ui-wm-badge ui-wm-badge-off'}>
            {wm.enabled ? `${modeSummary(wm)} · ${POS_LABELS[wm.position]}` : W.disabled}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="rounded-lg border border-border-subtle bg-elevated px-2.5 py-1 text-[11px] font-bold text-text-2 transition-colors hover:bg-soft hover:text-text"
        >
          {expanded ? W.collapse : W.customize}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 grid grid-cols-1 gap-3 border-t border-border-subtle pt-3 sm:grid-cols-3">
          <div>
            <span className="mb-1 block text-[11px] font-semibold text-muted">{W.modeLabel}</span>
            <StudioSelect
              aria-label={W.modeAria}
              variant="compact"
              value={wm.mode}
              onChange={(val) => updateWm({ mode: val as WatermarkSettings['mode'] })}
              options={MODE_OPTIONS}
            />
          </div>

          <div>
            <span className="mb-1 block text-[11px] font-semibold text-muted">
              {W.positionLabel}
            </span>
            <StudioSelect
              aria-label={W.positionAria}
              variant="compact"
              value={wm.position}
              onChange={(val) => updateWm({ position: val as WatermarkSettings['position'] })}
              options={POSITION_OPTIONS}
            />
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-muted">
              {W.opacityLabel(Math.round(wm.opacity * 100))}
            </label>
            <input
              type="range"
              aria-label={W.opacityAria}
              min={0.15}
              max={0.8}
              step={0.05}
              value={wm.opacity}
              onChange={(e) => updateWm({ opacity: Number(e.target.value) })}
              className="mt-1.5 w-full accent-brand"
            />
          </div>
        </div>
      )}
    </div>
  );
}
