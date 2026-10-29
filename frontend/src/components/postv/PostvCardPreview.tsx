import { api } from '../../api/endpoints';
import { vi } from '../../i18n/vi';

interface Props {
  slug: string;
  kind: 'hook' | 'post' | 'comment';
  /** Id bình luận khi `kind` là `comment`. */
  refId?: string;
  /** Tăng sau mỗi lần lưu để tải lại ảnh. */
  version: number;
  caption?: string;
}

/**
 * Xem trước thẻ: ảnh thật do máy chủ vẽ bằng Pillow từ dữ liệu đã lưu (cùng bộ vẽ với video),
 * đặt trên khung nền của clip đầu. Tên tài khoản và thời gian đúng như bài đã dán (K-22).
 */
export function PostvCardPreview({ slug, kind, refId, version, caption }: Props) {
  const label = caption ?? vi.postv.source.previewTitle;
  return (
    <figure className="m-0 flex flex-col items-center gap-2">
      <div
        className="relative overflow-hidden rounded-[28px] bg-soft shadow-lg"
        style={{ width: 288, height: 512 }}
      >
        <img
          src={api.postvCardUrl(slug, { kind, ref: refId, w: 288, version })}
          alt={label}
          width={288}
          height={512}
          className="block h-full w-full"
        />
      </div>
      <figcaption className="text-small text-muted">{label}</figcaption>
    </figure>
  );
}
