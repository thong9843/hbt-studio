import { memo, useState, type ReactNode } from 'react';
import { useRenderJobProgress } from '../../hooks/renderJob';
import { useRemainingText } from '../../hooks/useRemaining';
import { vi } from '../../i18n/vi';
import { DownloadIcon, PlayIcon, StopIcon } from '../icons';
import { WatermarkControl } from '../WatermarkControl';
import { Button } from '../ui/Button';
import { Popover } from '../ui/Popover';
import { Progress } from '../ui/Progress';
import { Switch } from '../ui/Switch';

export interface ExportPopoverProps {
  aspect?: '9:16' | '16:9';
  outroEnabled?: boolean;
  onOutroChange?: (enabled: boolean) => void;
  showWatermarkControl?: boolean;
  onExportPreview?: () => void;
  onExportFinal: () => void;
  previewLabel?: string;
  finalLabel?: string;
  disabled?: boolean;
  isSubmitting?: boolean;
  isRendering?: boolean;
  /** Khi bật, đọc trực tiếp tiến độ từ external store toàn cục để không làm re-render trang cha. */
  subscribeGlobalProgress?: boolean;
  progressPct?: number;
  progressStage?: string;
  progressMessage?: string;
  beatProgressText?: string | null;
  remainingText?: string | null;
  onCancelRender?: () => void;
  extraSettings?: ReactNode;
}

/**
 * Popover Xuất video chuẩn VEED.IO:
 * - Tách wrapper theo `subscribeGlobalProgress` để các trang KHÔNG bật flag này re-render 0 lần
 *   khi job toàn cục cập nhật %.
 */
function ExportPopoverInner({
  aspect = '9:16',
  outroEnabled,
  onOutroChange,
  showWatermarkControl = true,
  onExportPreview,
  onExportFinal,
  previewLabel = vi.studioShell.exportPreviewBtn,
  finalLabel = vi.studioShell.exportFinalBtn,
  disabled = false,
  isSubmitting = false,
  isRendering = false,
  progressPct = 0,
  progressStage = '',
  progressMessage = '',
  beatProgressText = null,
  remainingText = null,
  onCancelRender,
  extraSettings,
}: Omit<ExportPopoverProps, 'subscribeGlobalProgress'>) {
  const [open, setOpen] = useState(false);

  const busy = isSubmitting || isRendering;
  const pct = Math.max(0, Math.min(100, Math.round(progressPct)));
  const stage = progressStage;
  const message = progressMessage;
  const beatText = beatProgressText;
  const remaining = remainingText;

  return (
    <Popover
      open={open}
      onClose={() => setOpen(false)}
      align="right"
      ariaLabel={vi.studioShell.exportPopoverTitle}
      panelClassName="w-[360px]"
      trigger={
        <Button
          tone="brand"
          size="sm"
          icon={<DownloadIcon size={15} />}
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-haspopup="dialog"
          className="relative overflow-hidden"
        >
          <span>
            {isRendering ? vi.studioShell.exportingVideoBtn(pct) : vi.studioShell.exportVideoBtn}
          </span>
          {isRendering && (
            <span
              role="progressbar"
              aria-label={vi.studioShell.liveProgressTitle}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
              className="pointer-events-none absolute inset-x-0 bottom-0 h-1 bg-black/25"
            >
              <span
                className="block h-full origin-left bg-white/95 transition-transform duration-200"
                style={{ transform: `scaleX(${pct / 100})` }}
              />
            </span>
          )}
        </Button>
      }
    >
      <div className="space-y-3.5">
        <div className="flex items-center justify-between border-b border-line pb-2.5">
          <span className="text-small font-bold text-text">
            {vi.studioShell.exportPopoverTitle}
          </span>
          <span className="rounded-pill bg-soft px-2.5 py-0.5 text-tiny font-semibold text-muted tabular-nums">
            {aspect === '16:9'
              ? vi.studioShell.resolutionHorizontal
              : vi.studioShell.resolutionVertical}
          </span>
        </div>

        {onOutroChange !== undefined && outroEnabled !== undefined && (
          <div className="flex items-center justify-between gap-3 rounded-inner border border-line bg-soft px-3 py-2">
            <div className="min-w-0">
              <p className="text-tiny font-bold text-text">{vi.studioShell.outroLabel}</p>
              <p className="text-[11px] text-muted">{vi.studioShell.outroDesc}</p>
            </div>
            <Switch
              checked={outroEnabled}
              onChange={onOutroChange}
              label={vi.studioShell.outroLabel}
              disabled={busy}
            />
          </div>
        )}

        {showWatermarkControl && <WatermarkControl />}

        {extraSettings}

        {isRendering && (
          <div
            role="status"
            aria-label={vi.studioShell.liveProgressTitle}
            className="space-y-2 rounded-inner border border-brand/30 bg-[var(--accent-soft)] p-3"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="truncate text-tiny font-bold text-text">
                <span className="num mr-1.5 text-brand">{pct}%</span>
                <span>{stage || vi.studioShell.liveProgressTitle}</span>
              </p>
              {beatText && (
                <span className="shrink-0 text-[11px] font-semibold text-muted tabular-nums">
                  {beatText}
                </span>
              )}
            </div>
            <Progress value={pct} label={vi.studioShell.liveProgressTitle} />
            <div className="flex items-center justify-between gap-2 pt-0.5">
              <span className="truncate text-[11px] text-muted">{message || remaining || ''}</span>
              {onCancelRender && (
                <Button
                  tone="soft"
                  size="sm"
                  icon={<StopIcon size={13} />}
                  onClick={onCancelRender}
                >
                  {vi.studioShell.cancelRenderBtn}
                </Button>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-2 pt-1">
          {onExportPreview && (
            <Button
              tone="soft"
              size="sm"
              icon={<PlayIcon size={14} />}
              disabled={disabled || busy}
              busy={isSubmitting}
              onClick={onExportPreview}
              className="w-full"
            >
              {previewLabel}
            </Button>
          )}
          <Button
            tone="brand"
            size="md"
            icon={<DownloadIcon size={15} />}
            disabled={disabled || busy}
            busy={isSubmitting}
            onClick={onExportFinal}
            className="w-full"
          >
            {finalLabel}
          </Button>
        </div>
      </div>
    </Popover>
  );
}

function SubscribedExportPopover(props: ExportPopoverProps) {
  const globalProgress = useRenderJobProgress();
  const globalRemaining = useRemainingText();
  const beatText =
    globalProgress.totalBeats != null &&
    globalProgress.totalBeats > 0 &&
    globalProgress.currentBeat != null
      ? vi.stickvJob.beatProgress(globalProgress.currentBeat, globalProgress.totalBeats)
      : props.beatProgressText;
  return (
    <ExportPopoverInner
      {...props}
      progressPct={globalProgress.percent}
      progressStage={globalProgress.stage || globalProgress.step || props.progressStage}
      progressMessage={globalProgress.message || props.progressMessage}
      beatProgressText={beatText}
      remainingText={globalRemaining ?? props.remainingText}
    />
  );
}

export const ExportPopover = memo(function ExportPopover(props: ExportPopoverProps) {
  if (props.subscribeGlobalProgress) {
    return <SubscribedExportPopover {...props} />;
  }
  return <ExportPopoverInner {...props} />;
});
