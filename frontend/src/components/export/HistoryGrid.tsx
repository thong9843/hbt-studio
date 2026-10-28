import type { RenderRecord } from '../../api/types';
import { vi } from '../../i18n/vi';
import { historyLabel } from '../../utils/exportView';
import { formatDateTime, formatDuration } from '../../utils/format';
import { CardImage } from '../ProjectCard';
import { Badge } from '../ui/Badge';
import { Card } from '../ui/Card';

const H = vi.export.history;

interface Props {
  renders: RenderRecord[];
  /** Ảnh cảnh 1 của dự án, dùng khi lần dựng không có bìa. */
  fallbackImage: string | null;
  /** `job_id` đang xem (viền vàng). */
  current: string | null;
  onSelect: (r: RenderRecord) => void;
}

/** Lịch sử dạng lưới: bìa (hoặc ảnh cảnh 1), nhãn Bản đẹp / Xem nhanh / 10 s đầu, ngày giờ. */
export function HistoryGrid({ renders, fallbackImage, current, onSelect }: Props) {
  return (
    <section aria-label={H.title} className="space-y-3">
      <h2 className="text-h2 font-bold">{H.title}</h2>
      <p className="text-small text-muted">{H.note}</p>
      {renders.length === 0 && <p className="text-muted">{H.empty}</p>}
      <ul className="grid grid-cols-2 gap-4 min-[1100px]:grid-cols-3">
        {renders.map((r) => {
          const label = historyLabel(r);
          const when = formatDateTime(r.created_at);
          const on = r.job_id === current;
          return (
            <Card
              as="li"
              key={r.job_id}
              padded={false}
              className={`ui-card-link overflow-hidden ${on ? 'ui-history-on' : ''}`}
            >
              <button
                type="button"
                aria-pressed={on}
                aria-label={H.select(label, when)}
                className="block w-full text-left"
                onClick={() => onSelect(r)}
              >
                <div className="aspect-[9/16] w-full overflow-hidden bg-soft">
                  <CardImage src={r.cover ?? fallbackImage} />
                </div>
                <div className="space-y-2 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={r.preview ? 'yel' : 'red'}>{label}</Badge>
                    {on && <Badge tone="neutral">{H.current}</Badge>}
                  </div>
                  <p className="num text-tiny text-muted">{when}</p>
                  <p className="num text-tiny text-muted">
                    {r.duration ? formatDuration(r.duration) : '—'}
                    {r.fps ? ` · ${r.fps} fps` : ''}
                  </p>
                </div>
              </button>
            </Card>
          );
        })}
      </ul>
    </section>
  );
}
