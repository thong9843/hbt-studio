import { useMutation, useQuery } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { cinemaApi, type CinemaSourcePayload } from '../../api/cinema';
import type {
  CinemaContactSheetResponse,
  CinemaPreflightReport,
  CinemaRenderBeatResponse,
  HbtCoreScript,
  StickvProject,
} from '../../api/types';
import { useReleaseVideoOnUnmount } from '../../hooks/useReleaseVideoOnUnmount';
import { useToast } from '../../hooks/toast';
import { vi } from '../../i18n/vi';
import { AlertIcon, CheckIcon, CpuIcon, EyeIcon, FilmIcon, PlayIcon } from '../icons';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Dialog } from '../ui/Dialog';

const T = vi.cinema;

export interface CinemaInspectorPanelProps {
  stickvProject?: StickvProject;
  coreScript?: HbtCoreScript;
  beatId?: string;
  beatIndex?: number;
  disabled?: boolean;
}

export function CinemaInspectorPanel({
  stickvProject,
  coreScript,
  beatId,
  beatIndex = 0,
  disabled = false,
}: CinemaInspectorPanelProps) {
  const toast = useToast();
  const [preflight, setPreflight] = useState<CinemaPreflightReport | null>(null);
  const [sheet, setSheet] = useState<CinemaContactSheetResponse | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [beatRender, setBeatRender] = useState<CinemaRenderBeatResponse | null>(null);
  const beatVideoRef = useRef<HTMLVideoElement | null>(null);
  useReleaseVideoOnUnmount(beatVideoRef, beatRender?.url);

  const hwQuery = useQuery({
    queryKey: ['cinema-hardware'],
    queryFn: () => cinemaApi.getHardware(),
    retry: false,
    staleTime: 60_000,
  });

  const buildPayload = (): CinemaSourcePayload => {
    if (stickvProject) {
      return {
        stickv_project: stickvProject,
        aspect: stickvProject.aspect,
        fps: stickvProject.fps,
        theme: stickvProject.theme,
      };
    }
    return {
      core_script: coreScript,
      aspect: '9:16',
      fps: 30,
      theme: 'cream',
    };
  };

  const preflightMut = useMutation({
    mutationFn: () => cinemaApi.runPreflight({ ...buildPayload(), auto_fix: true }),
    onSuccess: (data) => setPreflight(data),
    onError: (err) => toast.error(err),
  });

  const sheetMut = useMutation({
    mutationFn: () =>
      cinemaApi.generateContactSheet({ ...buildPayload(), cols: 4, run_preflight: true }),
    onSuccess: (data) => {
      setSheet(data);
      setSheetOpen(true);
    },
    onError: (err) => toast.error(err),
  });

  const beatMut = useMutation({
    mutationFn: () =>
      cinemaApi.renderBeat({
        ...buildPayload(),
        beat_id: beatId,
        beat_index: beatIndex,
        preview: true,
      }),
    onSuccess: (data) => setBeatRender(data),
    onError: (err) => toast.error(err),
  });

  const hasSource = Boolean(
    (stickvProject && stickvProject.beats.length > 0) ||
    (coreScript && coreScript.segments.length > 0),
  );
  const controlsOff = disabled || !hasSource;
  const hw = hwQuery.data;

  return (
    <Card className="space-y-3 border-line bg-card text-text">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FilmIcon size={18} className="text-brand" />
          <div>
            <h3 className="text-small font-extrabold text-text">{T.title}</h3>
            <p className="text-tiny text-muted">{T.subtitle}</p>
          </div>
        </div>
        {hw ? (
          <Badge tone={hw.mode === 'gpu' ? 'yel' : 'ok'}>
            <CpuIcon size={12} />
            <span>
              {hw.mode === 'gpu'
                ? T.hardwareGpu(hw.gpu_name || 'NVENC', hw.layer_cache_mb)
                : T.hardwareCpu(hw.layer_cache_mb, hw.ffmpeg_threads)}
            </span>
          </Badge>
        ) : (
          <Badge tone="neutral">{T.hardwareChecking}</Badge>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          tone="soft"
          disabled={controlsOff}
          busy={preflightMut.isPending}
          icon={<CheckIcon size={14} />}
          onClick={() => preflightMut.mutate()}
        >
          {T.preflightBtn}
        </Button>

        <Button
          size="sm"
          tone="soft"
          disabled={controlsOff}
          busy={sheetMut.isPending}
          icon={<EyeIcon size={14} />}
          onClick={() => sheetMut.mutate()}
        >
          {T.contactSheetBtn}
        </Button>

        <Button
          size="sm"
          tone="ink"
          disabled={controlsOff}
          busy={beatMut.isPending}
          icon={<PlayIcon size={14} />}
          onClick={() => beatMut.mutate()}
        >
          {T.renderBeatBtn}
        </Button>
      </div>

      {preflight && (
        <div className="space-y-2 rounded-inner border border-line bg-soft-2 p-3 text-tiny">
          <div className="flex flex-wrap items-center justify-between gap-2">
            {preflight.ok ? (
              <span className="inline-flex items-center gap-1.5 rounded-pill bg-ok-soft px-2.5 py-0.5 font-bold text-on-ok-soft">
                <CheckIcon size={12} />
                {preflight.fixed_count > 0
                  ? T.preflightFixed(preflight.fixed_count)
                  : T.preflightOk}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-pill bg-danger-soft px-2.5 py-0.5 font-bold text-danger">
                <AlertIcon size={12} />
                {T.preflightHasErrors(preflight.errors.length)}
              </span>
            )}
            <span className="font-semibold text-muted tabular-nums">
              {preflight.repaired_spec.beats.length} beat
            </span>
          </div>

          <div className="flex flex-wrap gap-1.5 text-tiny text-text-2">
            <span className="rounded-pill bg-soft px-2 py-0.5">
              {T.statReflows(preflight.stats.bbox_reflows ?? 0)}
            </span>
            <span className="rounded-pill bg-soft px-2 py-0.5">
              {T.statAntiParrot(preflight.stats.anti_parrot_rewrites ?? 0)}
            </span>
            <span className="rounded-pill bg-soft px-2 py-0.5">
              {T.statPacing(preflight.stats.pacing_diversifications ?? 0)}
            </span>
            <span className="rounded-pill bg-soft px-2 py-0.5">
              {T.statRecap(preflight.stats.recap_conversions ?? 0)}
            </span>
          </div>
        </div>
      )}

      {beatRender && (
        <div className="space-y-2 rounded-inner border border-line bg-soft-2 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span
              className={`inline-flex items-center gap-1 rounded-pill px-2.5 py-0.5 text-tiny font-bold ${
                beatRender.cache_hit ? 'bg-ok-soft text-on-ok-soft' : 'bg-tint-yel text-on-tint-yel'
              }`}
            >
              {beatRender.cache_hit ? T.beatCacheHit : T.beatCacheMiss}
            </span>
            <span className="text-tiny font-semibold text-muted tabular-nums">
              {beatRender.beat_id} · {T.beatElapsed(beatRender.elapsed_ms)}
            </span>
          </div>
          <video
            key={beatRender.url}
            ref={beatVideoRef}
            src={beatRender.url}
            controls
            playsInline
            preload="metadata"
            className="max-h-72 w-full rounded-input bg-hero object-contain"
          />
        </div>
      )}

      <Dialog open={sheetOpen} onClose={() => setSheetOpen(false)} title={T.contactSheetTitle}>
        {sheet && (
          <div className="space-y-3">
            <p className="text-small text-text-2">
              {T.contactSheetMeta(sheet.beats_rendered, sheet.elapsed_ms)}
            </p>
            <img
              src={sheet.url}
              alt={T.contactSheetTitle}
              className="max-h-[70vh] w-full rounded-inner border border-line object-contain bg-soft"
            />
          </div>
        )}
      </Dialog>
    </Card>
  );
}
