import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchText } from '../../api/client';
import { vi } from '../../i18n/vi';
import { splitPublishBlocks } from '../../utils/publish';
import { ErrorNote } from '../ErrorNote';
import { CopyIcon } from '../icons';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';

const X = vi.export;

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState('copied');
      setTimeout(() => setState('idle'), 2000);
    } catch {
      setState('failed');
    }
  };
  return (
    <span className="inline-flex items-center gap-2">
      <Button
        tone="soft"
        size="sm"
        aria-label={label}
        icon={<CopyIcon size={18} />}
        onClick={() => void copy()}
      >
        {state === 'copied' ? X.publish.copied : X.publish.copy}
      </Button>
      {state === 'failed' && (
        <span role="alert" className="text-small text-danger">
          {X.publish.copyFailed}
        </span>
      )}
    </span>
  );
}

/** Nội dung đăng: các khối (TikTok / YouTube Shorts / …) lấy từ publish.txt, mỗi khối có Sao chép. */
export function PublishCard({ url }: { url: string }) {
  const text = useQuery({
    queryKey: ['publish', url],
    queryFn: () => fetchText(url),
    retry: false,
  });
  const blocks = splitPublishBlocks(text.data ?? '');
  return (
    <section aria-label={X.publish.title} className="space-y-3">
      <h2 className="text-h2 font-bold">{X.publish.title}</h2>
      <ErrorNote error={text.error} />
      {blocks.length === 0 && text.data !== undefined && (
        <textarea
          readOnly
          rows={8}
          aria-label={X.publish.title}
          className="ui-input font-mono"
          value={text.data}
        />
      )}
      <ul className="space-y-3">
        {blocks.map((b) => (
          <Card as="li" key={b.name} className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-tiny font-semibold uppercase text-muted">{b.name}</h3>
              <CopyButton text={b.body} label={X.publish.copyBlock(b.name)} />
            </div>
            <pre className="whitespace-pre-wrap break-words font-mono text-small">{b.body}</pre>
          </Card>
        ))}
      </ul>
      {text.data && blocks.length > 1 && <CopyButton text={text.data} label={X.publish.copyAll} />}
    </section>
  );
}
