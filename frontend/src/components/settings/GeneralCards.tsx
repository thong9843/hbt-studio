import type { AppSettings, Fps } from '../../api/types';
import { vi } from '../../i18n/vi';
import { Card } from '../ui/Card';
import { Chip } from '../ui/Chip';
import { Input } from '../ui/Field';

const S = vi.settings;
export const HEX = /^#[0-9a-fA-F]{6}$/;
const FPS: Fps[] = [30, 50, 60];
const MODELS: AppSettings['whisper_model'][] = ['auto', 'small', 'medium', 'large-v3'];

/** Dòng giải thích Whisper sẽ chạy thế nào trên máy này (health.gpu / health.whisper). */
function whisperNote(health: { gpu: boolean; whisper: boolean } | undefined): string {
  const G = S.general;
  if (!health) return G.whisperNoteUnknown;
  if (!health.whisper) return G.whisperNoteMissing;
  return health.gpu ? G.whisperNoteGpu : G.whisperNoteCpu;
}

interface Props {
  value: AppSettings;
  onChange: (patch: Partial<AppSettings>) => void;
}

/** Thẻ FPS mặc định: ba chip 30 / 50 / 60. */
export function FpsCard({ value, onChange }: Props) {
  return (
    <Card as="section" aria-label={S.fpsCard.title} className="space-y-3">
      <h2 className="text-h2 font-bold">{S.fpsCard.title}</h2>
      <p className="text-small text-muted">{S.fpsCard.help}</p>
      <div role="group" aria-label={S.general.fps} className="flex flex-wrap gap-2">
        {FPS.map((f) => (
          <Chip
            key={f}
            selected={value.default_fps === f}
            onClick={() => onChange({ default_fps: f })}
          >
            {f} fps
          </Chip>
        ))}
      </div>
    </Card>
  );
}

/** Thẻ Căn chữ: chip Tự động / small / medium / large-v3, ghi chú theo máy, giới hạn giây. */
export function WhisperCard({
  value,
  onChange,
  health,
}: Props & { health: { gpu: boolean; whisper: boolean } | undefined }) {
  const G = S.general;
  const slow = value.whisper_model === 'medium' || value.whisper_model === 'large-v3';
  return (
    <Card as="section" aria-label={S.whisperCard.title} className="space-y-4">
      <h2 className="text-h2 font-bold">{S.whisperCard.title}</h2>
      <div role="group" aria-label={G.whisperModel} className="flex flex-wrap gap-2">
        {MODELS.map((m) => (
          <Chip
            key={m}
            selected={value.whisper_model === m}
            onClick={() => onChange({ whisper_model: m })}
          >
            {m === 'auto' ? G.whisperAuto : m}
          </Chip>
        ))}
      </div>
      {slow && (
        <p role="note" className="ui-note-yel px-4 py-2 text-small font-bold">
          {G.whisperSlowWarning}
        </p>
      )}
      <p className="text-small text-muted">{whisperNote(health)}</p>
      <Input
        label={G.whisperTimeout}
        type="number"
        min={30}
        max={7200}
        value={value.whisper_timeout_seconds}
        onChange={(e) =>
          onChange({
            whisper_timeout_seconds: Math.min(7200, Math.max(30, Number(e.target.value) || 900)),
          })
        }
      />
    </Card>
  );
}

/** Thẻ Màu chủ đề: hai ô màu (chọn màu + mã #RRGGBB). */
export function ThemeCard({ value, onChange }: Props) {
  const G = S.general;
  return (
    <Card as="section" aria-label={S.themeCard.title} className="space-y-4">
      <h2 className="text-h2 font-bold">{S.themeCard.title}</h2>
      <p className="text-small text-muted">{S.themeCard.help}</p>
      <div className="grid gap-4 sm:grid-cols-2">
        {(
          [
            ['primary', G.primary],
            ['accent', G.accent],
          ] as const
        ).map(([key, text]) => {
          const color = value.theme[key];
          return (
            <div key={key} className="space-y-2">
              <p className="ui-label !mb-0">{text}</p>
              <div className="flex items-start gap-2">
                <Input
                  type="color"
                  aria-label={text}
                  className="!w-16 !p-1"
                  value={HEX.test(color) ? color : '#000000'}
                  onChange={(e) =>
                    onChange({ theme: { ...value.theme, [key]: e.target.value.toUpperCase() } })
                  }
                />
                <Input
                  aria-label={`${text} (#RRGGBB)`}
                  className="font-mono"
                  maxLength={7}
                  value={color}
                  error={HEX.test(color) ? undefined : S.invalidColor}
                  onChange={(e) => onChange({ theme: { ...value.theme, [key]: e.target.value } })}
                />
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
