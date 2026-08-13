const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('desktopAgent', {
  getBackendStatus: () => ipcRenderer.invoke('backend:status'),
})
