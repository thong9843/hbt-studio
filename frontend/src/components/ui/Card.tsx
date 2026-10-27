import type { HTMLAttributes } from 'react';
import { cx } from './cx';
import './ui.css';

interface Props extends HTMLAttributes<HTMLElement> {
  /** Thẻ bấm được: nhấc 2 px khi hover, bóng đậm hơn. Thẻ tĩnh thì bỏ qua. */
  interactive?: boolean;
  padded?: boolean;
  as?: 'div' | 'section' | 'article' | 'li';
}

/** Thẻ bo 24. Thẻ `interactive` nhận Tab và Enter/Space như nút. */
export function Card({
  interactive,
  padded = true,
  as: Tag = 'div',
  className,
  onKeyDown,
  ...rest
}: Props) {
  return (
    <Tag
      {...rest}
      role={interactive ? (rest.role ?? 'button') : rest.role}
      tabIndex={interactive ? (rest.tabIndex ?? 0) : rest.tabIndex}
      onKeyDown={(e) => {
        onKeyDown?.(e);
        if (interactive && !e.defaultPrevented && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          e.currentTarget.click();
        }
      }}
      className={cx('ui-card', padded && 'ui-card-pad', interactive && 'ui-card-link', className)}
    />
  );
}
