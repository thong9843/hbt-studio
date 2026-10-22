import { useQuery } from '@tanstack/react-query';
import { fetchHealth, type Health } from '../api/client';
import { vi } from '../i18n/vi';
import { AlertIcon, CheckIcon } from './icons';

const ITEMS = ['ffmpeg', 'whisper', 'gpu'] as const satisfies readonly (keyof Health)[];

export function HealthStatus() {
  const { data, isPending, isError, refetch, isFetching } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetchHealth(),
    retry: false,
  });

  return (
    <section className="rounded-card border border-border bg-surface p-6">
      <h2 className="text-tiny font-semibold uppercase text-text-muted">{vi.health.title}</h2>

      {isPending && (
        <p className="mt-4 flex items-center gap-3">
          <span className="spinner" aria-hidden="true" />
          {vi.health.loading}
        </p>
      )}
      {isError && (
        <p role="alert" className="mt-4 flex items-center gap-2 font-bold text-danger">
          <AlertIcon />
          {vi.health.unreachable}
        </p>
      )}

      {data && (
        <>
          <p className="mt-4 text-h2 font-bold">{data.ok ? vi.health.ready : vi.health.notReady}</p>
          {data.ffmpeg && data.missing.length > 0 && (
            <p className="mt-2 flex items-center gap-2 font-bold text-danger">
              <AlertIcon />
              {vi.health.missingList} {data.missing.join(', ')}
            </p>
          )}
          <ul className="mt-4 flex flex-wrap gap-2">
            {ITEMS.map((key) => (
              <li
                key={key}
                className={`chip h-10 gap-2 px-4 text-small normal-case ${
                  data[key]
                    ? 'chip-warn'
                    : 'border-[1.5px] border-danger bg-transparent text-danger'
                }`}
              >
                {data[key] ? <CheckIcon size={16} /> : <AlertIcon size={16} />}
                {vi.health.items[key]}
                <span className="sr-only">
                  {`: ${data[key] ? vi.health.available : vi.health.missing}`}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      <button
        type="button"
        onClick={() => refetch()}
        disabled={isFetching}
        className="btn btn-outline btn-sm mt-6"
      >
        {vi.health.recheck}
      </button>
    </section>
  );
}
