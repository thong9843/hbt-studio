import { useState } from 'react';
import type { ScriptCheck, ScriptExtra, ScriptIssue, Theme } from '../../api/types';
import { vi } from '../../i18n/vi';
import { sceneNumber } from '../../utils/scene';
import {
  buildRows,
  hasSurplus,
  surplusScenes,
  untouched,
  type ScriptRow,
} from '../../utils/scriptDiff';
import { AlertIcon } from '../icons';
import { Badge } from '../ui/Badge';
import { Chip } from '../ui/Chip';
import { DiffValue } from './DiffValue';

const T = vi.script;

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'danger' }) {
  return (
    <div className="rounded-inner bg-soft-2 p-3">
      <p className="text-tiny font-semibold text-muted">{label}</p>
      <p
        className={`text-title font-extrabold tabular-nums ${tone === 'danger' ? 'text-danger' : ''}`}
      >
        {value}
      </p>
    </div>
  );
}

function Issue({ issue, kind }: { issue: ScriptIssue; kind: 'error' | 'warning' }) {
  const block = issue.level === 'block';
  return (
    <li
      className={`flex items-start gap-2 rounded-input px-3 py-2 text-small ${
        kind === 'error' || block ? 'bg-danger-soft text-danger' : 'bg-tint-yel text-on-tint-yel'
      }`}
    >
      <AlertIcon size={16} />
      <span className="min-w-0 flex-1 break-words">
        <span className="font-bold">
          {kind === 'error' ? T.errorsHeading : block ? T.levelBlock : T.levelWarn} · {issue.code}
        </span>
        {' — '}
        {issue.message}
      </span>
    </li>
  );
}

function Diff({ row, theme }: { row: ScriptRow; theme: Theme }) {
  const fieldNames = T.fields as Record<string, string>;
  return (
    <div className="space-y-3">
      {row.diffs.map((d, i) => (
        <div key={`${d.field}-${i}`}>
          <p className="text-tiny font-semibold text-muted">{fieldNames[d.field] ?? d.field}</p>
          <div className="mt-1 grid gap-2 sm:grid-cols-2">
            {d.field !== 'scene' && (
              <div className="rounded-inner bg-soft-2 p-3 text-small">
                <p className="mb-1 text-tiny font-bold text-muted">{T.from}</p>
                <DiffValue field={d.field} value={d.before} theme={theme} />
              </div>
            )}
            <div
              className={`rounded-inner bg-soft-2 p-3 text-small ${d.field === 'scene' ? 'sm:col-span-2' : ''}`}
            >
              <p className="mb-1 text-tiny font-bold text-muted">{T.to}</p>
              <DiffValue field={d.field} value={d.after} theme={theme} />
            </div>
          </div>
        </div>
      ))}
      {row.errors.length + row.warnings.length > 0 && (
        <ul className="space-y-1">
          {row.errors.map((e, i) => (
            <Issue key={`e${i}`} issue={e} kind="error" />
          ))}
          {row.warnings.map((w, i) => (
            <Issue key={`w${i}`} issue={w} kind="warning" />
          ))}
        </ul>
      )}
    </div>
  );
}

function Section({ title, row, theme }: { title: string; row: ScriptRow; theme: Theme }) {
  return (
    <section className="rounded-card border border-line p-4">
      <h3 className="mb-3 text-h2 font-bold">{title}</h3>
      <Diff row={row} theme={theme} />
    </section>
  );
}

interface Props {
  check: ScriptCheck;
  theme: Theme;
  extra: ScriptExtra | null;
  busy: boolean;
  onExtra: (extra: ScriptExtra) => void;
}

/** Bước 2 của hộp Dán JSON: 3 ô số, khác biệt theo cảnh, "Giữ nguyên", ghi chú căn chữ lại. */
export function ScriptCheckView({ check, theme, extra, busy, onExtra }: Props) {
  const rows = buildRows(check);
  const [showAdded, setShowAdded] = useState(false);
  const { json, project } = check.counts;
  const surplus = hasSurplus(check, extra);
  const wholeIssues = rows.whole.errors.length + rows.whole.warnings.length > 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Stat
          label={T.stats.scenes}
          value={json === project ? T.scenesEqual(json, project) : T.scenesDiffer(json, project)}
        />
        <Stat
          label={T.stats.errors}
          value={String(check.errors.length)}
          tone={check.errors.length > 0 ? 'danger' : undefined}
        />
        <Stat label={T.stats.warnings} value={String(check.warnings.length)} />
      </div>

      {surplus && (
        <div role="group" aria-label={T.mismatch.label(surplusScenes(check))} className="space-y-2">
          <p className="text-small font-bold">{T.mismatch.label(surplusScenes(check))}</p>
          <div className="flex flex-wrap gap-2">
            <Chip selected={extra === 'add'} disabled={busy} onClick={() => onExtra('add')}>
              {T.mismatch.add}
            </Chip>
            <Chip selected={extra === 'trim'} disabled={busy} onClick={() => onExtra('trim')}>
              {T.mismatch.trim}
            </Chip>
          </div>
        </div>
      )}

      {wholeIssues && <Section title={T.whole} row={{ ...rows.whole, diffs: [] }} theme={theme} />}

      {rows.scenes.map((r) => (
        <Section
          key={r.sceneIndex}
          title={T.scene(sceneNumber(r.sceneIndex as number))}
          row={r}
          theme={theme}
        />
      ))}

      {rows.added.length > 0 && (
        <section className="rounded-card border border-line p-4">
          <button
            type="button"
            className="ui-row w-full text-left font-bold"
            aria-expanded={showAdded}
            onClick={() => setShowAdded((v) => !v)}
          >
            {T.addedScenes(rows.added.length)}
          </button>
          {showAdded && (
            <div className="mt-3 space-y-3">
              {rows.added.map((r) => (
                <div key={r.sceneIndex}>
                  <h3 className="mb-2 text-small font-bold">
                    {T.scene(sceneNumber(r.sceneIndex as number))} · {T.addedEmpty}
                  </h3>
                  <Diff row={r} theme={theme} />
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {rows.whole.diffs.length > 0 && (
        <Section
          title={`${T.fields.publish} / ${T.fields.thumbnail}`}
          row={{ ...rows.whole, errors: [], warnings: [] }}
          theme={theme}
        />
      )}

      {check.diff.length === 0 && check.errors.length === 0 && (
        <p className="text-small text-muted">{T.nothingChanged}</p>
      )}

      <p className="text-small text-muted">
        <span className="font-bold">{T.keep}</span> {untouched(check).join(' · ')}
      </p>
      {check.realign_scenes.length > 0 && (
        <Badge tone="yel">{T.realign(check.realign_scenes.length)}</Badge>
      )}
    </div>
  );
}
