import { useQuery } from '@tanstack/react-query';
import { fetchHealth, type Health } from '../api/client';
import { vi } from '../i18n/vi';

const ITEMS = ['ffmpeg', 'whisper', 'gpu'] as const satisfies readonly (keyof Health)[];

export function HealthStatus() {
  const { data, isPending, isError, refetch, isFetching } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetchHealth(),
    retry: false,
  });

  return (
    <section className="rounded-3xl bg-surface p-8">
      <h2 className="text-sm font-bold uppercase tracking-widest text-muted">{vi.health.title}</h2>

      {isPending && <p className="mt-4">{vi.health.loading}</p>}
      {isError && <p className="mt-4 font-semibold text-hbt-red">{vi.health.unreachable}</p>}

      {data && (
        <>
          <p className={`mt-4 text-2xl font-extrabold ${data.ok ? '' : 'text-hbt-red'}`}>
            {data.ok ? vi.health.ready : vi.health.notReady}
          </p>
          {data.ffmpeg && data.missing.length > 0 && (
            <p className="mt-2 font-semibold text-hbt-red">
              {vi.health.missingList} {data.missing.join(', ')}
            </p>
          )}
          <ul className="mt-6 flex flex-wrap gap-3">
            {ITEMS.map((key) => (
              <li
                key={key}
                className={`rounded-full px-5 py-2 font-semibold ${
                  data[key] ? 'bg-fg text-bg' : 'bg-hbt-red text-white'
                }`}
              >
                <span aria-hidden="true">
                  {vi.health.items[key]} {data[key] ? '✓' : '✗'}
                </span>
                <span className="sr-only">
                  {`${vi.health.items[key]}: ${data[key] ? vi.health.available : vi.health.missing}`}
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
        className="mt-8 rounded-full border border-fg px-6 py-2 font-semibold transition hover:bg-fg hover:text-bg disabled:opacity-50"
      >
        {vi.health.recheck}
      </button>
    </section>
  );
}
