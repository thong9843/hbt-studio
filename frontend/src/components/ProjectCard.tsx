import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { ProjectSummary } from '../api/types';
import { vi } from '../i18n/vi';
import { formatDate } from '../utils/format';
import { projectImage, projectStatus, type ProjectStatusKind } from '../utils/projectStatus';
import { MoreIcon } from './icons';
import { Badge, type BadgeTone } from './ui/Badge';
import { Card } from './ui/Card';
import { Menu } from './ui/Menu';
import { Skeleton } from './ui/Skeleton';

const TONE: Record<ProjectStatusKind, BadgeTone> = {
  final: 'red',
  preview: 'yel',
  none: 'neutral',
  broken: 'danger',
};

/** Ảnh thẻ; ảnh không tải được thì rơi về ô HBT đúng một lần (không thử lại). */
export function CardImage({ src }: { src: string | null }) {
  const [failed, setFailed] = useState<string | null>(null);
  if (src && failed !== src) {
    return (
      <img
        src={src}
        alt=""
        className="h-full w-full object-cover"
        loading="lazy"
        decoding="async"
        onError={() => setFailed(src)}
      />
    );
  }
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3">
      <img src="/brand/hbt-logo-mark.png" alt="" className="h-14 w-auto opacity-80" />
      <span className="text-small font-semibold text-muted">{vi.projects.noImage}</span>
    </div>
  );
}

interface Props {
  project: ProjectSummary;
  onDuplicate: () => void;
  onDelete: () => void;
  busy?: boolean;
  /** Dự án đang được dựng: khoá Nhân bản và Xoá (backend cũng trả 409). */
  rendering?: boolean;
}

/** Thẻ dự án: ảnh 9:16 tràn mép, tên 2 dòng, nhãn trạng thái + ngày, menu ⋯. */
export function ProjectCard({ project, onDuplicate, onDelete, busy, rendering }: Props) {
  const status = projectStatus(project);
  const image = projectImage(project);
  const href = `/p/${project.slug}`;
  const t = vi.projects;
  return (
    <Card as="li" padded={false} className="ui-card-link overflow-hidden">
      <Link to={href} aria-label={`${t.open}: ${project.title}`} className="block">
        <div className="aspect-[9/16] w-full overflow-hidden bg-soft">
          <CardImage src={image} />
        </div>
      </Link>
      <div className="flex items-start gap-2 p-4">
        <div className="min-w-0 flex-1 space-y-2">
          <h3 className="line-clamp-2 text-h2 font-bold">
            <Link to={href} className="hover:underline">
              {project.title}
            </Link>
          </h3>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <Badge tone={TONE[status.kind]}>{status.label}</Badge>
            <span className="num text-tiny text-muted">{formatDate(project.updated_at)}</span>
          </div>
        </div>
        <Menu
          label={t.menu(project.title)}
          icon={<MoreIcon />}
          items={[
            {
              key: 'duplicate',
              label: t.duplicate,
              disabled: busy || rendering,
              reason: rendering ? t.renderingReason : undefined,
              onSelect: onDuplicate,
            },
            {
              key: 'delete',
              label: t.delete,
              danger: true,
              disabled: busy || rendering,
              reason: rendering ? t.renderingReason : undefined,
              onSelect: onDelete,
            },
          ]}
        />
      </div>
    </Card>
  );
}

/** Khung xương một thẻ khi đang tải danh sách. */
export function ProjectCardSkeleton() {
  return (
    <li className="ui-card overflow-hidden">
      <Skeleton height="auto" className="aspect-[9/16] !rounded-none" />
      <div className="space-y-3 p-4">
        <Skeleton height={20} />
        <Skeleton width="60%" height={16} />
      </div>
    </li>
  );
}
