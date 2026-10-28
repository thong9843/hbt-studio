import { useEffect, useRef, useState, type ReactNode } from 'react';
import { vi } from '../../i18n/vi';
import { PlayIcon, StopIcon } from '../icons';
import { Button } from '../ui/Button';
import { IconButton } from '../ui/IconButton';

/** Chỉ một đoạn nghe thử phát tại một thời điểm: bắt đầu đoạn mới thì dừng đoạn đang phát. */
let stopActive: (() => void) | null = null;

interface Props {
  src: string;
  /** Giây bắt đầu phát trong file. */
  start?: number;
  /** Tự dừng sau chừng này giây; bỏ trống = phát tới hết hoặc tới khi bấm dừng. */
  seconds?: number;
  /** Tên đọc cho trình đọc màn hình (nút chỉ có biểu tượng). */
  label: string;
  stopLabel?: string;
  /** Có `children` thì là nút chữ, không thì là nút tròn chỉ có biểu tượng. */
  children?: ReactNode;
}

/** Nút nghe một đoạn âm thanh; bấm lần nữa để dừng. Không tải file cho tới khi bấm. */
export function ClipButton({ src, start = 0, seconds, label, stopLabel, children }: Props) {
  const ref = useRef<HTMLAudioElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [playing, setPlaying] = useState(false);

  const stop = () => {
    clearTimeout(timer.current);
    ref.current?.pause();
    setPlaying(false);
    if (stopActive === stop) stopActive = null;
  };
  // Đổi bài / rời màn thì dừng hẳn.
  useEffect(
    () => () => {
      clearTimeout(timer.current);
      ref.current?.pause();
    },
    [],
  );

  const toggle = () => {
    const el = ref.current;
    if (!el) return;
    if (playing) {
      stop();
      return;
    }
    stopActive?.();
    stopActive = stop;
    el.currentTime = start;
    void el.play();
    setPlaying(true);
    if (seconds) timer.current = setTimeout(stop, seconds * 1000);
  };

  const name = playing ? (stopLabel ?? vi.audio.stop) : label;
  const icon = playing ? <StopIcon size={18} /> : <PlayIcon size={18} />;
  return (
    <>
      <audio ref={ref} src={src} preload="none" onEnded={stop} />
      {children === undefined ? (
        <IconButton label={name} small onClick={toggle}>
          {icon}
        </IconButton>
      ) : (
        <Button tone="soft" size="sm" icon={icon} onClick={toggle} aria-label={name}>
          {playing ? vi.audio.stop : children}
        </Button>
      )}
    </>
  );
}
