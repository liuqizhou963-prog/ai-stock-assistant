const path = require('node:path')
const fs = require('node:fs')
const net = require('node:net')
const { app, BrowserWindow, dialog, ipcMain } = require('electron')
const { spawn } = require('node:child_process')

const backendDirectory = app.isPackaged
  ? path.join(process.resourcesPath, 'backend')
  : path.resolve(__dirname, '../../backend')
const backendPython = path.join(backendDirectory, '.venv', 'Scripts', 'python.exe')
const packagedNewsServiceDirectory = app.isPackaged
  ? path.join(process.resourcesPath, 'news-service')
  : path.resolve(__dirname, '../../news-service')
const newsPython = path.join(packagedNewsServiceDirectory, '.venv', 'Scripts', 'python.exe')
const rendererDevUrl = process.env.DESKTOP_AGENT_RENDERER_URL || 'http://localhost:5173/'
let backendPort = null
let backendProcess = null
let newsPort = null
let newsProcess = null
let mainWindow = null
let quitting = false

function canListen(port) {
  return new Promise((resolve) => {
    const probe = net.createServer()
    probe.once('error', () => resolve(false))
    probe.once('listening', () => probe.close(() => resolve(true)))
    probe.listen(port, '127.0.0.1')
  })
}

async function findAvailablePort(startPort = 8000) {
  for (let port = startPort; port < startPort + 100; port += 1) {
    if (await canListen(port)) return port
  }
  throw new Error(`无法在 ${startPort}-${startPort + 99} 范围内找到可用端口`)
}

function backendHealthUrl() {
  return `http://127.0.0.1:${backendPort}/health`
}

function newsHealthUrl() {
  return `http://127.0.0.1:${newsPort}/index.html`
}

function synchronizeNewsServiceRuntime() {
  if (!app.isPackaged) return packagedNewsServiceDirectory

  const runtimeDirectory = path.join(app.getPath('userData'), 'news-service-runtime')
  fs.mkdirSync(runtimeDirectory, { recursive: true })
  const preservedEntries = new Set(['data.js', 'llm.config.json', 'sources.json', 'state'])
  for (const entry of fs.readdirSync(packagedNewsServiceDirectory)) {
    if (['.venv', '__pycache__', '.pytest_cache'].includes(entry)) continue
    if (preservedEntries.has(entry)) {
      const target = path.join(runtimeDirectory, entry)
      if (!fs.existsSync(target)) {
        fs.cpSync(path.join(packagedNewsServiceDirectory, entry), target, { recursive: true })
      }
      continue
    }
    fs.cpSync(path.join(packagedNewsServiceDirectory, entry), path.join(runtimeDirectory, entry), { recursive: true, force: true })
  }
  fs.mkdirSync(path.join(runtimeDirectory, 'state'), { recursive: true })
  return runtimeDirectory
}

function startBackend() {
  if (!fs.existsSync(backendPython)) {
    throw new Error(`未找到后端 Python 环境：${backendPython}。请先运行 npm run prepare-release。`)
  }
  backendProcess = spawn(
    backendPython,
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(backendPort)],
    {
      cwd: backendDirectory,
      windowsHide: true,
      stdio: 'ignore',
      env: {
        ...process.env,
        DESKTOP_AGENT_BACKEND_PORT: String(backendPort),
        DESKTOP_AGENT_ROOT: app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '../../..'),
        DESKTOP_AGENT_CONFIG_DIR: app.isPackaged ? path.join(process.resourcesPath, 'config') : path.resolve(__dirname, '../../../config'),
        DESKTOP_AGENT_STATE_DIR: app.isPackaged ? path.join(app.getPath('userData'), 'state') : path.resolve(__dirname, '../../../state'),
      },
    },
  )
  backendProcess.on('error', (error) => console.error('Python 后端启动失败:', error.message))
  backendProcess.on('exit', (code, signal) => {
    backendProcess = null
    if (!quitting && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('backend:exited', { code, signal })
    }
  })
}

function startNewsService(newsServiceDirectory) {
  if (!fs.existsSync(newsPython)) {
    throw new Error(`未找到资讯服务 Python 环境：${newsPython}。请先运行 npm run prepare-release。`)
  }
  if (!fs.existsSync(path.join(newsServiceDirectory, 'server.py'))) {
    throw new Error(`未找到资讯服务：${newsServiceDirectory}`)
  }
  newsProcess = spawn(
    newsPython,
    [path.join(newsServiceDirectory, 'server.py'), String(newsPort)],
    {
      cwd: newsServiceDirectory,
      windowsHide: true,
      stdio: 'ignore',
      env: {
        ...process.env,
        PYTHONUTF8: '1',
      },
    },
  )
  newsProcess.on('error', (error) => console.error('资讯服务启动失败:', error.message))
  newsProcess.on('exit', (code, signal) => {
    newsProcess = null
    if (!quitting && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('news:exited', { code, signal })
    }
  })
}

async function waitForBackend(timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const response = await fetch(backendHealthUrl(), { signal: AbortSignal.timeout(1200) })
      if (response.ok) return
    } catch {
      // The process may need several seconds to import dependencies and bind.
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error('Python 后端在规定时间内未通过健康检查')
}

async function waitForNewsService(timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const response = await fetch(newsHealthUrl(), { signal: AbortSignal.timeout(1200) })
      if (response.ok) return
    } catch {
      // The local service may need several seconds to import dependencies and bind.
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error('资讯服务在规定时间内未能启动')
}

async function backendStatus() {
  if (!backendPort) return { online: false, detail: '后端尚未分配端口' }
  try {
    const response = await fetch(backendHealthUrl(), { signal: AbortSignal.timeout(1200) })
    if (!response.ok) return { online: false, detail: `后端返回 HTTP ${response.status}`, port: backendPort }
    return { online: true, port: backendPort, ...(await response.json()) }
  } catch {
    return { online: false, port: backendPort, detail: '后端尚未启动或不可访问' }
  }
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  mainWindow.on('closed', () => { mainWindow = null })

  if (app.isPackaged) {
    await mainWindow.loadFile(path.join(process.resourcesPath, 'renderer', 'index.html'), {
      query: { backendPort: String(backendPort), newsPort: String(newsPort) },
    })
  } else {
    const separator = rendererDevUrl.includes('?') ? '&' : '?'
    await mainWindow.loadURL(`${rendererDevUrl}${separator}backendPort=${backendPort}&newsPort=${newsPort}`)
  }
}

async function boot() {
  backendPort = await findAvailablePort(Number(process.env.DESKTOP_AGENT_BACKEND_PORT) || 8000)
  newsPort = await findAvailablePort(Number(process.env.DESKTOP_AGENT_NEWS_PORT) || 8888)
  startBackend()
  startNewsService(synchronizeNewsServiceRuntime())
  await waitForBackend()
  await waitForNewsService()
  await createWindow()
}

ipcMain.handle('backend:status', () => backendStatus())

app.whenReady().then(() => boot()).catch((error) => {
  console.error(error)
  dialog.showErrorBox('桌面 Agent 启动失败', error instanceof Error ? error.message : String(error))
  app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && backendPort) void createWindow()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  quitting = true
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill()
    backendProcess = null
  }
  if (newsProcess && !newsProcess.killed) {
    newsProcess.kill()
    newsProcess = null
  }
})
