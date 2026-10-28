import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { api } from '../../api/endpoints';
import type { MusicEntry } from '../../api/types';
import { vi } from '../../i18n/vi';
import { ErrorNote } from '../ErrorNote';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { Input } from '../ui/Field';
import { AudioDrop } from './AudioDrop';

const T = vi.audio.music;
type Key = keyof typeof T.fields;
const KEYS = Object.keys(T.fields) as Key[];
const REQUIRED: readonly Key[] = ['title', 'artist', 'source', 'license'];
const EMPTY: Record<Key, string> = {
  title: '',
  artist: '',
  source: '',
  license: '',
  url: '',
  moods: '',
  bpm: '',
};

interface Props {
  open: boolean;
  onClose: () => void;
  /** Bài đã thêm vào thư viện (app dùng luôn cho dự án). */
  onAdded: (entry: MusicEntry) => void;
}

/** Hộp "Tải nhạc": file từ máy lên + tên, tác giả, nguồn, giấy phép, tâm trạng (IMPLEMENT 6.2). */
export function UploadTrackDialog({ open, onClose, onAdded }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [fields, setFields] = useState(EMPTY);
  const add = useMutation({
    mutationFn: () =>
      api.addMusic({ file: file!, ...fields, bpm: fields.bpm ? Number(fields.bpm) : null }),
    onSuccess: (entry) => {
      setFile(null);
      setFields(EMPTY);
      onAdded(entry);
      onClose();
    },
  });
  const ready = file !== null && REQUIRED.every((k) => fields[k].trim());

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (ready) add.mutate();
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={T.uploadTitle}
      footer={
        <>
          <Button tone="soft" onClick={onClose}>
            {T.cancel}
          </Button>
          <Button
            type="submit"
            form="upload-track"
            tone="ink"
            disabled={!ready}
            busy={add.isPending}
          >
            {add.isPending ? T.submitting : T.submit}
          </Button>
        </>
      }
    >
      <form id="upload-track" onSubmit={submit} className="space-y-4">
        <AudioDrop label={T.uploadDrop} onFile={setFile} />
        {file && (
          <p className="text-small">
            {T.fileChosen}: <b>{file.name}</b>
          </p>
        )}
        <div className="grid gap-3 min-[560px]:grid-cols-2">
          {KEYS.map((key) => (
            <Input
              key={key}
              label={T.fields[key]}
              type={key === 'bpm' ? 'number' : 'text'}
              required={REQUIRED.includes(key)}
              value={fields[key]}
              onChange={(e) => setFields((f) => ({ ...f, [key]: e.target.value }))}
            />
          ))}
        </div>
        <ErrorNote error={add.error} />
      </form>
    </Dialog>
  );
}
