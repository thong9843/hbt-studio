import { useEffect, useState, type ReactNode } from 'react';
import { MoreIcon, MoonIcon, PlayIcon, PlusIcon, SunIcon } from '../components/icons';
import { Badge } from '../components/ui/Badge';
import { Button, type ButtonTone } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { Dialog } from '../components/ui/Dialog';
import { Drawer } from '../components/ui/Drawer';
import { IconButton } from '../components/ui/IconButton';
import { Input, Textarea } from '../components/ui/Field';
import { Menu } from '../components/ui/Menu';
import { Progress } from '../components/ui/Progress';
import { Skeleton } from '../components/ui/Skeleton';
import { Switch } from '../components/ui/Switch';
import { useToast } from '../hooks/toast';
import { vi } from '../i18n/vi';

type Theme = 'system' | 'light' | 'dark';

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-4">
      <h2 className="text-h2">{title}</h2>
      <div className="ui-card ui-card-pad flex flex-wrap items-start gap-4">{children}</div>
    </section>
  );
}

/**
 * Trang xem bộ thành phần nền. Chỉ có khi chạy `npm run dev` (route đăng ký dưới
 * `import.meta.env.DEV`), không vào bản build. Hover, nhấn, focus là trạng thái thật: tự thao tác.
 */
export default function UiKit() {
  const t = vi.ui.kit;
  const toast = useToast();
  const [theme, setTheme] = useState<Theme>('system');
  const [on, setOn] = useState(true);
  const [chip, setChip] = useState('b');
  const [text, setText] = useState('HAY BIẾT TUỐT');
  const [voice, setVoice] = useState('Muỗi đốt bạn vì mùi cơ thể.');
  const [dialog, setDialog] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [pct, setPct] = useState(40);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
    return () => root.removeAttribute('data-theme');
  }, [theme]);

  const tones: ButtonTone[] = ['ink', 'accent', 'brand', 'soft', 'danger', 'ghost'];

  return (
    <main className="mx-auto max-w-[1100px] space-y-8 px-6 py-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1>{t.title}</h1>
        <div role="group" aria-label={t.theme} className="flex gap-2">
          <Chip selected={theme === 'system'} onClick={() => setTheme('system')}>
            {t.themeSystem}
          </Chip>
          <Chip selected={theme === 'light'} onClick={() => setTheme('light')}>
            <SunIcon size={16} />
            {t.themeLight}
          </Chip>
          <Chip selected={theme === 'dark'} onClick={() => setTheme('dark')}>
            <MoonIcon size={16} />
            {t.themeDark}
          </Chip>
        </div>
      </div>

      <Section title={t.buttons}>
        {tones.map((tone) => (
          <div key={tone} className="flex flex-col items-start gap-2">
            <Button tone={tone} icon={<PlusIcon size={18} />}>
              {t.sample}
            </Button>
            <Button tone={tone} disabled reason={t.reason}>
              {t.disabled}
            </Button>
            <Button tone={tone} busy>
              {t.running}
            </Button>
          </div>
        ))}
        <div className="flex flex-col items-start gap-2">
          <Button size="lg" tone="accent">
            {t.sample} 54
          </Button>
          <Button size="sm" tone="soft">
            {t.sample} 36
          </Button>
          <IconButton label={t.sample}>
            <PlayIcon />
          </IconButton>
          <IconButton label={t.disabled} disabled>
            <PlayIcon />
          </IconButton>
        </div>
      </Section>

      <Section title={t.chips}>
        {['a', 'b', 'c'].map((k) => (
          <Chip key={k} selected={chip === k} onClick={() => setChip(k)}>
            {t.sample} {k.toUpperCase()}
          </Chip>
        ))}
        <Chip small>{t.sample}</Chip>
        <Chip disabled>{t.disabled}</Chip>
        <Switch checked={on} onChange={setOn} label={t.sample} />
        <Switch checked={false} onChange={() => {}} label={t.disabled} disabled />
      </Section>

      <Section title={t.cards}>
        <Card className="w-56">{t.sample}</Card>
        <Card interactive className="w-56" onClick={() => toast.info(t.toastText)}>
          {t.sample}
        </Card>
        <div className="flex flex-wrap gap-2">
          <Badge>{t.sample}</Badge>
          <Badge tone="red">{t.sample}</Badge>
          <Badge tone="yel">{t.sample}</Badge>
          <Badge tone="ok">{t.sample}</Badge>
          <Badge tone="danger">{t.sample}</Badge>
        </div>
      </Section>

      <Section title={t.fields}>
        <div className="w-72">
          <Input
            label={t.inputLabel}
            value={text}
            limit={12}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="w-72">
          <Input label={t.inputLabel} defaultValue="HBT" error={t.inputError} />
        </div>
        <div className="w-72">
          <Input label={t.disabled} defaultValue="HBT" disabled />
        </div>
        <div className="w-72">
          <Textarea
            label={t.textareaLabel}
            value={voice}
            limit={40}
            onChange={(e) => setVoice(e.target.value)}
          />
        </div>
      </Section>

      <Section title={t.feedback}>
        <div className="w-72 space-y-3">
          <Progress value={pct} label={t.sample} />
          <Chip small onClick={() => setPct((v) => (v >= 100 ? 0 : v + 20))}>
            {pct}%
          </Chip>
        </div>
        <div className="w-72 space-y-2">
          <Skeleton height={20} />
          <Skeleton height={20} width="60%" />
        </div>
      </Section>

      <Section title={t.overlays}>
        <Button tone="soft" onClick={() => setDialog(true)}>
          {t.openDialog}
        </Button>
        <Button tone="soft" onClick={() => setDrawer(true)}>
          {t.openDrawer}
        </Button>
        <Button tone="soft" onClick={() => toast.info(t.toastText)}>
          {t.showToast}
        </Button>
        <Button tone="soft" onClick={() => toast.info(t.toastUndo, { undo: () => {} })}>
          {t.showUndo}
        </Button>
        <Button tone="soft" onClick={() => toast.error(new Error('demo'))}>
          {t.showError}
        </Button>
        <Menu
          label={t.menuLabel}
          icon={<MoreIcon />}
          items={[
            { key: 'a', label: t.itemOne, onSelect: () => toast.info(t.itemOne) },
            { key: 'b', label: t.itemTwo, danger: true, onSelect: () => toast.info(t.itemTwo) },
            { key: 'c', label: t.disabled, disabled: true, reason: t.reason, onSelect: () => {} },
          ]}
        />
      </Section>

      <Dialog
        open={dialog}
        onClose={() => setDialog(false)}
        title={t.dialogTitle}
        footer={
          <>
            <Button tone="soft" onClick={() => setDialog(false)}>
              {vi.common.cancel}
            </Button>
            <Button onClick={() => setDialog(false)}>{vi.common.save}</Button>
          </>
        }
      >
        <p className="text-muted">{t.dialogBody}</p>
        <div className="mt-4">
          <Input label={t.inputLabel} defaultValue="HBT" />
        </div>
      </Dialog>
      <Drawer open={drawer} onClose={() => setDrawer(false)} title={t.drawerTitle}>
        <p className="text-muted">{t.dialogBody}</p>
      </Drawer>
    </main>
  );
}
