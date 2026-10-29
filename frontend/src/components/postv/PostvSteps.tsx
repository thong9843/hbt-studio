import { NavLink } from 'react-router-dom';
import { vi } from '../../i18n/vi';
import { CheckIcon } from '../icons';
import { cx } from '../ui/cx';

const PATHS = ['', 'pick', 'script', 'preview', 'export'] as const;

interface Props {
  /** Bước đã xong (chỉ số từ 0): hiện dấu tích. */
  done: boolean[];
}

/** Thanh 5 bước nằm ngang ở đầu màn PostV (K-36). */
export function PostvSteps({ done }: Props) {
  const t = vi.postv;
  return (
    <nav aria-label={t.stepsLabel}>
      <ol className="flex flex-wrap gap-2">
        {t.steps.map((label, i) => (
          <li key={label} className="min-w-0 flex-1 basis-[150px]">
            <NavLink
              to={PATHS[i]}
              end
              className={({ isActive }) => cx('ui-step', isActive && 'ui-step-on')}
              aria-label={`${t.stepOf(i + 1)}: ${label}`}
            >
              <span className="ui-step-num num" aria-hidden="true">
                {done[i] ? <CheckIcon size={14} strokeWidth={3} /> : i + 1}
              </span>
              <span className="min-w-0 truncate">{label}</span>
            </NavLink>
          </li>
        ))}
      </ol>
    </nav>
  );
}
