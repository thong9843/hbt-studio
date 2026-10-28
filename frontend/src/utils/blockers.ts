import type { Project } from '../api/types';
import { vi } from '../i18n/vi';
import { sceneNumber } from './scene';
import { voiceFile } from './voice';

/** Lý do chưa thể dựng (nút Xem nhanh / Xuất bản đẹp tắt). Rỗng = đủ nguyên liệu. */
export function renderBlockers(p: Pick<Project, 'scenes' | 'voice'>): string[] {
  const out: string[] = [];
  const missing = p.scenes.flatMap((s, i) => (s.image ? [] : [sceneNumber(i)]));
  if (missing.length > 0) out.push(vi.compose.preview.blockedImage(missing.join(', ')));
  if (!voiceFile(p.voice)) out.push(vi.compose.preview.blockedVoice);
  return out;
}

export function primaryActionState(p: Pick<Project, 'scenes' | 'voice'>): {
  enabled: boolean;
  reason?: string;
} {
  const blockers = renderBlockers(p);
  return blockers.length === 0
    ? { enabled: true }
    : { enabled: false, reason: blockers.join(' · ') };
}
