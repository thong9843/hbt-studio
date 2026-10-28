import type { ScriptCheck, ScriptDiffItem, ScriptExtra, ScriptIssue } from '../api/types';
import { vi } from '../i18n/vi';

/** Mọi thứ của một cảnh (hoặc của cả video) cần hiện ở bước Kiểm tra. */
export interface ScriptRow {
  /** Chỉ số cảnh từ 0; `null` = cả video (nội dung đăng, ảnh bìa, lỗi chung). */
  sceneIndex: number | null;
  diffs: ScriptDiffItem[];
  errors: ScriptIssue[];
  warnings: ScriptIssue[];
}

export interface ScriptRows {
  whole: ScriptRow;
  scenes: ScriptRow[];
  /** Cảnh mới thêm (`extra: "add"`): thu gọn thành "+k cảnh". */
  added: ScriptRow[];
}

const emptyRow = (sceneIndex: number | null): ScriptRow => ({
  sceneIndex,
  diffs: [],
  errors: [],
  warnings: [],
});

/** Gom khác biệt, lỗi, cảnh báo theo cảnh; cảnh mới tách riêng. */
export function buildRows(check: ScriptCheck): ScriptRows {
  const rows = new Map<number | null, ScriptRow>();
  const row = (i: number | null) => {
    let r = rows.get(i);
    if (!r) rows.set(i, (r = emptyRow(i)));
    return r;
  };
  for (const d of check.diff) row(d.scene_index).diffs.push(d);
  for (const e of check.errors) row(e.scene_index).errors.push(e);
  for (const w of check.warnings) row(w.scene_index).warnings.push(w);

  const addedIdx = new Set(
    check.diff
      .filter((d) => d.field === 'scene' && d.scene_index !== null)
      .map((d) => d.scene_index),
  );
  const numbered = [...rows.values()]
    .filter((r): r is ScriptRow & { sceneIndex: number } => r.sceneIndex !== null)
    .sort((a, b) => a.sceneIndex - b.sceneIndex);
  return {
    whole: rows.get(null) ?? emptyRow(null),
    scenes: numbered.filter((r) => !addedIdx.has(r.sceneIndex)),
    added: numbered.filter((r) => addedIdx.has(r.sceneIndex)),
  };
}

/** Số cảnh JSON sẽ ghi vào (không tính phần bị bỏ). */
export function appliedScenes(check: ScriptCheck): number {
  return Math.min(check.counts.json, check.counts.after);
}

/** JSON nhiều cảnh hơn dự án: giao diện phải cho chọn Thêm cảnh / Bỏ phần thừa. */
export function surplusScenes(check: ScriptCheck): number {
  return Math.max(0, check.counts.json - check.counts.project);
}

/** Cần hiện hai lựa chọn lệch số cảnh (lỗi K2 chưa chọn, hoặc đã chọn một trong hai). */
export function hasSurplus(check: ScriptCheck, extra: ScriptExtra | null): boolean {
  return surplusScenes(check) > 0 && (extra !== null || check.errors.some((e) => e.code === 'K2'));
}

/** Dòng "Giữ nguyên:" — những phần JSON không đụng tới. */
export function untouched(check: ScriptCheck): string[] {
  const K = vi.script.keepItems;
  const changed = new Set(check.diff.map((d) => d.field));
  const out: string[] = [K.images, K.voiceFile, K.music, K.settings, K.title];
  if (!changed.has('publish')) out.push(K.publish);
  if (!changed.has('thumbnail')) out.push(K.thumbnail);
  return out;
}
