import { Link } from 'react-router-dom';
import { useDraft, useDraftExists } from '../../hooks/useDraft';
import { vi } from '../../i18n/vi';
import { AlertIcon } from '../icons';

const T = vi.gd2.images;

/**
 * Tab Xuất: nhắc "Ảnh chưa duyệt" kèm link sang bước Ảnh. Chỉ với dự án có bản nháp GĐ2.
 * Chỉ là lời nhắc: không chặn xuất, không đụng bộ dựng.
 */
export function ImagesReminder({ slug }: { slug: string }) {
  const exists = useDraftExists(slug);
  const { data } = useDraft(slug, exists);
  if (!exists || !data || data.images_approved) return null;
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 rounded-card bg-tint-yel px-4 py-3 text-small font-semibold text-on-tint-yel"
    >
      <AlertIcon size={18} />
      <span>{T.exportReminder}</span>
      <Link to={`/p/${slug}/images`} className="ui-btn ui-btn-soft ui-btn-sm ml-auto">
        {T.exportReminderLink}
      </Link>
    </div>
  );
}
