import { useState } from 'react';
import { useProjectEditor } from '../../hooks/projectEditor';
import { vi } from '../../i18n/vi';
import { parseHashtags } from '../../utils/hashtags';
import { ThumbnailEditor } from '../ThumbnailEditor';
import { Drawer } from '../ui/Drawer';
import { Input } from '../ui/Field';

const T = vi.compose.publishPanel;

function PostFields() {
  const editor = useProjectEditor();
  const { publish } = editor.project;
  const [draft, setDraft] = useState(() => publish.hashtags.map((h) => `#${h}`).join(' '));
  return (
    <section className="space-y-3">
      <h2 className="text-h2 font-bold">{T.postTitle}</h2>
      <Input
        label={T.hook}
        placeholder={T.hookPlaceholder}
        value={publish.hook}
        onChange={(e) =>
          editor.update((p) => ({ ...p, publish: { ...p.publish, hook: e.target.value } }))
        }
      />
      <Input
        label={T.hashtags}
        placeholder={T.hashtagsPlaceholder}
        hint={<p className="mt-1 text-tiny text-muted">{T.hashtagsHelp}</p>}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
          const hashtags = parseHashtags(e.target.value);
          editor.update((p) => ({ ...p, publish: { ...p.publish, hashtags } }));
        }}
        onBlur={() => setDraft(publish.hashtags.map((h) => `#${h}`).join(' '))}
      />
    </section>
  );
}

/** Ngăn kéo "Bìa & đăng" từ thanh đầu: ảnh bìa (ThumbnailEditor) và câu mở đầu + hashtag. */
export function PublishDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Drawer open={open} onClose={onClose} title={T.title} wide>
      <div className="space-y-8">
        <ThumbnailEditor />
        <PostFields />
      </div>
    </Drawer>
  );
}
