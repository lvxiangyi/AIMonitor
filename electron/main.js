const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const net = require('net');
const fs = require('fs');

let mainWindow;
let backendProcess = null;
let BACKEND_PORT = 8899;

// Find a free port
function findFreePort(startPort = 8899) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(startPort, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
    server.on('error', () => {
      // Try next port
      resolve(findFreePort(startPort + 1));
    });
  });
}

function startBackend(port) {
  const backendDir = path.join(__dirname, '..', 'backend');

  backendProcess = spawn('python', ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)], {
    cwd: backendDir,
    shell: true,
    env: { ...process.env, FOCUSGUARD_PORT: String(port) },
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.log(`[backend] ${data}`);
  });

  backendProcess.on('error', (err) => {
    console.error('[backend] Failed to start:', err);
  });
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

  // Load frontend with port info injected
  const frontendPath = path.join(__dirname, '..', 'frontend', 'dist', 'index.html');
  mainWindow.loadFile(frontendPath);

  // After page loads, inject the correct backend port
  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow.webContents.executeJavaScript(`window.__BACKEND_PORT__ = ${port};`);
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function waitForBackend(port, retries = 30) {
  return new Promise((resolve, reject) => {
    const http = require('http');
    let attempts = 0;

    const check = () => {
      attempts++;
      const req = http.get(`http://127.0.0.1:${port}/`, (res) => {
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

app.whenReady().then(async () => {
  // Find free port and start
  BACKEND_PORT = await findFreePort(8899);
  console.log(`[app] Using port ${BACKEND_PORT}`);

  // Write port to a file so frontend api.js can read it at build time
  // But for runtime, we'll use a simpler approach: write a config file the frontend reads
  const portFile = path.join(__dirname, '..', 'frontend', 'dist', 'port.json');
  fs.writeFileSync(portFile, JSON.stringify({ port: BACKEND_PORT }));

  startBackend(BACKEND_PORT);

  try {
    await waitForBackend(BACKEND_PORT);
    console.log('[app] Backend is ready');
  } catch (e) {
    console.error('[app] Backend failed to start, launching anyway...');
  }

  createWindow(BACKEND_PORT);
});

app.on('window-all-closed', () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
  app.quit();
});

app.on('before-quit', () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
