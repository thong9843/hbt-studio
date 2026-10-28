import { useDropzone } from 'react-dropzone';
import { vi } from '../i18n/vi';
import { UploadIcon } from './icons';
import './ui/ui.css';

const IMAGE_ACCEPT = { 'image/png': [], 'image/jpeg': [], 'image/webp': [] };

/** Vùng thả một ảnh bìa (PNG, JPG, WEBP). */
export function CoverDrop({
  label,
  busy,
  onFile,
}: {
  label: string;
  busy?: boolean;
  onFile: (file: File) => void;
}) {
  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop: (files) => files[0] && onFile(files[0]),
    accept: IMAGE_ACCEPT,
    maxFiles: 1,
    multiple: false,
    disabled: busy,
  });
  return (
    <div>
      <div {...getRootProps({ className: 'ui-drop' })} data-active={isDragActive}>
        <input {...getInputProps({ 'aria-label': label })} />
        {busy ? <span className="ui-spinner" aria-hidden="true" /> : <UploadIcon size={18} />}
        {busy ? vi.ui.loading : label}
      </div>
      {fileRejections.length > 0 && (
        <p role="alert" className="ui-field-error mt-2">
          {vi.export.thumb.rejected}
        </p>
      )}
    </div>
  );
}
