import type { Label, Theme } from '../../api/types';
import { vi } from '../../i18n/vi';
import { PlusIcon, TrashIcon } from '../icons';
import { Button } from '../ui/Button';
import { Drawer } from '../ui/Drawer';
import { Input } from '../ui/Field';
import { IconButton } from '../ui/IconButton';
import { ColorDots } from './ColorDots';

const T = vi.compose.labels;
const NUMBER_FIELDS = [
  ['x', T.x],
  ['y', T.y],
  ['size', T.size],
  ['rot', T.rot],
] as const;

interface Props {
  open: boolean;
  onClose: () => void;
  /** Số cảnh hiển thị (từ 1). */
  sceneNumber: number;
  labels: Label[];
  theme: Theme;
  onChange: (labels: Label[]) => void;
}

/** Ngăn kéo "Nhãn cảnh n": nhãn cố định của cảnh (chữ, vị trí, cỡ, xoay, màu). */
export function LabelsDrawer({ open, onClose, sceneNumber, labels, theme, onChange }: Props) {
  const patch = (i: number, change: Partial<Label>) =>
    onChange(labels.map((l, k) => (k === i ? { ...l, ...change } : l)));
  return (
    <Drawer open={open} onClose={onClose} title={T.title(sceneNumber)}>
      {labels.length === 0 && <p className="mb-4 text-muted">{T.empty}</p>}
      <ul className="space-y-3">
        {labels.map((label, i) => (
          <li key={i} className="ui-inner space-y-3 p-3">
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <Input
                  aria-label={`${T.text} ${i + 1}`}
                  placeholder={T.item(i + 1)}
                  value={label.text}
                  onChange={(e) => patch(i, { text: e.target.value })}
                />
              </div>
              <IconButton
                label={T.remove(i + 1)}
                onClick={() => onChange(labels.filter((_, k) => k !== i))}
              >
                <TrashIcon size={18} />
              </IconButton>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {NUMBER_FIELDS.map(([field, text]) => (
                <Input
                  key={field}
                  type="number"
                  label={text}
                  aria-label={`${text} ${i + 1}`}
                  value={label[field]}
                  onChange={(e) => patch(i, { [field]: Number(e.target.value) || 0 })}
                />
              ))}
            </div>
            <ColorDots
              value={label.color}
              theme={theme}
              label={`${T.color} ${i + 1}`}
              onChange={(color) => patch(i, { color })}
            />
          </li>
        ))}
      </ul>
      <Button
        tone="soft"
        size="sm"
        className="mt-4"
        icon={<PlusIcon size={18} />}
        onClick={() =>
          onChange([...labels, { text: '', x: 540, y: 960, size: 80, color: 'ink', rot: 0 }])
        }
      >
        {T.add}
      </Button>
    </Drawer>
  );
}
