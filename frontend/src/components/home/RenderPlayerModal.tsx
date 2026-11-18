import { Link } from 'react-router-dom';
import type { UnifiedRenderItem } from '../../api/types';
import { formatDuration } from '../../utils/format';
import { releaseVideoElementLocks } from '../../utils/media';
import { CopyIcon, DownloadIcon, TrashIcon } from '../icons';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';

const ENGINE_LABELS: Record<'core' | 'postv' | 'chatting' | 'stickv', string> = {
  core: 'HBT Core',
  postv: 'PostV',
  chatting: 'Chatting',
  stickv: 'StickV',
};

interface RenderPlayerModalProps {
  item: UnifiedRenderItem | null;
  onClose: () => void;
  onCopyPublish: (text: string) => void;
  onRequestDelete: (item: UnifiedRenderItem) => void;
}

export function RenderPlayerModal({
  item,
  onClose,
  onCopyPublish,
  onRequestDelete,
}: RenderPlayerModalProps) {
  return (
    <Dialog
      open={Boolean(item)}
      onClose={onClose}
      title={item ? item.title : 'Chi tiết video đã xuất'}
      className="!max-w-[780px]"
    >
      {item && (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-[240px_1fr]">
          <div className="mx-auto aspect-[9/16] w-full max-w-[240px] overflow-hidden rounded-inner border border-line bg-hero shadow-card">
            <video
              src={item.video_url}
              controls
              autoPlay
              playsInline
              className="h-full w-full object-contain"
            />
          </div>
          <div className="flex flex-col justify-between gap-4">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={item.engine}>{ENGINE_LABELS[item.engine]}</Badge>
                <span className="num text-small text-muted">
                  {item.size_mb} MB
                  {item.duration_sec > 0 ? ` · ${formatDuration(item.duration_sec)}` : ''}
                </span>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-small font-bold">Nội dung đăng bài (publish.txt)</span>
                  {item.publish_text && (
                    <Button
                      size="sm"
                      tone="accent"
                      icon={<CopyIcon size={14} />}
                      onClick={() => onCopyPublish(item.publish_text)}
                    >
                      Sao chép caption
                    </Button>
                  )}
                </div>
                <pre className="max-h-56 overflow-y-auto rounded-inner border border-line bg-soft p-3 font-sans text-small whitespace-pre-wrap text-text-2">
                  {item.publish_text || 'Chưa có nội dung publish.txt đính kèm.'}
                </pre>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4">
              <div className="flex flex-wrap items-center gap-2">
                <a
                  href={`${item.video_url}${item.video_url.includes('?') ? '&' : '?'}download=1`}
                  download={`${item.slug || 'video'}.mp4`}
                  className="ui-btn ui-btn-export ui-btn-sm"
                >
                  <DownloadIcon size={14} />
                  Tải .mp4
                </a>
                {item.slug && (
                  <Link
                    to={
                      item.engine === 'chatting'
                        ? `/chatting/${item.slug}`
                        : item.engine === 'postv'
                          ? `/postv/${item.slug}`
                          : `/p/${item.slug}`
                    }
                    className="ui-btn ui-btn-soft ui-btn-sm"
                    onClick={onClose}
                  >
                    Mở lại dự án
                  </Link>
                )}
              </div>
              <Button
                size="sm"
                tone="danger"
                icon={<TrashIcon size={14} />}
                onClick={() => {
                  releaseVideoElementLocks(item.video_url);
                  onRequestDelete(item);
                }}
              >
                Xóa video
              </Button>
            </div>
          </div>
        </div>
      )}
    </Dialog>
  );
}
