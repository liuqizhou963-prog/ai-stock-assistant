const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('desktopAgent', {
  getBackendStatus: () => ipcRenderer.invoke('backend:status'),
  onBackendExited: (callback) => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('backend:exited', listener)
    return () => ipcRenderer.removeListener('backend:exited', listener)
  },
})
