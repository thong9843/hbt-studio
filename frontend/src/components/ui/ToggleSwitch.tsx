import { Switch } from './Switch';
import { cx } from './cx';

export interface ToggleSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
  className?: string;
}

/**
 * Công tắc gạt chuẩn VEED.IO (ToggleSwitch):
 * Có thể đứng độc lập (chỉ nút switch có `aria-label`) hoặc kèm nhãn hiển thị gọn gàng.
 */
export function ToggleSwitch({
  checked,
  onChange,
  label,
  description,
  disabled,
  className,
}: ToggleSwitchProps) {
  if (!description) {
    return (
      <Switch
        checked={checked}
        onChange={onChange}
        label={label}
        disabled={disabled}
        className={className}
      />
    );
  }

  return (
    <div className={cx('flex items-center justify-between gap-3', className)}>
      <div className="min-w-0">
        <p className="text-small font-semibold text-text">{label}</p>
        <p className="text-tiny text-muted">{description}</p>
      </div>
      <Switch checked={checked} onChange={onChange} label={label} disabled={disabled} />
    </div>
  );
}
