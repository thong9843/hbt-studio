import { useState } from 'react';
import { CheckIcon } from '../components/icons';
import { Progress } from '../components/ui/Progress';
import { cx } from '../components/ui/cx';

export type WaterfallStepState = 'waiting' | 'running' | 'done' | 'error';

export interface WaterfallStep {
  id: string;
  icon: string;
  title: string;
  state: WaterfallStepState;
  badgeText?: string;
  logs: string[];
}

export interface WaterfallProgressProps {
  title: string;
  overallPercent: number;
  steps: WaterfallStep[];
  error?: string | null;
}

const STATE_LABEL: Record<WaterfallStepState, string> = {
  waiting: 'Chờ',
  running: 'Đang chạy',
  done: 'Xong',
  error: 'Lỗi',
};

/**
 * Dropdown Waterfall Progress Component:
 * Hiển thị tiến trình 4 bước dạng thác nước theo phong cách Dark Studio,
 * cho phép click vào từng bước để mở dropdown xem log chi tiết.
 */
export function WaterfallProgress({ title, overallPercent, steps, error }: WaterfallProgressProps) {
  const [openSteps, setOpenSteps] = useState<Record<string, boolean>>({});

  const toggleStep = (id: string) => {
    setOpenSteps((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <section
      aria-label={title}
      className="space-y-4 rounded-card border border-line bg-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-small font-extrabold text-ink">{title}</p>
        <span className="num text-small font-extrabold text-amber-400">
          {Math.round(overallPercent)}%
        </span>
      </div>

      <Progress value={overallPercent} label={title} />

      <ol className="space-y-2">
        {steps.map((st) => {
          const isOpen = Boolean(openSteps[st.id]);
          const isRunning = st.state === 'running';
          const isDone = st.state === 'done';
          const isError = st.state === 'error';

          return (
            <li
              key={st.id}
              className={cx(
                'overflow-hidden rounded-inner border transition duration-150',
                isRunning
                  ? 'border-indigo-500/70 bg-indigo-500/10'
                  : isDone
                    ? 'border-ok/40 bg-soft-2'
                    : isError
                      ? 'border-danger/50 bg-danger-soft'
                      : 'border-line bg-soft/50',
              )}
            >
              <button
                type="button"
                aria-expanded={isOpen}
                onClick={() => toggleStep(st.id)}
                className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left"
              >
                <div className="flex min-w-0 items-center gap-2.5">
                  <span aria-hidden="true" className="text-base leading-none">
                    {st.icon}
                  </span>
                  <span className="truncate text-small font-bold text-ink">{st.title}</span>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  {st.badgeText && (
                    <span className="rounded-pill bg-soft px-2 py-0.5 text-tiny font-bold text-indigo-300">
                      {st.badgeText}
                    </span>
                  )}
                  <span
                    className={cx(
                      'inline-flex items-center gap-1 rounded-pill px-2.5 py-0.5 text-tiny font-extrabold',
                      isRunning && 'animate-pulse bg-indigo-500/25 text-indigo-300',
                      isDone && 'bg-ok/20 text-ok',
                      isError && 'bg-danger/20 text-danger',
                      st.state === 'waiting' && 'bg-soft text-muted',
                    )}
                  >
                    {isDone && <CheckIcon size={12} strokeWidth={3} />}
                    {STATE_LABEL[st.state]}
                  </span>
                </div>
              </button>

              {isOpen && (
                <div className="border-t border-line/70 bg-bg/70 px-3.5 py-2.5 font-mono text-tiny text-muted">
                  {st.logs.length === 0 ? (
                    <p>Chưa có log cho bước này.</p>
                  ) : (
                    <ul className="max-h-32 space-y-1 overflow-y-auto">
                      {st.logs.map((line, i) => (
                        <li key={i} className="break-words">
                          {line}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {error && (
        <p role="alert" className="text-small font-bold text-danger">
          {error}
        </p>
      )}
    </section>
  );
}
