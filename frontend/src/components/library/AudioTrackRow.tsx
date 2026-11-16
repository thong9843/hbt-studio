import { useEffect, useRef, useState } from 'react';
import type { AssetHubItem } from '../../api/types';
import { formatDuration } from '../../utils/format';
import { MusicIcon, PlayIcon, StopIcon, TrashIcon } from '../icons';
import { Badge } from '../ui/Badge';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface AudioTrackRowProps {
  item: AssetHubItem;
  isPlaying: boolean;
  onTogglePlay: (url: string) => void;
  onDelete: (item: AssetHubItem) => void;
  audioElement: HTMLAudioElement | null;
}

/**
 * Dòng nhạc nền thanh lịch với trình phát mini ngay trên từng dòng (Play/Pause, thanh tua, mood, dung lượng).
 */
export function AudioTrackRow({
  item,
  isPlaying,
  onTogglePlay,
  onDelete,
  audioElement,
}: AudioTrackRowProps) {
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isPlaying || !audioElement) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    const tick = () => {
      if (audioElement.duration && !Number.isNaN(audioElement.duration)) {
        setDuration(audioElement.duration);
        setProgress(audioElement.currentTime / audioElement.duration);
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, audioElement]);

  const handleSeek = (ratio: number) => {
    if (!audioElement || !isPlaying || !audioElement.duration) return;
    audioElement.currentTime = ratio * audioElement.duration;
    setProgress(ratio);
  };

  return (
    <li className="flex flex-wrap items-center gap-3 rounded-card border border-line bg-card px-4 py-3 shadow-card transition-all duration-180 hover:border-engine-postv/40">
      <button
        type="button"
        onClick={() => onTogglePlay(item.url)}
        aria-label={isPlaying ? `Tạm dừng ${item.name}` : `Nghe thử ${item.name}`}
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-transform active:scale-95 ${
          isPlaying ? 'bg-engine-postv text-white shadow-sm' : 'bg-soft text-text hover:bg-soft-2'
        }`}
      >
        {isPlaying ? <StopIcon size={16} /> : <PlayIcon size={16} />}
      </button>

      <div className="min-w-[180px] flex-1">
        <div className="flex items-center gap-2">
          <MusicIcon size={14} className="shrink-0 text-muted" />
          <p className="truncate text-small font-bold text-text">{item.name}</p>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-tiny text-muted">
          <Badge>{item.source === 'library' ? 'Thư viện' : 'Assets'}</Badge>
          {item.moods && item.moods.length > 0 && (
            <Badge tone="postv">{item.moods.slice(0, 2).join(', ')}</Badge>
          )}
          <span className="num">{formatBytes(item.size)}</span>
          {duration > 0 && isPlaying && (
            <span className="num font-semibold text-engine-postv">
              {formatDuration(progress * duration)} / {formatDuration(duration)}
            </span>
          )}
        </div>
      </div>

      {/* Thanh tua mini */}
      <div className="flex w-full items-center gap-2 sm:w-44">
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={isPlaying ? progress : 0}
          disabled={!isPlaying}
          onChange={(e) => handleSeek(Number(e.target.value))}
          aria-label={`Tua ${item.name}`}
          className="h-1.5 w-full cursor-pointer accent-engine-postv disabled:cursor-default disabled:opacity-40"
        />
      </div>

      <button
        type="button"
        onClick={() => onDelete(item)}
        aria-label={`Xóa ${item.name}`}
        className="ui-icon-btn ui-icon-btn-sm text-danger hover:bg-danger-soft"
      >
        <TrashIcon size={15} />
      </button>
    </li>
  );
}
