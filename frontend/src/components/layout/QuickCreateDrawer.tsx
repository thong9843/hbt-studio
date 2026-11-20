import { useNavigate } from 'react-router-dom';
import { useNewProject } from '../../hooks/newProject';
import { MessagesSquareIcon, PlusIcon, SmartphoneIcon, SparklesIcon, ZapIcon } from '../icons';
import { Drawer } from '../ui/Drawer';

interface QuickCreateDrawerProps {
  open: boolean;
  onClose: () => void;
}

const ENGINES = [
  {
    id: 'core',
    to: '/core',
    title: 'HBT Core — Video Kiến thức',
    desc: '1-Click AI hoặc dán JSON 10–12 phân đoạn, tự khớp giọng VieNeu & phụ đề.',
    cta: 'Tạo kịch bản AI',
    icon: ZapIcon,
    accent: 'border-engine-core/30 bg-engine-core-soft/60 hover:border-engine-core',
    badge: 'bg-engine-core text-white',
  },
  {
    id: 'postv',
    to: '/postv',
    title: 'PostV — Bài đăng MXH 60fps',
    desc: 'Dán link Threads / Reddit, tự tải ảnh/GIF, nền gameplay 60fps & meme.',
    cta: 'Dán link Threads / Reddit',
    icon: SmartphoneIcon,
    accent: 'border-engine-postv/30 bg-engine-postv-soft/60 hover:border-engine-postv',
    badge: 'bg-engine-postv text-white',
  },
  {
    id: 'chatting',
    to: '/chatting',
    title: 'Chatting — Hội thoại Tin nhắn',
    desc: 'Tạo đoạn chat Messenger / Zalo 2–4 nhân vật, sticker cảm xúc & giọng đọc.',
    cta: 'Tạo đoạn chat 2 người',
    icon: MessagesSquareIcon,
    accent: 'border-engine-chatting/30 bg-engine-chatting-soft/60 hover:border-engine-chatting',
    badge: 'bg-engine-chatting text-white',
  },
  {
    id: 'stickv',
    to: '/stickv',
    title: 'StickV — Người que 2D/2.5D',
    desc: 'Video giải thích kiến thức 9:16 & 16:9 với nhân vật người que, bảng minh họa & SFX.',
    cta: 'Tạo video Người que',
    icon: SparklesIcon,
    accent: 'border-engine-stickv/30 bg-engine-stickv-soft/60 hover:border-engine-stickv',
    badge: 'bg-engine-stickv text-white',
  },
] as const;

export function QuickCreateDrawer({ open, onClose }: QuickCreateDrawerProps) {
  const navigate = useNavigate();
  const { open: openNewProject } = useNewProject();

  return (
    <Drawer open={open} onClose={onClose} title="Tạo nhanh video mới">
      <div className="space-y-4">
        <p className="text-small text-muted">
          Chọn động cơ phù hợp với định dạng nội dung bạn muốn sản xuất ngay bây giờ.
        </p>

        <div className="space-y-3">
          {ENGINES.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  onClose();
                  navigate(item.to);
                }}
                className={`group flex w-full items-start gap-3.5 rounded-card border p-4 text-left transition-all duration-180 hover:-translate-y-0.5 hover:shadow-card ${item.accent}`}
              >
                <span
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-inner shadow-sm ${item.badge}`}
                >
                  <Icon size={20} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-body font-bold text-text">{item.title}</div>
                  <p className="mt-0.5 text-small text-text-2">{item.desc}</p>
                  <span className="mt-2 inline-flex items-center gap-1 text-tiny font-bold text-text underline-offset-4 group-hover:underline">
                    {item.cta} →
                  </span>
                </div>
              </button>
            );
          })}
        </div>

        <div className="border-t border-line pt-4">
          <button
            type="button"
            onClick={() => {
              onClose();
              openNewProject();
            }}
            className="ui-btn ui-btn-soft w-full justify-center"
          >
            <PlusIcon size={16} />
            Tạo dự án thủ công (HBT / PostV)
          </button>
        </div>
      </div>
    </Drawer>
  );
}
