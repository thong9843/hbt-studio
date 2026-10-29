import type { PostvProject } from '../../api/types';
import { vi } from '../../i18n/vi';
import { formatCount } from '../../utils/count';
import { cardText } from '../../utils/postvSegments';

function Stat({ icon, value }: { icon: string; value: number | null }) {
  if (value === null) return null;
  return (
    <span className="inline-flex items-center gap-1">
      <svg
        width="11"
        height="11"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        aria-hidden="true"
      >
        <path d={icon} />
      </svg>
      <span className="num">{formatCount(value)}</span>
    </span>
  );
}

const HEART = 'M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z';
const COMMENT = 'M4 5h16v11H10l-6 4z';
const REPOST = 'M7 7h10l-3-3M17 17H7l3 3';
const SEND = 'M4 12l16-8-6 16-2-6z';

/**
 * Xem trước thẻ bài gốc (xấp xỉ bằng CSS, 288×512). Ảnh thẻ thật do bộ vẽ Pillow tạo ở PV3.
 * Tên tài khoản và thời gian đúng như bài đã dán (K-22).
 */
export function PostvCardPreview({ post }: { post: PostvProject['post'] }) {
  const text = cardText(post);
  return (
    <figure className="m-0 flex flex-col items-center gap-2">
      <div
        className="relative overflow-hidden rounded-[28px] bg-soft shadow-lg"
        style={{ width: 288, height: 512 }}
      >
        <div
          className="absolute inset-x-0 bottom-0 bg-[#6DB33F]"
          style={{ height: '34%' }}
          aria-hidden="true"
        />
        <div
          className="absolute inset-x-0 bottom-0 bg-[#8B5A2B]"
          style={{ height: '14%' }}
          aria-hidden="true"
        />
        <div
          className="absolute flex flex-col gap-1.5 rounded-2xl bg-white p-3 text-[#16120F]"
          style={{ left: 14, right: 14, top: 60 }}
        >
          <div className="flex items-center gap-2">
            <span className="h-6 w-6 shrink-0 rounded-full bg-[#D3D3D9]" aria-hidden="true" />
            <span className="truncate text-[11px] font-extrabold">{post.handle || '—'}</span>
            <span className="text-[10px] text-[#6E6A72]">{post.age}</span>
          </div>
          {text && <p className="m-0 text-[11px] leading-[15px]">{text}</p>}
          <div className="flex gap-3 text-[10px] font-bold text-[#3A3540]">
            <Stat icon={HEART} value={post.likes} />
            <Stat icon={COMMENT} value={post.replies} />
            <Stat icon={REPOST} value={post.reposts} />
            <Stat icon={SEND} value={post.shares} />
          </div>
          {post.views !== null && (
            <span className="text-[9px] text-[#6E6A72]">
              <span className="num">{formatCount(post.views)}</span> {vi.postv.source.views}
            </span>
          )}
        </div>
      </div>
      <figcaption className="text-small text-muted">{vi.postv.source.previewTitle}</figcaption>
    </figure>
  );
}
