import { Link } from 'react-router-dom';
import type { LintIssue, LintResult } from '../../api/types';
import { vi } from '../../i18n/vi';
import { checkStatus } from '../../utils/exportView';
import { sceneNumber } from '../../utils/scene';
import { ErrorNote } from '../ErrorNote';
import { AlertIcon } from '../icons';
import { Badge, type BadgeTone } from '../ui/Badge';
import { Card } from '../ui/Card';
import { Skeleton } from '../ui/Skeleton';

const X = vi.export;
const LEVEL_TONE: Record<LintIssue['level'], BadgeTone> = {
  block: 'danger',
  warn: 'yel',
  info: 'neutral',
};

interface Props {
  slug: string;
  lint: { data?: LintResult; isPending: boolean; error: unknown };
  /** Thiếu nguyên liệu tính ở giao diện (thiếu ảnh cảnh n, thiếu giọng đọc). */
  missing: string[];
}

/** Thẻ Kiểm tra: Sẵn sàng / có cảnh báo / bị chặn, ba số, mỗi lỗi có "Đến cảnh N". */
export function ChecksCard({ slug, lint, missing }: Props) {
  const data = lint.data;
  const status = checkStatus(data, missing);
  const issues = data?.issues ?? [];
  const problems = [...missing, ...(data?.problems ?? [])];
  return (
    <Card as="section" aria-label={X.checks.title} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-h2 font-bold">{X.checks.title}</h2>
        {status && (
          <Badge tone={status === 'ready' ? 'ok' : status === 'warn' ? 'yel' : 'danger'}>
            {status === 'blocked' && <AlertIcon size={14} />}
            {X.status[status]}
          </Badge>
        )}
      </div>
      {lint.isPending && <Skeleton height={20} width="50%" />}
      <ErrorNote error={lint.error} />
      {data && (
        <dl className="grid grid-cols-3 gap-3">
          {(['block', 'warn', 'info'] as const).map((level) => (
            <div key={level} className="ui-inner p-3">
              <dt className="text-tiny font-semibold text-muted">{X.counts[level]}</dt>
              <dd className="text-h2 font-extrabold tabular-nums">{data.counts[level]}</dd>
            </div>
          ))}
        </dl>
      )}
      {problems.length > 0 && (
        <ul className="space-y-2">
          {problems.map((p) => (
            <li key={p} className="flex flex-wrap items-center gap-2 text-small">
              <Badge tone="danger">
                <AlertIcon size={14} />
                {X.checks.missing}
              </Badge>
              {p}
            </li>
          ))}
        </ul>
      )}
      {issues.length > 0 && (
        <ul className="space-y-2">
          {issues.map((issue, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2 text-small">
              <Badge tone={LEVEL_TONE[issue.level]}>
                {issue.level === 'block' && <AlertIcon size={14} />}
                {X.checks[issue.level]}
              </Badge>
              <b>
                {issue.scene_index === null
                  ? X.checks.wholeVideo
                  : X.checks.scene(sceneNumber(issue.scene_index))}
              </b>
              <span>{issue.message}</span>
              {issue.hint && <span className="text-muted">{issue.hint}</span>}
              {issue.scene_index !== null && (
                <Link
                  to={`/p/${slug}`}
                  state={{ scene: sceneNumber(issue.scene_index) }}
                  className="ml-auto font-bold underline"
                >
                  {X.gotoScene(sceneNumber(issue.scene_index))}
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
