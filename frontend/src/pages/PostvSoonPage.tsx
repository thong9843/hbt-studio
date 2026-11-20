import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { vi } from '../i18n/vi';

/** Bước chưa làm (3–5): chỉ báo "Sắp có". Nguồn và đoạn đã chọn vẫn được lưu. */
export function PostvSoonPage({ step }: { step: number }) {
  const t = vi.postv;
  return (
    <Card as="section" aria-label={t.steps[step]} className="flex items-center gap-4">
      <Badge tone="yel">{t.soon}</Badge>
      <p className="text-body font-semibold">
        {t.stepOf(step + 1)} · {t.steps[step]}
      </p>
      <p className="text-small text-muted">{t.soonNote}</p>
    </Card>
  );
}
