#!/usr/bin/env node
// Optional local QA authentication backend; never provisions or seeds a database.
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const { spawn, execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const runtime = path.join(root, '.tmp/tri-ocr-v2-runtime');
const sessionFile = path.join(runtime, 'qa-backend-session.json');
async function main() {
  if (process.argv[2] === 'stop') {
    if (!fs.existsSync(sessionFile)) return console.log('No managed QA backend');
    const session = JSON.parse(fs.readFileSync(sessionFile));
    if (session.root !== root) throw Error('QA backend session root mismatch');
    if (process.platform === 'win32') {
      const command = execFileSync('powershell.exe', ['-NoProfile', '-Command',
        `(Get-CimInstance Win32_Process -Filter "ProcessId = ${Number(session.pid)}").CommandLine`],
      { encoding: 'utf8', windowsHide: true });
      if (command.trim()) {
        if (!command.includes('uvicorn') || !command.includes(path.join(root, 'backend')) || !command.includes(session.port.toString())) throw Error('PID identity mismatch; preserved');
        execFileSync('taskkill.exe', ['/PID', String(session.pid), '/T', '/F'], { stdio: 'pipe', windowsHide: true });
      }
    } else process.kill(-session.pid, 'SIGTERM');
    fs.renameSync(sessionFile, path.join(runtime, `qa-backend-stopped-${Date.now()}.json`));
    return console.log('Managed QA backend stopped; database preserved');
  }
  const helperModule = path.join(root, 'frontend/.test-build-run/e2e/qa-harness-safety.js');
  if (!fs.existsSync(helperModule)) throw Error('Run npm run test:compile in frontend first');
  const { validateQaHarnessEnv } = require(helperModule);
  const cfg = validateQaHarnessEnv(process.env, path.join(root, '.tmp/tri-ocr-e2e/.qa-e2e.env'));
  if (cfg.appEnv !== 'test') throw Error('Only APP_ENV=test is allowed');
  const port = 8000;
  await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', () => reject(Error('Port 8000 is busy; existing service preserved')));
    server.listen(port, '127.0.0.1', () => server.close(resolve));
  });
  const python = process.env.PYTHON_EXE || [path.join(root, 'backend/.venv/Scripts/python.exe'),
    path.resolve(root, '../Coach_Learning/backend/.venv/Scripts/python.exe'),
    path.join(root, 'backend/.venv/bin/python')].find(fs.existsSync);
  if (!python) throw Error('Set PYTHON_EXE to the existing application backend Python');
  const env = { ...process.env, APP_ENV: 'test', DATABASE_NAME: cfg.qaDatabaseName,
    QA_E2E_DATABASE_NAME: cfg.qaDatabaseName, PYTHONDONTWRITEBYTECODE: '1' };
  let safety;
  try {
    safety = JSON.parse(execFileSync(python, [path.join(root, 'frontend/e2e/qa_db_helper.py'), 'verify-safety'],
      { cwd: path.join(root, 'backend'), env, encoding: 'utf8', timeout: 60000, stdio: ['ignore', 'pipe', 'pipe'] }));
  } catch { throw Error('Dedicated QA database safety check failed; no server started, no database writes performed'); }
  if (!safety.ok || safety.connected_database_name !== cfg.qaDatabaseName) throw Error('QA database mismatch');
  fs.mkdirSync(runtime, { recursive: true });
  const log = fs.openSync(path.join(runtime, 'qa-backend.log'), 'a');
  const child = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--app-dir', path.join(root, 'backend'), '--host', '127.0.0.1', '--port', String(port)],
    { cwd: path.join(root, 'backend'), env, windowsHide: true, detached: true, stdio: ['ignore', log, log] });
  fs.closeSync(log); child.unref();
  fs.writeFileSync(sessionFile, JSON.stringify({ root, pid: child.pid, port, database: cfg.qaDatabaseName,
    startedAt: new Date().toISOString() }, null, 2));
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      if ((await fetch(`http://127.0.0.1:${port}/openapi.json`, { signal: AbortSignal.timeout(2000) })).ok)
        return console.log(JSON.stringify({ status: 'QA_BACKEND_READY', port, database: cfg.qaDatabaseName }));
    } catch { /* wait for import/startup */ }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw Error('QA backend startup timeout; inspect private runtime/qa-backend.log and use qa-backend.cjs stop');
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
