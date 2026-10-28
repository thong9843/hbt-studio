import { useState } from 'react';
import { projectFileUrl } from '../../api/endpoints';
import type { Music, RenderRecord } from '../../api/types';
import { lastAutoStart, PREVIEW_SECONDS } from '../../utils/audio';
import { useProjectEditor } from '../../hooks/projectEditor';
import { vi } from '../../i18n/vi';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Chip } from '../ui/Chip';
import { Input } from '../ui/Field';
import { ClipButton } from './clip';

const T = vi.audio.start;
/** Thẻ Điểm bắt đầu nhạc: Tự chọn / Đặt tay, "Lần trước: giây X" + Nghe + Dùng. */
export function MusicStartCard({
  music,
  latest,
}: {
  music: Music | null;
  latest: RenderRecord | undefined;
}) {
  const editor = useProjectEditor();
  const { slug } = editor.project;
  const file = music?.file ?? null;
  const manual = music?.start !== null && music?.start !== undefined;
  const last = lastAutoStart(latest);
  const [draft, setDraft] = useState<string | null>(null);

  const setStart = (start: number | null) =>
    editor.update((p) => (p.music ? { ...p, music: { ...p.music, start } } : p));

  return (
    <Card as="section" aria-label={T.title} className="space-y-4">
      <h2 className="text-h2 font-bold">{T.title}</h2>
      {!file ? (
        <p className="text-small text-muted">{T.needMusic}</p>
      ) : (
        <>
          <div role="group" aria-label={T.group} className="flex flex-wrap gap-2">
            <Chip selected={!manual} onClick={() => setStart(null)}>
              {T.auto}
            </Chip>
            <Chip
              selected={manual}
              onClick={() => {
                setDraft(null);
                if (!manual) setStart(last ?? 0);
              }}
            >
              {T.manual}
            </Chip>
          </div>

          {manual && (
            <Input
              label={T.seconds}
              type="number"
              min={0}
              step={0.5}
              inputMode="decimal"
              value={draft ?? music?.start ?? 0}
              onChange={(e) => {
                setDraft(e.target.value);
                const n = Number(e.target.value);
                if (e.target.value.trim() !== '' && Number.isFinite(n) && n >= 0) setStart(n);
              }}
              onBlur={() => setDraft(null)}
            />
          )}

          {last !== null && (
            <div className="ui-inner flex flex-wrap items-center gap-2 p-3">
              <span className="mr-auto text-small font-bold tabular-nums">{T.last(last)}</span>
              <ClipButton
                src={projectFileUrl(slug, file)}
                start={last}
                seconds={PREVIEW_SECONDS}
                label={T.listenLast}
              >
                {vi.audio.play}
              </ClipButton>
              {!(manual && music?.start === last) && (
                <Button
                  tone="ink"
                  size="sm"
                  onClick={() => {
                    setDraft(null);
                    setStart(last);
                  }}
                >
                  {T.use}
                </Button>
              )}
            </div>
          )}

          <ClipButton
            src={projectFileUrl(slug, file)}
            start={music?.start ?? last ?? 0}
            seconds={PREVIEW_SECONDS}
            label={T.preview}
          >
            {T.preview}
          </ClipButton>
        </>
      )}
    </Card>
  );
}
