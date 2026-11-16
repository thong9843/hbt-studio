import { useRef, useState } from 'react';
import type { AssetHubItem } from '../../api/types';
import { PlayIcon, TrashIcon } from '../icons';
import { Badge } from '../ui/Badge';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface GameplayCardProps {
  item: AssetHubItem;
  onPreview: (item: AssetHubItem) => void;
  onDelete: (item: AssetHubItem) => void;
}

/**
 * Thẻ Video nền Gameplay 9:16 tự phát xem trước khi rê chuột (hover-to-play).
 */
export function GameplayCard({ item, onPreview, onDelete }: GameplayCardProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [hovering, setHovering] = useState(false);

  const handleEnter = () => {
    setHovering(true);
    const v = videoRef.current;
    if (v) {
      v.currentTime = 0;
      void v.play().catch(() => {});
    }
  };

  const handleLeave = () => {
    setHovering(false);
    const v = videoRef.current;
    if (v) {
      v.pause();
    }
  };

  return (
    <li
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      className="group flex flex-col overflow-hidden rounded-card border border-line bg-card shadow-card transition-all duration-180 hover:-translate-y-0.5 hover:shadow-card-hover"
    >
      <button
        type="button"
        onClick={() => onPreview(item)}
        className="relative aspect-[9/16] w-full overflow-hidden bg-hero text-left"
        aria-label={`Xem trước ${item.name}`}
      >
        <video
          ref={videoRef}
          src={item.url}
          muted
          loop
          playsInline
          preload="metadata"
          className="h-full w-full object-cover"
        />
        <span className="absolute left-2.5 top-2.5">
          <Badge tone="postv">{item.source === 'library' ? 'Thư viện' : 'Assets'}</Badge>
        </span>
        {!hovering && (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/20">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/85 text-slate-900 shadow">
              <PlayIcon size={16} />
            </span>
          </span>
        )}
      </button>

      <div className="flex items-center justify-between gap-2 p-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-small font-bold text-text">{item.name}</p>
          <p className="num text-tiny text-muted">{formatBytes(item.size)}</p>
        </div>
        <button
          type="button"
          onClick={() => onDelete(item)}
          aria-label={`Xóa ${item.name}`}
          className="ui-icon-btn ui-icon-btn-sm text-danger hover:bg-danger-soft"
        >
          <TrashIcon size={14} />
        </button>
      </div>
    </li>
  );
}
