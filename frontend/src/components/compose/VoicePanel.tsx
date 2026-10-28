import { useRef } from 'react';
import { vi } from '../../i18n/vi';
import { VOICE_CHAR_LIMIT, countVoiceChars } from '../../utils/voice';
import { insertVoiceMark, type VoiceMark } from '../../utils/voiceEdit';
import { Badge } from '../ui/Badge';
import { Chip } from '../ui/Chip';
import { Textarea } from '../ui/Field';
import { Progress } from '../ui/Progress';

const T = vi.compose.voice;

interface Props {
  sceneIndex: number;
  voice: string;
  /** Tổng ký tự lời đọc cả video. */
  totalChars: number;
  onChange: (voice: string) => void;
}

/** Cột 2: lời đọc cảnh + chip cú pháp `|` / `{ }` + thanh "Cả video n/750". */
export function VoicePanel({ sceneIndex, voice, totalChars, onChange }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const over = totalChars > VOICE_CHAR_LIMIT;

  const insert = (mark: VoiceMark) => {
    const area = box.current?.querySelector('textarea');
    const start = area?.selectionStart ?? voice.length;
    const end = area?.selectionEnd ?? voice.length;
    const edit = insertVoiceMark(voice, start, end, mark);
    onChange(edit.text);
    // Đặt lại con trỏ sau khi React vẽ lại ô.
    requestAnimationFrame(() => {
      area?.focus();
      area?.setSelectionRange(edit.caret, edit.caret);
    });
  };

  return (
    <section aria-label={T.title} className="space-y-3">
      <h2 className="text-h2 font-bold">{T.title}</h2>
      <div ref={box}>
        <Textarea
          id={`voice-${sceneIndex}`}
          aria-label={T.label}
          rows={7}
          value={voice}
          limit={VOICE_CHAR_LIMIT}
          count={totalChars}
          countTitle={T.totalBar}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Chip small title={T.breakTitle} onClick={() => insert('break')}>
          <span aria-hidden="true">|</span> {T.breakChip}
        </Chip>
        <Chip small title={T.numberTitle} onClick={() => insert('number')}>
          <span aria-hidden="true">{'{ }'}</span> {T.numberChip}
        </Chip>
        <span className="ml-auto text-small font-semibold tabular-nums text-muted">
          {T.sceneCount(countVoiceChars(voice))}
        </span>
      </div>
      <div className="ui-inner space-y-2 p-3">
        {over && (
          <Badge tone="yel" role="alert" title={T.overTitle}>
            {T.over}
          </Badge>
        )}
        <Progress value={(totalChars / VOICE_CHAR_LIMIT) * 100} label={T.totalBar} />
      </div>
    </section>
  );
}
