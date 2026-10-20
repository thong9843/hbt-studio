// Chạy Python của backend: ưu tiên backend/.venv, không có thì dùng python trên PATH (CI).
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

const venv = join('backend', '.venv');
const candidates = [join(venv, 'Scripts', 'python.exe'), join(venv, 'bin', 'python')];
const python = candidates.find((p) => existsSync(p)) ?? 'python';

const result = spawnSync(python, process.argv.slice(2), { stdio: 'inherit' });
if (result.error) {
  console.error(`Không chạy được ${python}: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
