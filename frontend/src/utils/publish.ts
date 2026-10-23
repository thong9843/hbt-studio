export interface PublishBlock {
  /** Tên khối, ví dụ "TikTok" hoặc "YouTube Shorts". */
  name: string;
  body: string;
}

/** Tách `publish.txt` thành các khối theo dòng tiêu đề dạng `[Tên khối]`. */
export function splitPublishBlocks(text: string): PublishBlock[] {
  const blocks: PublishBlock[] = [];
  let current: { name: string; lines: string[] } | null = null;
  for (const line of text.split(/\r?\n/)) {
    const m = /^\[(.+)\]\s*$/.exec(line);
    if (m) {
      if (current) blocks.push({ name: current.name, body: current.lines.join('\n').trim() });
      current = { name: m[1], lines: [] };
    } else if (current) {
      current.lines.push(line);
    }
  }
  if (current) blocks.push({ name: current.name, body: current.lines.join('\n').trim() });
  return blocks;
}
