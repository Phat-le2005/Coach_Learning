// One frontend supervisor. Only the frontend is restarted when interface addresses
// change, so Next's exact allowedDevOrigins refreshes without losing backend grants.
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const port = process.argv[process.argv.indexOf('--port') + 1] || '3000';
if (!/^\d+$/.test(port) || +port < 1 || +port > 65535) throw Error('Invalid port');
process.env.COACH_LAN_MODE = '1';
process.env.COACH_LAN_FRONTEND_PORT = port;
function hosts() {
  return Object.entries(os.networkInterfaces())
    .filter(([name]) => !/^(?:lo|veth|br-|virbr|docker|tun|tap|wg)|loopback|vethernet|wsl|docker|virtual|vmware|vbox|tailscale|tunnel|vpn/i.test(name))
    .flatMap(([, rows]) => (rows || []).filter(a => a.family === 'IPv4' && !a.internal
      && /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(a.address)).map(a => a.address)).sort();
}
let signature = hosts().join('|'), child, stopping = false, restarting = false;
function start() {
  console.log(`[LAN] Laptop: http://localhost:${port}; devices: ${hosts().map(h => `http://${h}:${port}`).join(', ') || 'waiting for network'}`);
  child = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'dev', '--hostname', '0.0.0.0', '--port', port],
    { cwd: path.join(root, 'frontend'), env: process.env, stdio: 'inherit', windowsHide: true });
  child.once('exit', code => {
    if (stopping) process.exit(0);
    if (restarting) { restarting = false; start(); }
    else process.exit(code ?? 1);
  });
}
const timer = setInterval(() => {
  const next = hosts().join('|');
  if (signature === next || restarting || stopping) return;
  signature = next; restarting = true;
  console.log('[LAN] Network changed; refreshing frontend addresses. Backend and saved ink are retained.');
  stopChild();
}, 5000);
function stopChild() {
  if (!child?.pid) return;
  // Terminate only our own child tree (Next has an additional worker on Windows).
  if (process.platform === 'win32') spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
  else child.kill('SIGTERM');
}
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { stopping = true; clearInterval(timer); stopChild(); });
start();
