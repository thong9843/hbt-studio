import type { AlignerInfo } from '../../api/types';
import { vi } from '../../i18n/vi';
import { alignerLabel, alignerNotes } from '../../utils/aligner';
import { formatDuration } from '../../utils/format';
import { AlertIcon } from '../icons';
import { Card } from '../ui/Card';

const R = vi.export.result;

/** Số liệu của một lần dựng, lấy từ job vừa xong hoặc từ một dòng lịch sử. */
export interface ResultInfo {
  duration: number | null;
  fps: number | null;
  lufs: number | null;
  aligner: string | null;
  aligner_info?: AlignerInfo | null;
  trimmed_tail?: string | null;
  trimmed_tail_seconds?: number | null;
  /** Thời gian dựng (giây); bản cũ không ghi thì `null`. */
  seconds: number | null;
  warnings: string[];
}

/** Thẻ Kết quả: độ dài, LUFS, căn chữ + tỉ lệ khớp, thời gian dựng, cắt đuôi + Nghe. */
export function ResultCard({ info }: { info: ResultInfo }) {
  const stats: [string, string][] = [
    [R.duration, info.duration === null ? '—' : formatDuration(info.duration)],
    [R.lufs, info.lufs === null ? '—' : `${info.lufs.toFixed(1)} LUFS`],
    [R.aligner, info.aligner ? alignerLabel(info.aligner, info.aligner_info) : '—'],
    [R.seconds, info.seconds === null ? '—' : `${info.seconds} ${vi.common.seconds}`],
  ];
  return (
    <Card as="section" aria-label={R.title} className="space-y-4">
      <h2 className="text-h2 font-bold">{R.title}</h2>
      <dl className="grid grid-cols-2 gap-3 min-[900px]:grid-cols-4">
        {stats.map(([k, v]) => (
          <div key={k} className="ui-inner p-3">
            <dt className="text-tiny font-semibold text-muted">{k}</dt>
            <dd className="font-bold tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      {info.trimmed_tail && (
        <div className="space-y-2 text-small">
          <p className="text-muted">
            {R.trimmedTail((info.trimmed_tail_seconds ?? 0).toFixed(1).replace('.', ','))}
          </p>
          <audio controls aria-label={R.trimmedTailPlayer} src={info.trimmed_tail} />
        </div>
      )}
      {info.aligner &&
        alignerNotes(info.aligner, info.aligner_info).map((note) => (
          <p key={note} className="text-small text-muted">
            {note}
          </p>
        ))}
      {info.warnings.length > 0 && (
        <div className="ui-note-yel p-4 text-small">
          <b className="flex items-center gap-2">
            <AlertIcon size={18} />
            {R.warnings}
          </b>
          <ul className="mt-1 list-disc pl-5">
            {info.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
