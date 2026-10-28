import { useState } from 'react';
import type { Scene } from '../../api/types';
import { vi } from '../../i18n/vi';
import { CARD_Y_MAX, clampCardY } from '../../utils/card';
import { sceneNumber } from '../../utils/scene';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Chip } from '../ui/Chip';
import { Input } from '../ui/Field';
import { Switch } from '../ui/Switch';
import { LabelsDrawer } from './LabelsDrawer';

const T = vi.compose.options;
/** Vị trí phụ đề mặc định khi chuyển từ "Tự động" sang px (khớp `caption_y` mặc định 1400). */
const DEFAULT_CAPTION_Y = 1400;

/** Ô px phụ đề: giữ chữ đang gõ (kể cả rỗng) và chỉ ghi vào cảnh khi là số hợp lệ. */
function CaptionY({ value, onChange }: { value: number; onChange: (y: number) => void }) {
  const [draft, setDraft] = useState(String(value));
  return (
    <Input
      type="number"
      min={0}
      max={CARD_Y_MAX}
      aria-label={T.captionY}
      value={draft}
      onChange={(e) => {
        setDraft(e.target.value);
        if (e.target.value.trim() !== '') onChange(clampCardY(e.target.value));
      }}
      onBlur={() => setDraft(String(value))}
    />
  );
}

interface Props {
  sceneIndex: number;
  scene: Scene;
  theme: { primary: string; accent: string };
  onChange: (fn: (scene: Scene) => Scene) => void;
}

/** Cột 2, thẻ "Tuỳ chọn": Cú lật, vị trí phụ đề của cảnh, và nút mở nhãn cố định. */
export function OptionsPanel({ sceneIndex, scene, theme, onChange }: Props) {
  const [labelsOpen, setLabelsOpen] = useState(false);
  const px = scene.caption_y !== null;
  return (
    <Card as="section" aria-label={T.title} className="space-y-4">
      <h2 className="text-h2 font-bold">{T.title}</h2>

      <div className="flex items-center justify-between gap-3" title={T.punchTitle}>
        <span className="text-body font-semibold">{T.punch}</span>
        <Switch
          label={T.punch}
          checked={scene.punch}
          onChange={(punch) => onChange((s) => ({ ...s, punch }))}
        />
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <span className="text-body font-semibold" id={`cap-${sceneIndex}`}>
            {T.captions}
          </span>
          <div role="group" aria-labelledby={`cap-${sceneIndex}`} className="flex gap-1">
            <Chip small selected={!px} onClick={() => onChange((s) => ({ ...s, caption_y: null }))}>
              {T.captionAuto}
            </Chip>
            <Chip
              small
              selected={px}
              onClick={() =>
                onChange((s) => ({ ...s, caption_y: s.caption_y ?? DEFAULT_CAPTION_Y }))
              }
            >
              {T.captionPx}
            </Chip>
          </div>
        </div>
        {px && (
          <CaptionY
            key={sceneIndex}
            value={scene.caption_y ?? DEFAULT_CAPTION_Y}
            onChange={(caption_y) => onChange((s) => ({ ...s, caption_y }))}
          />
        )}
      </div>

      <Button tone="soft" className="w-full justify-between" onClick={() => setLabelsOpen(true)}>
        <span>{T.labels(scene.labels.length)}</span>
        <span aria-hidden="true">›</span>
      </Button>
      <LabelsDrawer
        open={labelsOpen}
        onClose={() => setLabelsOpen(false)}
        sceneNumber={sceneNumber(sceneIndex)}
        labels={scene.labels}
        theme={theme}
        onChange={(labels) => onChange((s) => ({ ...s, labels }))}
      />
    </Card>
  );
}
