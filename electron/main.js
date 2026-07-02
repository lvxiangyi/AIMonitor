const { app, BrowserWindow, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const net = require('net');
const fs = require('fs');
const http = require('http');

let mainWindow;
let backendProcess = null;
let BACKEND_PORT = 8899;

const repoRoot = path.join(__dirname, '..');
const dataEnv = process.env.AIMONITOR_DATA_ENV || 'prod';
const logsDir = path.join(repoRoot, 'data', dataEnv, 'logs');
const appLogPath = path.join(logsDir, 'app.log');

function writeAppLog(message) {
  try {
    fs.mkdirSync(logsDir, { recursive: true });
    fs.appendFileSync(appLogPath, `[${new Date().toISOString()}] ${message}\n`, 'utf8');
  } catch (e) {
    console.error('[app] Failed to write app log:', e);
  }
}

function logInfo(message) {
  console.log(message);
  writeAppLog(message);
}

function logWarn(message) {
  console.warn(message);
  writeAppLog(message);
}

function logError(message, error) {
  console.error(message, error || '');
  writeAppLog(error ? `${message} ${error.stack || error}` : message);
}

function getFreePort(startPort = 8899) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.listen(startPort, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
    server.on('error', () => {
      resolve(getFreePort(startPort + 1));
    });
  });
}

function startBackend(port) {
  const backendDir = path.join(__dirname, '..', 'backend');
  const venvPython = path.join(backendDir, '.venv', 'Scripts', 'python.exe');
  let pythonCommand = venvPython;

  if (!fs.existsSync(venvPython)) {
    pythonCommand = 'python';
    logWarn(`[backend] ${venvPython} was not found. Falling back to global "python". Run setup_windows.bat to create the project virtual environment.`);
  }

  backendProcess = spawn(
    pythonCommand,
    ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)],
    {
      cwd: backendDir,
      shell: false,
      env: {
        ...process.env,
        FOCUSGUARD_PORT: String(port),
        AIMONITOR_DATA_ENV: process.env.AIMONITOR_DATA_ENV || 'prod',
      },
    },
  );

  backendProcess.stdout.on('data', (data) => {
    const message = `[backend] ${data}`;
    process.stdout.write(message);
    writeAppLog(message.trimEnd());
  });

  backendProcess.stderr.on('data', (data) => {
    const message = `[backend] ${data}`;
    process.stderr.write(message);
    writeAppLog(message.trimEnd());
  });

  backendProcess.on('error', (err) => {
    logError('[backend] Failed to start:', err);
  });

  backendProcess.on('exit', (code, signal) => {
    logInfo(`[backend] exited with code=${code} signal=${signal}`);
    backendProcess = null;
  });
}

function renderMissingFrontendPage() {
  const message = [
    'Production frontend build not found.',
    '',
    'Run:',
    '  cd frontend',
    '  npm install',
    '  npm run build',
  ].join('\n');

  dialog.showErrorBox('FocusGuard frontend is not built', message);
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>FocusGuard setup needed</title>
        <style>
          body { margin: 0; font-family: Segoe UI, sans-serif; background: #111827; color: #f9fafb; display: grid; min-height: 100vh; place-items: center; }
          main { max-width: 680px; padding: 32px; }
          h1 { margin-top: 0; }
          pre { background: #030712; padding: 16px; border-radius: 8px; overflow: auto; }
        </style>
      </head>
      <body>
        <main>
          <h1>Frontend build not found</h1>
          <p>Run these commands from the repository root, then start the app again:</p>
          <pre>cd frontend
npm install
npm run build</pre>
        </main>
      </body>
    </html>
  `)}`);
}

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 820,
    height: 750,
    title: 'FocusGuard Agent',
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    backgroundColor: '#0f0f23',
    autoHideMenuBar: true,
  });

  const apiBase = `http://127.0.0.1:${port}`;
  const frontendPath = path.join(__dirname, '..', 'frontend', 'dist', 'index.html');

  if (process.env.AIMONITOR_ELECTRON_DEV === '1') {
    const devUrl = process.env.AIMONITOR_FRONTEND_DEV_URL || 'http://127.0.0.1:3000';
    mainWindow.loadURL(`${devUrl}?apiBase=${encodeURIComponent(apiBase)}`);
  } else if (fs.existsSync(frontendPath)) {
    mainWindow.loadFile(frontendPath, {
      query: { apiBase },
    });
  } else {
    renderMissingFrontendPage();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function waitForBackend(port, retries = 30) {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    const check = () => {
      attempts++;
      const req = http.get(`http://127.0.0.1:${port}/`, () => {
        resolve();
      });
      req.on('error', () => {
        if (attempts >= retries) {
          reject(new Error('Backend failed to start'));
        } else {
          setTimeout(check, 500);
        }
      });
      req.end();
    };

    check();
  });
}

function stopBackend() {
  if (!backendProcess) {
    return;
  }

  const pid = backendProcess.pid;
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(pid), '/t', '/f'], { windowsHide: true });
  } else {
    backendProcess.kill('SIGTERM');
  }
  backendProcess = null;
}

app.whenReady().then(async () => {
  if (process.env.AIMONITOR_SKIP_BACKEND === '1') {
    BACKEND_PORT = Number(process.env.AIMONITOR_BACKEND_PORT || 8000);
    logInfo(`[app] Using existing backend on port ${BACKEND_PORT}`);
  } else {
    BACKEND_PORT = await getFreePort(8899);
    logInfo(`[app] Using port ${BACKEND_PORT}`);

    startBackend(BACKEND_PORT);
  }

  try {
    await waitForBackend(BACKEND_PORT);
    logInfo('[app] Backend is ready');
  } catch (e) {
    logError('[app] Backend failed to start, launching window anyway:', e);
  }

  createWindow(BACKEND_PORT);
});

app.on('window-all-closed', () => {
  stopBackend();
  app.quit();
});

app.on('before-quit', () => {
  stopBackend();
});
