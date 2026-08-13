const path = require('node:path')
const { app, BrowserWindow, ipcMain } = require('electron')
const { spawn } = require('node:child_process')

const backendPort = 8000
const backendDirectory = path.resolve(__dirname, '../../backend')
const backendPython = path.join(
  backendDirectory,
  '.venv',
  'Scripts',
  'python.exe',
)
let backendProcess = null

function startBackend() {
  backendProcess = spawn(
    backendPython,
    [
      '-m',
      'uvicorn',
      'app.main:app',
      '--host',
      '127.0.0.1',
      '--port',
      String(backendPort),
    ],
    {
      cwd: backendDirectory,
      windowsHide: true,
      stdio: 'ignore',
    },
  )

  backendProcess.on('error', (error) => {
    console.error('Python 后端启动失败:', error.message)
  })
}

ipcMain.handle('backend:status', async () => {
  try {
    const response = await fetch(`http://127.0.0.1:${backendPort}/health`)

    if (!response.ok) {
      return {
        online: false,
        detail: `后端返回 HTTP ${response.status}`,
      }
    }

    return {
      online: true,
      ...(await response.json()),
    }
  } catch {
    return {
      online: false,
      detail: '后端尚未启动或不可访问',
    }
  }
})

function createWindow() {
  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    webPreferences: {
    preload: path.join(__dirname, 'preload.cjs'),
    contextIsolation: true,
    nodeIntegration: false,
    },
  })

  window.loadURL('http://localhost:5174/')
}

app.whenReady().then(() => {
  startBackend()
  createWindow()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill()
  }
})
