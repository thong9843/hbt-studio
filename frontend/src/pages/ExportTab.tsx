import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchHealth, fetchText } from '../api/client';
import { api } from '../api/endpoints';
import type { Job, LintIssue, LintResult, RenderOptions, RenderRecord } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { useProjectEditor } from '../hooks/projectEditor';
import { useJob } from '../hooks/useJob';
import { vi } from '../i18n/vi';
import { formatBytes, formatDateTime, formatDuration } from '../utils/format';
import { sceneNumber } from '../utils/scene';

const X = vi.export;
const LEVEL_CHIP = { block: 'chip-danger', warn: 'chip-warn', info: 'chip-muted' } as const;

function issueScope(issue: LintIssue): string {
  return issue.scene_index === null
    ? X.checks.wholeVideo
    : X.checks.scene(sceneNumber(issue.scene_index));
}

function Checks({ lint }: { lint: { data?: LintResult; isPending: boolean; error: unknown } }) {
  const data = lint.data;
  return (
    <section className="space-y-3">
      <h2 className="text-2xl">{X.checks.title}</h2>
      {lint.isPending && <p className="text-muted">{X.checks.running}</p>}
      <ErrorNote error={lint.error} />
      {data && data.problems.length === 0 && data.issues.length === 0 && (
        <p className="chip chip-ok">{X.checks.ok}</p>
      )}
      {data && data.problems.length > 0 && (
        <ul className="space-y-1">
          {data.problems.map((p) => (
            <li key={p} className="flex items-center gap-2 text-sm">
              <span className="chip chip-danger">{X.checks.missing}</span>
              {p}
            </li>
          ))}
        </ul>
      )}
      {data && data.issues.length > 0 && (
        <ul className="space-y-1">
          {data.issues.map((issue, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
              <span className={`chip ${LEVEL_CHIP[issue.level]}`}>{X.checks[issue.level]}</span>
              <b>{issueScope(issue)}</b>
              <span>{issue.message}</span>
              {issue.hint && <span className="text-muted">{issue.hint}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PublishBox({ url }: { url: string }) {
  const text = useQuery({
    queryKey: ['publish', url],
    queryFn: () => fetchText(url),
    retry: false,
  });
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text.data ?? '');
      setState('copied');
    } catch {
      setState('failed');
    }
  };
  return (
    <section className="space-y-3">
      <h3 className="text-lg font-extrabold">{X.publish.title}</h3>
      <textarea
        readOnly
        rows={8}
        aria-label={X.publish.title}
        className="input font-mono"
        value={text.data ?? ''}
      />
      <div className="flex items-center gap-3">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void copy()}>
          {state === 'copied' ? X.publish.copied : X.publish.copy}
        </button>
        {state === 'failed' && <span className="text-sm text-danger">{X.publish.copyFailed}</span>}
      </div>
    </section>
  );
}

function ResultView({ job }: { job: Job }) {
  const out = job.output;
  if (!out) return null;
  const R = X.result;
  return (
    <section className="space-y-5">
      <h2 className="text-2xl">{R.title}</h2>
      <video
        controls
        aria-label={X.player}
        className="mx-auto max-h-[70vh] rounded-2xl bg-black"
        src={out.video}
      />
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
        {[
          [R.duration, formatDuration(out.duration)],
          [R.fps, String(out.fps)],
          [R.lufs, `${out.lufs.toFixed(1)} LUFS`],
          [R.aligner, out.aligner],
          [R.seconds, `${out.seconds} ${vi.common.seconds}`],
        ].map(([k, v]) => (
          <div key={k} className="card p-3">
            <dt className="label mb-0">{k}</dt>
            <dd className="font-extrabold">{v}</dd>
          </div>
        ))}
      </dl>
      {out.warnings.length > 0 && (
        <div className="rounded-2xl bg-warn-bg p-4 text-sm text-warn">
          <b>{R.warnings}</b>
          <ul className="mt-1 list-disc pl-5">
            {out.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <a className="btn btn-primary" href={out.video} download="video.mp4">
          {R.video}
        </a>
        {out.srt && (
          <a className="btn btn-secondary" href={out.srt} download="captions.srt">
            {R.srt}
          </a>
        )}
      </div>
      <PublishBox url={out.publish} />
    </section>
  );
}

function History({
  renders,
  onPlay,
}: {
  renders: RenderRecord[];
  onPlay: (r: RenderRecord) => void;
}) {
  const H = X.history;
  return (
    <section className="space-y-3">
      <h2 className="text-2xl">{H.title}</h2>
      {renders.length === 0 && <p className="text-muted">{H.empty}</p>}
      <ul className="space-y-2">
        {renders.map((r) => (
          <li key={r.job_id} className="card flex flex-wrap items-center gap-3 p-3 text-sm">
            <span className={`chip ${r.preview ? 'chip-muted' : 'chip-ok'}`}>
              {r.preview ? H.fast : H.final}
            </span>
            <span>{formatDateTime(r.created_at)}</span>
            <span className="text-muted">
              {r.duration ? formatDuration(r.duration) : ''}
              {r.fps ? ` · ${r.fps} fps` : ''}
              {` · ${formatBytes(r.size)}`}
              {r.aligner ? ` · ${r.aligner}` : ''}
            </span>
            <span className="ml-auto flex gap-2">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => onPlay(r)}>
                {H.play}
              </button>
              {r.video && (
                <a className="btn btn-ghost btn-sm" href={r.video} download="video.mp4">
                  {H.video}
                </a>
              )}
              {r.srt && (
                <a className="btn btn-ghost btn-sm" href={r.srt} download="captions.srt">
                  {H.srt}
                </a>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ExportTab() {
  const editor = useProjectEditor();
  const { project } = editor;
  const slug = project.slug;
  const queryClient = useQueryClient();
  const outro = project.settings.outro;
  const [jobId, setJobId] = useState<string | null>(null);
  const [lastOptions, setLastOptions] = useState<RenderOptions>({});
  const [finished, setFinished] = useState<Job | null>(null);
  const [played, setPlayed] = useState<RenderRecord | null>(null);
  const health = useQuery({ queryKey: ['health'], queryFn: () => fetchHealth(), retry: false });

  const renders = useQuery({
    queryKey: ['renders', slug],
    queryFn: () => api.listRenders(slug),
  });

  const { progress, job, connectionError, cancel } = useJob(jobId, (j) => {
    setFinished(j);
    void queryClient.invalidateQueries({ queryKey: ['renders', slug] });
  });

  const lint = useQuery({
    queryKey: ['lint', slug, editor.savedCount],
    queryFn: () => api.lint(slug),
    retry: false,
  });
  const blocked = !!lint.data && (lint.data.blocked || lint.data.problems.length > 0);
  const noFfmpeg = health.data?.ffmpeg === false;

  const start = useMutation({
    mutationFn: async (options: RenderOptions) => {
      await editor.flush();
      return api.startRender(slug, options);
    },
    onSuccess: (res, options) => {
      setLastOptions(options);
      setFinished(null);
      setPlayed(null);
      setJobId(res.job_id);
    },
  });

  const running = jobId !== null && finished === null && !connectionError;
  const launch = (options: RenderOptions) => start.mutate({ ...options, outro });
  const failure = finished?.status === 'failed' ? finished : null;

  return (
    <div className="max-w-4xl space-y-10">
      <Checks lint={lint} />

      <section className="space-y-4">
        <h2 className="text-2xl">{X.title}</h2>
        <label className="flex w-fit items-center gap-3 font-bold">
          <input
            type="checkbox"
            className="h-5 w-5 accent-[var(--color-accent)]"
            checked={outro}
            onChange={(e) => {
              editor.update((p) => ({
                ...p,
                settings: { ...p.settings, outro: e.target.checked },
              }));
            }}
          />
          {X.options.outro}
        </label>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={running || start.isPending || blocked || noFfmpeg}
            onClick={() => launch({ preview: true })}
          >
            {X.fast}
            <span className="text-xs font-medium opacity-70">{X.fastHelp}</span>
          </button>
          <button
            type="button"
            className="btn btn-accent"
            disabled={running || start.isPending || blocked || noFfmpeg}
            onClick={() => launch({ preview: false, fps: 50 })}
          >
            {X.final}
            <span className="text-xs font-medium opacity-80">{X.finalHelp}</span>
          </button>
        </div>
        {blocked && <p className="text-sm font-bold text-danger">{X.blocked}</p>}
        {noFfmpeg && <p className="text-sm font-bold text-danger">{X.missingFfmpeg}</p>}
        <ErrorNote error={start.error} />
      </section>

      {jobId && (
        <section className="space-y-3" aria-live="polite">
          <h2 className="text-2xl">{X.progress}</h2>
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(job?.progress ?? progress.progress)}
            aria-label={X.progress}
            className="h-4 w-full overflow-hidden rounded-full bg-surface-2"
          >
            <div
              className="h-full bg-accent transition-all"
              style={{ width: `${Math.round(job?.progress ?? progress.progress)}%` }}
            />
          </div>
          <p className="text-sm">
            <b>{Math.round(job?.progress ?? progress.progress)}%</b> · {job?.step ?? progress.step}
            {progress.message && <span className="text-muted"> — {progress.message}</span>}
          </p>
          {running && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void cancel()}>
              {X.cancel}
            </button>
          )}
          <ErrorNote error={connectionError} />
          {finished?.status === 'cancelled' && <p className="chip chip-muted">{X.cancelled}</p>}
          {failure && (
            <div className="space-y-3 rounded-2xl bg-danger-bg p-4 text-danger">
              <p role="alert" className="font-bold">
                {X.failed}: {failure.error}
              </p>
              {failure.needs_confirmation && (
                <>
                  <p className="text-sm">{X.confirmTrim}</p>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={() => start.mutate({ ...lastOptions, allow_long_trim: true })}
                  >
                    {X.confirmTrimButton}
                  </button>
                </>
              )}
            </div>
          )}
        </section>
      )}

      {finished?.status === 'done' && !played && <ResultView job={finished} />}
      {played && played.video && (
        <section className="space-y-3">
          <video
            controls
            aria-label={X.player}
            className="mx-auto max-h-[70vh] rounded-2xl bg-black"
            src={played.video}
          />
          {played.publish && <PublishBox url={played.publish} />}
        </section>
      )}

      <History renders={renders.data ?? []} onPlay={setPlayed} />
    </div>
  );
}
