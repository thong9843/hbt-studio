import { useRef, useState } from 'react';
import { UploadIcon } from '../components/icons';
import { cx } from '../components/ui/cx';

export interface DropzoneProps {
  title: string;
  hint?: string;
  busy?: boolean;
  busyTitle?: string;
  multiple?: boolean;
  accept?: string;
  onFiles: (files: File[]) => void;
  className?: string;
}

/** Khu vực kéo thả tệp dùng chung theo giao diện Dark Studio. */
export function Dropzone({
  title,
  hint,
  busy = false,
  busyTitle,
  multiple = true,
  accept,
  onFiles,
  className,
}: DropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const emitFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    onFiles(Array.from(list));
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        emitFiles(e.dataTransfer.files);
      }}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
      className={cx(
        'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed px-6 py-8 text-center transition duration-150',
        dragging
          ? 'border-indigo-400 bg-indigo-500/10'
          : 'border-line bg-card hover:border-indigo-500/60 hover:bg-soft-2',
        className,
      )}
    >
      <input
        ref={inputRef}
        type="file"
        multiple={multiple}
        accept={accept}
        className="hidden"
        onChange={(e) => {
          emitFiles(e.target.files);
          e.target.value = '';
        }}
      />
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-soft text-indigo-400">
        <UploadIcon size={22} />
      </span>
      <p className="text-body font-bold">{busy && busyTitle ? busyTitle : title}</p>
      {hint && <p className="text-tiny text-muted">{hint}</p>}
    </div>
  );
}
