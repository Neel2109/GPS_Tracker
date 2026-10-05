import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const environmentNames = ['.venv312', '.venv'];
const pythonPath = environmentNames
  .map(environmentName => process.platform === 'win32'
    ? join(projectRoot, environmentName, 'Scripts', 'python.exe')
    : join(projectRoot, environmentName, 'bin', 'python'))
  .find(existsSync);

if (!pythonPath) {
  console.error('Project Python environment not found.');
  console.error('Create it with Python 3.12 and install backend requirements first:');
  console.error('  py -3.12 -m venv .venv312');
  console.error('  .\\.venv312\\Scripts\\python.exe -m pip install -r requirements.txt');
  process.exit(1);
}

const backend = spawn(pythonPath, ['run.py'], {
  cwd: projectRoot,
  stdio: 'inherit',
});
const frontend = spawn(process.execPath, ['node_modules/vite/bin/vite.js'], {
  cwd: projectRoot,
  stdio: 'inherit',
});

let stopping = false;

function stopServices(exitCode = 0) {
  if (stopping) return;
  stopping = true;
  if (backend.exitCode === null) backend.kill();
  if (frontend.exitCode === null) frontend.kill();
  process.exitCode = exitCode;
}

backend.once('error', error => {
  console.error('Could not start the TrackGuard backend:', error.message);
  stopServices(1);
});
frontend.once('error', error => {
  console.error('Could not start the Vite frontend:', error.message);
  stopServices(1);
});
backend.once('exit', code => {
  if (!stopping) {
    console.error(`TrackGuard backend exited${code === null ? '' : ` with code ${code}`}.`);
    stopServices(code || 1);
  }
});
frontend.once('exit', code => {
  if (!stopping) {
    console.error(`Vite frontend exited${code === null ? '' : ` with code ${code}`}.`);
    stopServices(code || 1);
  }
});

process.once('SIGINT', () => stopServices(0));
process.once('SIGTERM', () => stopServices(0));
