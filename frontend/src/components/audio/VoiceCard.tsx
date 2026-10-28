import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { api, projectFileUrl } from '../../api/endpoints';
import type { RenderRecord } from '../../api/types';
import { useProjectEditor } from '../../hooks/projectEditor';
import { vi } from '../../i18n/vi';
import { voiceFile, voiceTrimEnd, withVoiceTrim } from '../../utils/voice';
import { ErrorNote } from '../ErrorNote';
import { Badge } from '../ui/Badge';
import { Card } from '../ui/Card';
import { Input } from '../ui/Field';
import { AudioDrop } from './AudioDrop';
import { ClipButton } from './clip';

const T = vi.audio.voice;

function trimValue(raw: string): number | null {
  const n = Number(raw);
  return raw.trim() !== '' && Number.isFinite(n) && n > 0 ? n : null;
}

/** Thẻ Giọng đọc: trình phát, phần đã cắt đuôi (nghe lại được), cắt tay, thả giọng mới. */
export function VoiceCard({ latest }: { latest: RenderRecord | undefined }) {
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
  const tail = latest?.trimmed_tail ?? null;

  return (
    <Card as="section" aria-label={T.title} className="space-y-4">
      <h2 className="text-h2 font-bold">{T.title}</h2>
      {file ? (
        <audio
          key={version}
          controls
          className="w-full"
          src={`${projectFileUrl(project.slug, file)}?v=${version}`}
        />
      ) : (
        <p className="text-small text-muted">{T.none}</p>
      )}

      {tail && (
        <div className="ui-inner flex items-center justify-between gap-3 p-3">
          <Badge tone="yel">
            {latest?.trimmed_tail_seconds
              ? T.trimmedSeconds(latest.trimmed_tail_seconds.toFixed(1).replace('.', ','))
              : T.trimmed}
          </Badge>
          <ClipButton src={tail} label={T.listenTrimmed}>
            {vi.audio.play}
          </ClipButton>
        </div>
      )}

      <AudioDrop
        label={file ? T.replace : T.drop}
        busy={upload.isPending}
        onFile={(f) => upload.mutate(f)}
      />
      <ErrorNote error={upload.error} />

      {file && (
        <Input
          label={T.trim}
          type="number"
          min={0}
          step={0.1}
          inputMode="decimal"
          hint={<p className="mt-1 text-small text-muted">{T.trimHelp}</p>}
          value={trim ?? ''}
          onChange={(e) => editor.update((p) => withVoiceTrim(p, trimValue(e.target.value)))}
        />
      )}
    </Card>
  );
}
