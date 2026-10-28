import type { RenderRecord } from '../../api/types';
import { vi } from '../../i18n/vi';
import { historyLabel } from '../../utils/exportView';
import { formatDateTime, formatDuration } from '../../utils/format';
import { MoreIcon } from '../icons';
import { CardImage } from '../ProjectCard';
import { Badge } from '../ui/Badge';
import { Card } from '../ui/Card';
import { Menu } from '../ui/Menu';

const H = vi.export.history;

interface Props {
  renders: RenderRecord[];
  /** Ảnh cảnh 1 của dự án, dùng khi lần dựng không có bìa. */
  fallbackImage: string | null;
  /** `job_id` đang xem (viền vàng). */
  current: string | null;
  onSelect: (r: RenderRecord) => void;
  /** `job_id` đang chạy hoặc đang chờ: tắt "Xoá" ở thẻ đó. */
  lockedId?: string | null;
  /** Bấm "Xoá" (nơi gọi hiện hộp xác nhận rồi gọi API). */
  onDelete: (r: RenderRecord) => void;
}

/** Tải file bằng một thẻ <a download> tạm (mục menu không phải liên kết). */
function download(href: string, file: string) {
  const a = document.createElement('a');
  a.href = href;
  a.download = file;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** Lịch sử dạng lưới: bìa (hoặc ảnh cảnh 1), nhãn Bản đẹp / Xem nhanh / 10 s đầu, ngày giờ. */
export function HistoryGrid({
  renders,
  fallbackImage,
  current,
  onSelect,
  lockedId = null,
  onDelete,
}: Props) {
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
              className={`ui-card-link ${on ? 'ui-history-on' : ''}`}
            >
              <button
                type="button"
                aria-pressed={on}
                aria-label={H.select(label, when)}
                className="block w-full text-left"
                onClick={() => onSelect(r)}
              >
                <div className="aspect-[9/16] w-full overflow-hidden rounded-t-card bg-soft">
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
              <div className="absolute bottom-2 right-2">
                <Menu
                  label={H.menu(label, when)}
                  icon={<MoreIcon />}
                  items={[
                    ...(r.video
                      ? [
                          {
                            key: 'download',
                            label: H.download,
                            onSelect: () => download(r.video as string, 'video.mp4'),
                          },
                        ]
                      : []),
                    {
                      key: 'delete',
                      label: H.remove,
                      danger: true,
                      disabled: r.job_id === lockedId,
                      reason: r.job_id === lockedId ? H.runningReason : undefined,
                      onSelect: () => onDelete(r),
                    },
                  ]}
                />
              </div>
            </Card>
          );
        })}
      </ul>
    </section>
  );
}
