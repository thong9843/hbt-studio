import { Link } from 'react-router-dom';
import { MessagesSquareIcon, SmartphoneIcon, SparklesIcon, ZapIcon } from '../icons';

/**
 * 4 Thẻ Động cơ Sáng tạo tương tác trên Trang chủ:
 * Mỗi thẻ có dải accent/glow theo màu định danh riêng, hình minh họa UI thu nhỏ trực quan
 * cấu trúc video đầu ra và nút bấm hành động rõ nghĩa.
 */
export function EngineShowcaseCards() {
  return (
    <section
      aria-label="4 Động cơ Sáng tạo"
      className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4"
    >
      {/* 1. HBT Core — Video Kiến thức (San hô / Đỏ hồng) */}
      <div className="group relative flex flex-col justify-between overflow-hidden rounded-card border border-line bg-card p-5 shadow-card transition-all duration-180 hover:-translate-y-0.5 hover:border-engine-core/50 hover:shadow-[0_14px_36px_-8px_rgba(244,63,94,0.22)]">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r from-[#F43F5E] to-[#E11D48]"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-[#F43F5E]/10 blur-2xl transition-opacity group-hover:opacity-100"
        />

        <div>
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-pill bg-engine-core-soft px-3 py-1 text-tiny font-extrabold text-on-engine-core-soft">
              <ZapIcon size={14} />
              HBT Core · 50fps
            </span>
            <span className="text-tiny font-semibold text-muted">10–12 phân đoạn</span>
          </div>

          <h2 className="mt-3 text-title font-extrabold text-text">Video Kiến thức & Khám phá</h2>
          <p className="mt-1 text-small text-muted">
            Nhập ý tưởng hoặc dán JSON. Tự tạo ảnh, giọng VieNeu & phụ đề karaoke.
          </p>

          {/* Minh họa UI thu nhỏ: Khung thẻ kem + ảnh minh họa */}
          <div
            aria-hidden="true"
            className="mt-4 flex items-center gap-3 rounded-inner border border-engine-core/20 bg-engine-core-soft/50 p-3"
          >
            <div className="flex h-16 w-12 shrink-0 flex-col justify-between rounded-lg border border-amber-300/60 bg-[#FFFDF7] p-1.5 shadow-sm">
              <div className="h-1.5 w-8 rounded bg-engine-core/80" />
              <div className="h-7 w-full rounded bg-gradient-to-br from-rose-200 to-amber-100" />
              <div className="h-1.5 w-6 rounded bg-slate-300" />
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-engine-core" />
                <span className="text-[11px] font-bold text-text">V2 1-Click Gemini + V1 JSON</span>
              </div>
              <div className="h-2 w-4/5 rounded bg-engine-core/15" />
              <div className="h-2 w-3/5 rounded bg-engine-core/10" />
            </div>
          </div>
        </div>

        <div className="mt-5">
          <Link to="/core" className="ui-btn ui-btn-core w-full justify-center">
            <ZapIcon size={16} />
            Tạo kịch bản AI
          </Link>
        </div>
      </div>

      {/* 2. PostV — Bài đăng MXH 60fps (Xanh Dương / Indigo) */}
      <div className="group relative flex flex-col justify-between overflow-hidden rounded-card border border-line bg-card p-5 shadow-card transition-all duration-180 hover:-translate-y-0.5 hover:border-engine-postv/50 hover:shadow-[0_14px_36px_-8px_rgba(59,130,246,0.22)]">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r from-[#3B82F6] to-[#6366F1]"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-[#3B82F6]/10 blur-2xl transition-opacity group-hover:opacity-100"
        />

        <div>
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-pill bg-engine-postv-soft px-3 py-1 text-tiny font-extrabold text-on-engine-postv-soft">
              <SmartphoneIcon size={14} />
              PostV · 60fps
            </span>
            <span className="text-tiny font-semibold text-muted">Threads / Reddit</span>
          </div>

          <h2 className="mt-3 text-title font-extrabold text-text">Bài đăng MXH & Bình luận</h2>
          <p className="mt-1 text-small text-muted">
            Dán link bài viết, tự tải ảnh/GIF, ghép nền gameplay 60fps & meme phông xanh.
          </p>

          {/* Minh họa UI thu nhỏ: Thẻ bài MXH + nền gameplay */}
          <div
            aria-hidden="true"
            className="mt-4 flex items-center gap-3 rounded-inner border border-engine-postv/20 bg-engine-postv-soft/50 p-3"
          >
            <div className="relative flex h-16 w-12 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-b from-indigo-500 to-sky-400 p-1 shadow-sm">
              <div className="w-full rounded bg-white/95 p-1 shadow">
                <div className="h-1.5 w-6 rounded bg-indigo-500" />
                <div className="mt-1 h-1 w-full rounded bg-slate-200" />
                <div className="mt-0.5 h-1 w-4/5 rounded bg-slate-200" />
              </div>
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-engine-postv" />
                <span className="text-[11px] font-bold text-text">Bóc link & chọn bình luận</span>
              </div>
              <div className="h-2 w-4/5 rounded bg-engine-postv/15" />
              <div className="h-2 w-3/5 rounded bg-engine-postv/10" />
            </div>
          </div>
        </div>

        <div className="mt-5">
          <Link to="/postv" className="ui-btn ui-btn-postv w-full justify-center">
            <SmartphoneIcon size={16} />
            Dán link Threads / Reddit
          </Link>
        </div>
      </div>

      {/* 3. Chatting — Hội thoại Tin nhắn (Ngọc lục bảo / Teal) */}
      <div className="group relative flex flex-col justify-between overflow-hidden rounded-card border border-line bg-card p-5 shadow-card transition-all duration-180 hover:-translate-y-0.5 hover:border-engine-chatting/50 hover:shadow-[0_14px_36px_-8px_rgba(16,185,129,0.22)]">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r from-[#10B981] to-[#059669]"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-[#10B981]/10 blur-2xl transition-opacity group-hover:opacity-100"
        />

        <div>
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-pill bg-engine-chatting-soft px-3 py-1 text-tiny font-extrabold text-on-engine-chatting-soft">
              <MessagesSquareIcon size={14} />
              Chatting · 60fps
            </span>
            <span className="text-tiny font-semibold text-muted">Messenger / Zalo</span>
          </div>

          <h2 className="mt-3 text-title font-extrabold text-text">Hội thoại Tin nhắn Kịch tính</h2>
          <p className="mt-1 text-small text-muted">
            Tạo đoạn chat 2–4 nhân vật, âm thanh pop/typing, sticker cảm xúc & giọng VieNeu.
          </p>

          {/* Minh họa UI thu nhỏ: Bong bóng chat Messenger / Zalo */}
          <div
            aria-hidden="true"
            className="mt-4 flex items-center gap-3 rounded-inner border border-engine-chatting/20 bg-engine-chatting-soft/50 p-3"
          >
            <div className="flex h-16 w-12 shrink-0 flex-col justify-center gap-1.5 rounded-lg bg-slate-900/90 p-1.5 shadow-sm">
              <div className="h-2.5 w-7 self-start rounded-full bg-slate-600" />
              <div className="h-2.5 w-8 self-end rounded-full bg-emerald-400" />
              <div className="h-2.5 w-6 self-start rounded-full bg-slate-600" />
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-engine-chatting" />
                <span className="text-[11px] font-bold text-text">4 pha SSE + 10 tag sticker</span>
              </div>
              <div className="h-2 w-4/5 rounded bg-engine-chatting/15" />
              <div className="h-2 w-3/5 rounded bg-engine-chatting/10" />
            </div>
          </div>
        </div>

        <div className="mt-5">
          <Link to="/chatting" className="ui-btn ui-btn-chatting w-full justify-center">
            <MessagesSquareIcon size={16} />
            Tạo đoạn chat 2 người
          </Link>
        </div>
      </div>

      {/* 4. StickV — Video Người que 2D/2.5D (Cam Nghệ / Vàng Hổ Phách #F59E0B) */}
      <div className="group relative flex flex-col justify-between overflow-hidden rounded-card border border-line bg-card p-5 shadow-card transition-all duration-180 hover:-translate-y-0.5 hover:border-engine-stickv/50 hover:shadow-[0_14px_36px_-8px_rgba(245,158,11,0.24)]">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r from-[#F59E0B] to-[#D97706]"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-[#F59E0B]/10 blur-2xl transition-opacity group-hover:opacity-100"
        />

        <div>
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-pill bg-engine-stickv-soft px-3 py-1 text-tiny font-extrabold text-on-engine-stickv-soft">
              <SparklesIcon size={14} />
              StickV · 9:16 & 16:9
            </span>
            <span className="text-tiny font-semibold text-muted">Audio Anchoring</span>
          </div>

          <h2 className="mt-3 text-title font-extrabold text-text">Video Người que 2D/2.5D</h2>
          <p className="mt-1 text-small text-muted">
            Kể chuyện & giải thích kiến thức 1–15 phút với nhân vật người que, bảng minh họa & SFX.
          </p>

          <div
            aria-hidden="true"
            className="mt-4 flex items-center gap-3 rounded-inner border border-engine-stickv/20 bg-engine-stickv-soft/50 p-3"
          >
            <div className="flex h-16 w-12 shrink-0 flex-col items-center justify-between rounded-lg border border-amber-300/70 bg-[#FAF7F0] p-1.5 shadow-sm">
              <div className="h-3 w-full rounded bg-amber-400/30" />
              <div className="h-6 w-6 rounded-full border-2 border-slate-800 bg-white" />
              <div className="h-1.5 w-6 rounded bg-red-500" />
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-engine-stickv" />
                <span className="text-[11px] font-bold text-text">
                  8 dáng chuẩn + Bảng thông minh
                </span>
              </div>
              <div className="h-2 w-4/5 rounded bg-engine-stickv/20" />
              <div className="h-2 w-3/5 rounded bg-engine-stickv/10" />
            </div>
          </div>
        </div>

        <div className="mt-5">
          <Link
            to="/stickv"
            className="ui-btn w-full justify-center bg-engine-stickv text-white hover:bg-[#d97706]"
          >
            <SparklesIcon size={16} />
            Tạo video Người que
          </Link>
        </div>
      </div>
    </section>
  );
}
