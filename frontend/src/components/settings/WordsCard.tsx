import { useState } from 'react';
import type { SensitiveCategory } from '../../api/types';
import { vi } from '../../i18n/vi';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Chip } from '../ui/Chip';
import { Input } from '../ui/Field';

const W = vi.settings.words;
const LEVELS = ['info', 'warn', 'block'] as const;

/** Một nhóm từ nhạy cảm cùng chỗ nhập từ mới. */
export interface WordGroup extends SensitiveCategory {
  /** Khoá ổn định trong danh sách (id nhóm có thể đang được sửa). */
  key: string;
}

interface CardProps {
  group: WordGroup;
  onChange: (patch: Partial<WordGroup>) => void;
  onRemove: () => void;
}

function GroupCard({ group, onChange, onRemove }: CardProps) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const word = draft.trim();
    if (word && !group.words.includes(word)) onChange({ words: [...group.words, word] });
    setDraft('');
  };
  return (
    <Card as="li" className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[160px] flex-1">
          <Input
            label={W.id}
            className="font-mono"
            value={group.id}
            onChange={(e) => onChange({ id: e.target.value })}
          />
        </div>
        <div role="group" aria-label={W.level} className="flex flex-wrap gap-2 pb-1">
          {LEVELS.map((l) => (
            <Chip key={l} small selected={group.level === l} onClick={() => onChange({ level: l })}>
              {W.levels[l]}
            </Chip>
          ))}
        </div>
        <Button tone="ghost" size="sm" onClick={onRemove}>
          {W.removeCategory}
        </Button>
      </div>

      <ul aria-label={W.wordsOf(group.id)} className="flex flex-wrap gap-2">
        {group.words.length === 0 && <li className="text-small text-muted">{W.noWords}</li>}
        {group.words.map((word) => (
          <li key={word}>
            <Chip
              small
              aria-label={W.removeWord(word)}
              onClick={() => onChange({ words: group.words.filter((w) => w !== word) })}
            >
              {word}
              <span aria-hidden="true"> ×</span>
            </Chip>
          </li>
        ))}
      </ul>

      <Input
        label={W.addWord}
        placeholder={W.addWordPlaceholder}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
      />
      <Input
        label={W.hint}
        value={group.hint}
        onChange={(e) => onChange({ hint: e.target.value })}
      />
    </Card>
  );
}

interface Props {
  groups: WordGroup[];
  onChange: (groups: WordGroup[]) => void;
}

/**
 * Thẻ Từ nhạy cảm. Nhóm mức Cảnh báo / Chặn hiện sẵn; nhóm mức Lưu ý (ít dùng) gộp vào một mục
 * thu gọn.
 */
export function WordsCard({ groups, onChange }: Props) {
  const [showRare, setShowRare] = useState(false);
  const patch = (key: string, p: Partial<WordGroup>) =>
    onChange(groups.map((g) => (g.key === key ? { ...g, ...p } : g)));
  const remove = (key: string) => onChange(groups.filter((g) => g.key !== key));
  const main = groups.filter((g) => g.level !== 'info');
  const rare = groups.filter((g) => g.level === 'info');
  const render = (g: WordGroup) => (
    <GroupCard
      key={g.key}
      group={g}
      onChange={(p) => patch(g.key, p)}
      onRemove={() => remove(g.key)}
    />
  );
  return (
    <section aria-label={W.title} className="space-y-4">
      <h2 className="text-h2 font-bold">{W.title}</h2>
      <p className="text-small text-muted">{W.help}</p>
      <ul className="space-y-4">{main.map(render)}</ul>
      {rare.length > 0 && (
        <div className="space-y-4">
          <Button
            tone="soft"
            size="sm"
            aria-expanded={showRare}
            onClick={() => setShowRare((v) => !v)}
          >
            {W.rare(rare.length)}
          </Button>
          {showRare && <ul className="space-y-4">{rare.map(render)}</ul>}
        </div>
      )}
      <Button
        tone="soft"
        onClick={() =>
          onChange([
            ...groups,
            {
              key: `new-${groups.length + 1}-${Date.now()}`,
              id: `nhom_${groups.length + 1}`,
              level: 'warn',
              words: [],
              hint: '',
            },
          ])
        }
      >
        + {W.addCategory}
      </Button>
    </section>
  );
}
