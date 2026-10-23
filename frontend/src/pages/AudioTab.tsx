import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useDropzone } from 'react-dropzone';
import { api, projectFileUrl } from '../api/endpoints';
import type { MusicEntry } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { useProjectEditor } from '../hooks/projectEditor';
import { vi } from '../i18n/vi';
import { voiceFile, voiceTrimEnd, withVoiceTrim } from '../utils/voice';

const A = vi.audio;
const AUDIO_ACCEPT = { 'audio/*': [] };
export const PREVIEW_SECONDS = 10;

function numberOrNull(raw: string): number | null {
  if (raw.trim() === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

function AudioDrop({
  label,
  rejected,
  busy,
  onFile,
}: {
  label: string;
  rejected: string;
  busy?: boolean;
  onFile: (file: File) => void;
}) {
  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop: (files) => files[0] && onFile(files[0]),
    accept: AUDIO_ACCEPT,
    maxFiles: 1,
    multiple: false,
  });
  return (
    <div>
      <div
        {...getRootProps()}
        className={`cursor-pointer rounded-card border-2 border-dashed p-5 text-small font-bold transition ${
          isDragActive ? 'border-text bg-surface-2' : 'border-border bg-surface'
        }`}
      >
        <input {...getInputProps({ 'aria-label': label })} />
        {busy ? vi.common.loading : label}
      </div>
      {fileRejections.length > 0 && (
        <p role="alert" className="mt-2 text-small font-bold text-danger">
          {rejected}
        </p>
      )}
    </div>
  );
}

function VoiceSection() {
  const editor = useProjectEditor();
  const { project } = editor;
  const file = voiceFile(project.voice);
  const trim = voiceTrimEnd(project.voice);
  const [version, setVersion] = useState(0);
  const upload = useMutation({
    mutationFn: async (f: File) => {
      await editor.flush();
      return api.uploadAsset(project.slug, 'voice', f);
    },
    onSuccess: (res) => {
      editor.applyServer((p) => ({ ...p, voice: res.project.voice }));
      setVersion((v) => v + 1);
    },
  });

  return (
    <section className="space-y-4">
      <h2>{A.voice.title}</h2>
      {file ? (
        <audio
          key={version}
          controls
          className="w-full"
          src={`${projectFileUrl(project.slug, file)}?v=${version}`}
        />
      ) : (
        <p className="text-text-muted">{A.voice.none}</p>
      )}
      <AudioDrop
        label={file ? A.voice.replace : A.voice.drop}
        rejected={A.voice.rejected}
        busy={upload.isPending}
        onFile={(f) => upload.mutate(f)}
      />
      <ErrorNote error={upload.error} />
      {file && (
        <div className="max-w-xs">
          <label className="label" htmlFor="voice-trim">
            {A.voice.trim}
          </label>
          <input
            id="voice-trim"
            type="number"
            min={0}
            step={0.1}
            className="input"
            value={trim ?? ''}
            onChange={(e) => {
              const v = numberOrNull(e.target.value);
              editor.update((p) => withVoiceTrim(p, v && v > 0 ? v : null));
            }}
          />
          <p className="mt-1 text-small text-text-muted">{A.voice.trimHelp}</p>
        </div>
      )}
    </section>
  );
}

/** Nút nghe thử 10 giây từ `start`; dừng khi đủ thời gian hoặc bấm lần nữa. */
function SnippetPlayer({ src, start }: { src: string; start: number }) {
  const ref = useRef<HTMLAudioElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [playing, setPlaying] = useState(false);

  const stop = () => {
    clearTimeout(timer.current);
    ref.current?.pause();
    setPlaying(false);
  };
  useEffect(() => () => clearTimeout(timer.current), []);

  const toggle = () => {
    const el = ref.current;
    if (!el) return;
    if (playing) {
      stop();
      return;
    }
    el.currentTime = start;
    void el.play();
    setPlaying(true);
    timer.current = setTimeout(stop, PREVIEW_SECONDS * 1000);
  };

  return (
    <>
      <audio ref={ref} src={src} preload="none" />
      <button type="button" className="btn btn-secondary btn-sm" onClick={toggle}>
        {playing ? A.music.stop : A.music.preview}
      </button>
    </>
  );
}

function NewTrackForm({ onAdded }: { onAdded: (entry: MusicEntry) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [fields, setFields] = useState({
    title: '',
    artist: '',
    source: '',
    license: '',
    url: '',
    moods: '',
    bpm: '',
  });
  const add = useMutation({
    mutationFn: () =>
      api.addMusic({
        file: file!,
        ...fields,
        bpm: fields.bpm ? Number(fields.bpm) : null,
      }),
    onSuccess: (entry) => {
      setFile(null);
      setFields({ title: '', artist: '', source: '', license: '', url: '', moods: '', bpm: '' });
      onAdded(entry);
    },
  });
  const required = ['title', 'artist', 'source', 'license'] as const;
  const ready = file && required.every((k) => fields[k].trim());

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (ready) add.mutate();
  };

  return (
    <form onSubmit={submit} className="card space-y-4 p-5">
      <h3>{A.music.upload}</h3>
      <AudioDrop label={A.music.uploadDrop} rejected={A.voice.rejected} onFile={setFile} />
      {file && (
        <p className="text-small">
          {A.music.fileChosen}: <b>{file.name}</b>
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {(Object.keys(A.music.fields) as (keyof typeof A.music.fields)[]).map((key) => (
          <div key={key}>
            <label className="label" htmlFor={`nt-${key}`}>
              {A.music.fields[key]}
            </label>
            <input
              id={`nt-${key}`}
              className="input"
              type={key === 'bpm' ? 'number' : 'text'}
              required={(required as readonly string[]).includes(key)}
              value={fields[key]}
              onChange={(e) => setFields((f) => ({ ...f, [key]: e.target.value }))}
            />
          </div>
        ))}
      </div>
      <ErrorNote error={add.error} />
      <button type="submit" className="btn btn-primary" disabled={!ready || add.isPending}>
        {add.isPending ? A.music.submitting : A.music.submit}
      </button>
    </form>
  );
}

function MusicSection() {
  const editor = useProjectEditor();
  const { project } = editor;
  const queryClient = useQueryClient();
  const library = useQuery({ queryKey: ['music'], queryFn: api.listMusic });
  const music = project.music;
  const renders = useQuery({
    queryKey: ['renders', project.slug],
    queryFn: () => api.listRenders(project.slug),
    enabled: Boolean(music?.file),
  });
  // Lần dựng gần nhất (mới nhất đứng đầu) cho biết giây app đã tự chọn.
  const latest = renders.data?.[0];
  const autoStart =
    latest?.music_start_source === 'auto' && latest.music_start !== null
      ? latest.music_start
      : null;
  const start = music?.start ?? autoStart ?? 0;

  const attach = useMutation({
    mutationFn: async (id: string) => {
      await editor.flush();
      return api.attachLibraryMusic(project.slug, id);
    },
    onSuccess: (res) => editor.applyServer((p) => ({ ...p, music: res.music })),
  });

  const patchMusic = (patch: Partial<NonNullable<typeof music>>) =>
    editor.update((p) => ({
      ...p,
      music: { file: null, start: null, credit: '', ...p.music, ...patch },
    }));

  return (
    <section className="space-y-5">
      <h2>{A.music.title}</h2>

      {music?.file ? (
        <div className="card space-y-4 p-5">
          <p className="text-small">
            <span className="text-text-muted">{A.music.current}: </span>
            <b>{music.credit || music.file}</b>
          </p>
          <audio controls className="w-full" src={projectFileUrl(project.slug, music.file)} />
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="music-start">
                {A.music.start}
              </label>
              <input
                id="music-start"
                type="number"
                min={0}
                step={0.5}
                className="input"
                value={music.start ?? ''}
                onChange={(e) => patchMusic({ start: numberOrNull(e.target.value) })}
              />
              <p className="mt-1 text-small text-text-muted">{A.music.startHelp}</p>
              {music.start === null &&
                (autoStart !== null ? (
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-small">
                    <span>{A.music.autoStart(autoStart)}</span>
                    <button
                      type="button"
                      className="btn btn-outline btn-sm"
                      onClick={() => patchMusic({ start: autoStart })}
                    >
                      {A.music.useAutoStart}
                    </button>
                  </p>
                ) : (
                  renders.isSuccess && (
                    <p className="mt-1 text-small text-text-muted">{A.music.noRenderYet}</p>
                  )
                ))}
            </div>
            <div>
              <label className="label" htmlFor="music-credit">
                {A.music.credit}
              </label>
              <input
                id="music-credit"
                className="input"
                value={music.credit}
                onChange={(e) => patchMusic({ credit: e.target.value })}
              />
              <p className="mt-1 text-small text-text-muted">{A.music.creditHelp}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <SnippetPlayer src={projectFileUrl(project.slug, music.file)} start={start} />
            <button
              type="button"
              className="btn btn-outline btn-sm"
              onClick={() => editor.update((p) => ({ ...p, music: null }))}
            >
              {A.music.remove}
            </button>
          </div>
        </div>
      ) : (
        <p className="text-text-muted">{A.music.none}</p>
      )}

      <div>
        <h3 className="mb-3">{A.music.library}</h3>
        {library.data && library.data.length === 0 && (
          <p className="text-text-muted">{A.music.libraryEmpty}</p>
        )}
        <ul className="space-y-2">
          {library.data?.map((entry) => (
            <li key={entry.id} className="card flex flex-wrap items-center gap-3 p-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-bold">{entry.title}</p>
                <p className="truncate text-small text-text-muted">
                  {entry.artist} · {entry.source} · {entry.license}
                  {entry.bpm ? ` · ${entry.bpm} BPM` : ''}
                </p>
              </div>
              <audio controls preload="none" src={api.libraryMusicUrl(entry.id)} className="h-9" />
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={attach.isPending}
                onClick={() => attach.mutate(entry.id)}
              >
                {A.music.use}
              </button>
            </li>
          ))}
        </ul>
        <ErrorNote error={library.error ?? attach.error} className="mt-3" />
      </div>

      <NewTrackForm
        onAdded={(entry) => {
          void queryClient.invalidateQueries({ queryKey: ['music'] });
          attach.mutate(entry.id);
        }}
      />
    </section>
  );
}

export function AudioTab() {
  return (
    <div className="max-w-3xl space-y-12">
      <VoiceSection />
      <MusicSection />
    </div>
  );
}
