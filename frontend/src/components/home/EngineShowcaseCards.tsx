import { Link } from 'react-router-dom';
import { vi } from '../../i18n/vi';
import { MessagesSquareIcon, SmartphoneIcon, SparklesIcon, ZapIcon } from '../icons';

/**
 * 4 Thẻ Khởi Tạo Tối Giản chuẩn VEED.IO Dashboard (Luật 90 · 8 · 2):
 * Nền trắng (#FFFFFF / Dark #151821), viền mảnh 1px (#E6E8EE), khung minh họa tối giản tinh tế,
 * mô tả 1 dòng ngắn gọn, hover viền đỏ thương hiệu HBT (#D9232E).
 */
export function EngineShowcaseCards() {
  const E = vi.veedHome.engines;
  return (
    <section
      aria-label="4 Động cơ Sáng tạo"
      className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4"
    >
      {/* 1. HBT Core */}
      <div className="group flex flex-col justify-between rounded-card border border-line bg-card p-5 shadow-card transition-colors hover:border-brand">
        <div>
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-pill bg-[var(--accent-soft)] px-2.5 py-0.5 text-tiny font-bold text-[var(--on-accent-soft)]">
              <ZapIcon size={13} />
              {E.coreTitle}
            </span>
            <span className="text-tiny font-semibold text-muted tabular-nums">50fps · 9:16</span>
          </div>

          <h2 className="mt-3 text-title font-bold text-text">Video Kiến thức & Khám phá</h2>
          <p className="mt-1 text-small text-muted">{E.coreDesc}</p>

          <div
            aria-hidden="true"
            className="mt-4 flex items-center gap-3 rounded-inner border border-line bg-soft p-3"
          >
            <div className="flex h-14 w-11 shrink-0 flex-col justify-between rounded-md border border-line bg-card p-1.5">
              <div className="h-1.5 w-7 rounded bg-brand" />
              <div className="h-6 w-full rounded bg-soft-2" />
              <div className="h-1.5 w-5 rounded bg-line-input" />
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <span className="block text-[11px] font-bold text-text">
                1-Click Gemini & JSON 0-Token
              </span>
              <div className="h-1.5 w-4/5 rounded bg-line-input" />
              <div className="h-1.5 w-3/5 rounded bg-soft-2" />
            </div>
          </div>
        </div>

        <div className="mt-4">
          <Link to="/core" className="ui-btn ui-btn-ink w-full justify-center">
            <ZapIcon size={15} />
            Tạo kịch bản AI
          </Link>
        </div>
      </div>

      {/* 2. PostV */}
      <div className="group flex flex-col justify-between rounded-card border border-line bg-card p-5 shadow-card transition-colors hover:border-brand">
        <div>
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-pill bg-soft px-2.5 py-0.5 text-tiny font-bold text-text">
              <SmartphoneIcon size={13} />
              {E.postvTitle}
            </span>
            <span className="text-tiny font-semibold text-muted tabular-nums">60fps · Threads</span>
          </div>

          <h2 className="mt-3 text-title font-bold text-text">Bài đăng MXH & Bình luận</h2>
          <p className="mt-1 text-small text-muted">{E.postvDesc}</p>

          <div
            aria-hidden="true"
            className="mt-4 flex items-center gap-3 rounded-inner border border-line bg-soft p-3"
          >
            <div className="flex h-14 w-11 shrink-0 items-center justify-center rounded-md border border-line bg-card p-1">
              <div className="w-full space-y-1 rounded bg-soft p-1">
                <div className="h-1.5 w-5 rounded bg-text" />
                <div className="h-1 w-full rounded bg-line-input" />
                <div className="h-1 w-4/5 rounded bg-line-input" />
              </div>
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <span className="block text-[11px] font-bold text-text">
                Tự tải bài & lọc bình luận
              </span>
              <div className="h-1.5 w-4/5 rounded bg-line-input" />
              <div className="h-1.5 w-3/5 rounded bg-soft-2" />
            </div>
          </div>
        </div>

        <div className="mt-4">
          <Link to="/postv" className="ui-btn ui-btn-ink w-full justify-center">
            <SmartphoneIcon size={15} />
            Dán link Threads / Reddit
          </Link>
        </div>
      </div>

      {/* 3. Chatting */}
      <div className="group flex flex-col justify-between rounded-card border border-line bg-card p-5 shadow-card transition-colors hover:border-brand">
        <div>
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-pill bg-soft px-2.5 py-0.5 text-tiny font-bold text-text">
              <MessagesSquareIcon size={13} />
              {E.chattingTitle}
            </span>
            <span className="text-tiny font-semibold text-muted tabular-nums">60fps · Chat</span>
          </div>

          <h2 className="mt-3 text-title font-bold text-text">Hội thoại Tin nhắn Kịch tính</h2>
          <p className="mt-1 text-small text-muted">{E.chattingDesc}</p>

          <div
            aria-hidden="true"
            className="mt-4 flex items-center gap-3 rounded-inner border border-line bg-soft p-3"
          >
            <div className="flex h-14 w-11 shrink-0 flex-col justify-center gap-1 rounded-md border border-line bg-card p-1.5">
              <div className="h-2 w-6 self-start rounded-full bg-line-input" />
              <div className="h-2 w-7 self-end rounded-full bg-brand" />
              <div className="h-2 w-5 self-start rounded-full bg-line-input" />
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <span className="block text-[11px] font-bold text-text">
                Messenger / Zalo + Sticker
              </span>
              <div className="h-1.5 w-4/5 rounded bg-line-input" />
              <div className="h-1.5 w-3/5 rounded bg-soft-2" />
            </div>
          </div>
        </div>

        <div className="mt-4">
          <Link to="/chatting" className="ui-btn ui-btn-ink w-full justify-center">
            <MessagesSquareIcon size={15} />
            Tạo đoạn chat 2 người
          </Link>
        </div>
      </div>

      {/* 4. StickV */}
      <div className="group flex flex-col justify-between rounded-card border border-line bg-card p-5 shadow-card transition-colors hover:border-brand">
        <div>
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-pill bg-[var(--accent-soft)] px-2.5 py-0.5 text-tiny font-bold text-[var(--on-accent-soft)]">
              <SparklesIcon size={13} />
              {E.stickvTitle}
            </span>
            <span className="text-tiny font-semibold text-muted tabular-nums">9:16 & 16:9</span>
          </div>

          <h2 className="mt-3 text-title font-bold text-text">Video Người que 2D/2.5D</h2>
          <p className="mt-1 text-small text-muted">{E.stickvDesc}</p>

          <div
            aria-hidden="true"
            className="mt-4 flex items-center gap-3 rounded-inner border border-line bg-soft p-3"
          >
            <div className="flex h-14 w-11 shrink-0 flex-col items-center justify-between rounded-md border border-line bg-card p-1.5">
              <div className="h-2.5 w-full rounded bg-soft-2" />
              <div className="h-5 w-5 rounded-full border-2 border-text bg-card" />
              <div className="h-1.5 w-5 rounded bg-brand" />
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <span className="block text-[11px] font-bold text-text">
                18 dáng Puppet + Bảng Rich Text
              </span>
              <div className="h-1.5 w-4/5 rounded bg-line-input" />
              <div className="h-1.5 w-3/5 rounded bg-soft-2" />
            </div>
          </div>
        </div>

        <div className="mt-4">
          <Link to="/stickv" className="ui-btn ui-btn-brand w-full justify-center">
            <SparklesIcon size={15} />
            Tạo video Người que
          </Link>
        </div>
      </div>
    </section>
  );
}
