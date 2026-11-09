import { useQuery } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../../api/endpoints';
import type { ChatDoc, ChatCharacter, ChatMessage } from '../../api/types';
import { vi } from '../../i18n/vi';
import { Button } from '../../components/ui/Button';
import { ArrowLeftIcon, PlusIcon, TrashIcon } from '../../components/icons';

const STICKER_TAGS = [
  'soc',
  'cuoi',
  'khoc',
  'gian',
  'ngai',
  'yeu',
  'nghi',
  'can',
  'bat_luc',
  'ok',
] as const;

const VOICE_OPTIONS = ['Adam bựa', 'Trúc Ly', 'Thiện Minh', 'Mai Anh', 'Hải Đăng', 'Thùy Dung'];

export function ChattingEditor() {
  const { slug } = useParams<{ slug: string }>();
  const [selectedMsgIndex, setSelectedMsgIndex] = useState(0);
  const [isSaving, setIsSaving] = useState(false);
  const [isRendering, setIsRendering] = useState(false);
  const [renderJobId, setRenderJobId] = useState<string | null>(null);
  const [renderProgress, setRenderProgress] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const { data, refetch } = useQuery({
    queryKey: ['chattingProject', slug],
    queryFn: () => (slug ? api.getChattingProject(slug) : null),
    enabled: !!slug,
  });

  const doc = data?.doc;

  // Lắng nghe tiến độ dựng SSE
  useEffect(() => {
    if (!renderJobId) return;
    const es = new EventSource(`/api/render/events/${renderJobId}`);

    es.addEventListener('progress', (e) => {
      try {
        const d = JSON.parse(e.data);
        setRenderProgress(d.percent ?? d.progress ?? 0);
      } catch {
        // bỏ qua gói tin lỗi định dạng
      }
    });

    es.addEventListener('end', (e) => {
      try {
        const d = JSON.parse(e.data);
        es.close();
        setIsRendering(false);
        setRenderJobId(null);
        setRenderProgress(null);
        if (d.status === 'done') {
          refetch();
          setNotice('Dựng video hoàn tất!');
        } else {
          setNotice(`Lỗi dựng video: ${d.error || 'Thất bại'}`);
        }
      } catch {
        es.close();
      }
    });

    es.onerror = () => {
      es.close();
      setIsRendering(false);
    };

    return () => {
      es.close();
    };
  }, [renderJobId, refetch]);

  if (!doc) {
    return (
      <div className="flex h-64 items-center justify-center text-muted">{vi.common.loading}</div>
    );
  }

  const activeMsg = doc.messages[selectedMsgIndex] || doc.messages[0];

  const saveDoc = async (updatedDoc: ChatDoc) => {
    if (!slug) return;
    setIsSaving(true);
    try {
      await api.updateChattingProject(slug, updatedDoc);
      refetch();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Lỗi lưu: ${msg}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleTextChange = (text: string) => {
    const newMsgs = [...doc.messages];
    newMsgs[selectedMsgIndex] = { ...activeMsg, text };
    saveDoc({ ...doc, messages: newMsgs });
  };

  const handleSenderChange = (from_: string) => {
    const newMsgs = [...doc.messages];
    newMsgs[selectedMsgIndex] = { ...activeMsg, from: from_ };
    saveDoc({ ...doc, messages: newMsgs });
  };

  const handleStickerChange = (sticker: string | null) => {
    const newMsgs = [...doc.messages];
    newMsgs[selectedMsgIndex] = { ...activeMsg, sticker };
    saveDoc({ ...doc, messages: newMsgs });
  };

  const handleAddMessage = () => {
    const newMsg: ChatMessage = {
      id: `m${doc.messages.length + 1}`,
      from: doc.characters[0].id,
      text: 'Tin nhắn mới',
      sticker: null,
    };
    const newMsgs = [...doc.messages, newMsg];
    saveDoc({ ...doc, messages: newMsgs });
    setSelectedMsgIndex(newMsgs.length - 1);
  };

  const handleDeleteMessage = (idx: number) => {
    if (doc.messages.length <= 8) {
      alert('Đoạn chat cần tối thiểu 8 tin nhắn.');
      return;
    }
    const newMsgs = doc.messages.filter((_: ChatMessage, i: number) => i !== idx);
    saveDoc({ ...doc, messages: newMsgs });
    setSelectedMsgIndex(Math.max(0, idx - 1));
  };

  const handleRegenAI = async () => {
    if (!slug) return;
    if (!window.confirm('Viết lại kịch bản bằng AI? Nội dung chỉnh sửa hiện tại sẽ được thay thế.'))
      return;
    setIsSaving(true);
    try {
      await api.regenChattingProject(slug);
      refetch();
      setNotice('Đã viết lại kịch bản!');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Lỗi AI: ${msg}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleRender = async (preview: boolean) => {
    if (!slug) return;
    setIsRendering(true);
    setNotice(null);
    try {
      const res = await api.renderChattingProject(slug, preview);
      setRenderJobId(res.job_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Không thể bắt đầu dựng: ${msg}`);
      setIsRendering(false);
    }
  };

  const handleAvatarUpload = async (charId: string, file: File) => {
    if (!slug) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`/api/chatting/${slug}/avatar/${charId}`, {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        refetch();
      } else {
        alert('Tải ảnh đại diện thất bại');
      }
    } catch (err) {
      console.error(err);
    }
  };

  const latestRender = data?.renders?.[0];
  const videoUrl = latestRender
    ? `/api/chatting/${slug}/renders/${latestRender.video_file}`
    : data?.preview_url;

  return (
    <div className="flex h-[calc(100vh-64px)] overflow-hidden">
      {/* CỘT TRÁI (280px): Nhân vật + Danh sách tin nhắn */}
      <aside className="flex w-[280px] shrink-0 flex-col border-r border-line bg-card p-4 overflow-y-auto">
        <Link
          to="/chatting"
          className="mb-4 inline-flex items-center gap-1.5 text-tiny font-bold text-muted hover:text-text"
        >
          <ArrowLeftIcon size={16} /> Quay lại danh sách
        </Link>

        <h2 className="text-small font-extrabold text-text">{vi.chatting.characters}</h2>
        <div className="mt-3 space-y-3">
          {doc.characters.map((char: ChatCharacter) => (
            <div key={char.id} className="rounded-xl border border-line bg-soft-2 p-2.5">
              <div className="flex items-center gap-2.5">
                <label className="relative flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-full border border-line bg-soft">
                  {char.avatar ? (
                    <img
                      src={`/api/chatting/${slug}/${char.avatar}?t=${Date.now()}`}
                      alt={char.name}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <span className="font-bold text-text">{char.name ? char.name[0] : 'U'}</span>
                  )}
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files?.[0]) {
                        handleAvatarUpload(char.id, e.target.files[0]);
                      }
                    }}
                  />
                </label>
                <div className="flex-1 min-w-0">
                  <p className="truncate text-tiny font-bold text-text">
                    {char.name} ({char.side === 'right' ? 'Phải/Tôi' : 'Trái'})
                  </p>
                  <select
                    value={char.voice_id || 'Adam bựa'}
                    onChange={(e) => {
                      const newChars = doc.characters.map((c: ChatCharacter) =>
                        c.id === char.id ? { ...c, voice_id: e.target.value } : c,
                      );
                      saveDoc({ ...doc, characters: newChars });
                    }}
                    className="mt-0.5 w-full rounded border border-line bg-card py-0.5 text-[11px] font-medium outline-none"
                  >
                    {VOICE_OPTIONS.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 flex items-center justify-between border-t border-line pt-4">
          <h2 className="text-small font-extrabold text-text">
            {vi.chatting.messages} ({doc.messages.length})
          </h2>
          <button
            type="button"
            onClick={handleAddMessage}
            className="rounded p-1 text-muted hover:bg-soft hover:text-text"
            title={vi.chatting.addMsg}
          >
            <PlusIcon size={16} />
          </button>
        </div>

        <div className="mt-2 flex-1 space-y-1.5 overflow-y-auto">
          {doc.messages.map((m: ChatMessage, idx: number) => {
            const isSelected = idx === selectedMsgIndex;
            const sender = doc.characters.find((c: ChatCharacter) => c.id === m.from);
            return (
              <div
                key={idx}
                onClick={() => setSelectedMsgIndex(idx)}
                className={`flex cursor-pointer items-center justify-between rounded-xl px-2.5 py-2 text-tiny transition-colors ${
                  isSelected
                    ? 'bg-primary text-on-primary font-bold'
                    : 'bg-soft/40 hover:bg-soft text-text'
                }`}
              >
                <div className="flex-1 truncate mr-2">
                  <span className="opacity-70">{idx + 1}. </span>
                  <span className="font-semibold">{sender?.name}: </span>
                  <span>{m.text}</span>
                </div>
                {m.sticker && (
                  <span className="rounded bg-black/10 px-1.5 py-0.5 text-[10px] uppercase">
                    {m.sticker}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      {/* CỘT GIỮA: Sửa tin đang chọn */}
      <main className="flex flex-1 flex-col p-6 overflow-y-auto">
        <div className="flex items-center justify-between border-b border-line pb-4">
          <div>
            <h1 className="text-xl font-bold">{doc.title}</h1>
            <p className="text-tiny text-muted">
              {vi.chatting.platform}: {doc.platform} · {doc.messages.length} tin nhắn
            </p>
          </div>
          <div className="flex items-center gap-3">
            {isSaving && <span className="text-tiny text-muted">{vi.chatting.saving}</span>}
            <Button tone="soft" size="sm" onClick={handleRegenAI}>
              {vi.chatting.regenBtn}
            </Button>
          </div>
        </div>

        {notice && (
          <div className="mt-4 rounded-xl bg-tint-yel/60 p-3 text-tiny font-bold text-text">
            {notice}
          </div>
        )}

        <div className="mt-6 rounded-2xl border border-line bg-card p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-body font-extrabold">Sửa tin nhắn số {selectedMsgIndex + 1}</h2>
            <Button
              tone="soft"
              size="sm"
              onClick={() => handleDeleteMessage(selectedMsgIndex)}
              className="text-danger hover:bg-danger/10"
            >
              <TrashIcon size={14} /> {vi.chatting.delMsg}
            </Button>
          </div>

          {/* Chọn người gửi */}
          <div className="mt-4">
            <label className="text-tiny font-semibold text-muted">{vi.chatting.sender}:</label>
            <div className="mt-1.5 flex flex-wrap gap-2">
              {doc.characters.map((c: ChatCharacter) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => handleSenderChange(c.id)}
                  className={`rounded-full px-4 py-1.5 text-tiny font-bold transition-colors ${
                    activeMsg.from === c.id
                      ? 'bg-primary text-on-primary'
                      : 'bg-soft text-text hover:bg-soft/80'
                  }`}
                >
                  {c.name} ({c.side === 'right' ? 'Tôi' : 'Bạn'})
                </button>
              ))}
            </div>
          </div>

          {/* Nội dung tin nhắn */}
          <div className="mt-4">
            <div className="flex items-center justify-between">
              <label className="text-tiny font-semibold text-muted">Lời nhắn:</label>
              <span
                className={`text-tiny font-bold tabular-nums ${
                  activeMsg.text.length > 120 ? 'text-danger' : 'text-muted'
                }`}
              >
                {activeMsg.text.length}/120
              </span>
            </div>
            <textarea
              value={activeMsg.text}
              onChange={(e) => handleTextChange(e.target.value)}
              rows={3}
              maxLength={120}
              className="mt-1.5 w-full resize-none rounded-xl border border-line bg-soft-2 p-3 text-body font-medium outline-none focus:border-text focus:ring-2 focus:ring-accent"
            />
          </div>

          {/* Chọn Sticker */}
          <div className="mt-4">
            <label className="text-tiny font-semibold text-muted">{vi.chatting.sticker}:</label>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => handleStickerChange(null)}
                className={`rounded-full px-3 py-1 text-tiny font-bold transition-colors ${
                  !activeMsg.sticker
                    ? 'bg-primary text-on-primary'
                    : 'bg-soft text-text hover:bg-soft/80'
                }`}
              >
                {vi.chatting.noSticker}
              </button>
              {STICKER_TAGS.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => handleStickerChange(tag)}
                  className={`rounded-full px-3 py-1 text-tiny font-bold uppercase transition-colors ${
                    activeMsg.sticker === tag
                      ? 'bg-accent text-primary'
                      : 'bg-soft text-text hover:bg-soft/80'
                  }`}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>
        </div>
      </main>

      {/* CỘT PHẢI (360px): Xem trước 9:16 + Nút Xuất */}
      <aside className="flex w-[360px] shrink-0 flex-col items-center border-l border-line bg-card p-6">
        <h2 className="text-small font-extrabold text-text">Xem trước</h2>

        {/* Khung xem trước 9:16 */}
        <div className="relative mt-3 flex aspect-[9/16] w-full max-w-[260px] items-center justify-center overflow-hidden rounded-[28px] border border-line bg-black shadow-md">
          {videoUrl ? (
            <video
              key={videoUrl}
              src={videoUrl}
              controls
              autoPlay={false}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="text-center p-4 text-tiny text-muted">
              Chưa có video xem nhanh. Bấm "Xem nhanh" để dựng.
            </div>
          )}
        </div>

        {/* Nút hành động */}
        <div className="mt-6 flex w-full flex-col gap-2.5">
          {isRendering && (
            <div className="mb-2 text-center text-tiny font-bold text-accent">
              Đang dựng video... {renderProgress ? `${renderProgress}%` : ''}
            </div>
          )}

          <Button
            tone="soft"
            size="md"
            disabled={isRendering}
            onClick={() => handleRender(true)}
            className="w-full font-bold"
          >
            {vi.chatting.exportFast}
          </Button>

          <Button
            tone="accent"
            size="lg"
            disabled={isRendering}
            onClick={() => handleRender(false)}
            className="w-full rounded-full font-extrabold shadow-md"
          >
            {vi.chatting.exportFinal}
          </Button>

          {videoUrl && (
            <a
              href={videoUrl}
              download
              className="mt-2 text-center text-tiny font-bold text-muted hover:text-text"
            >
              {vi.chatting.download}
            </a>
          )}
        </div>
      </aside>
    </div>
  );
}
