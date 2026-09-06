interface Window {
  desktopAgent?: {
    getBackendStatus: () => Promise<{
      online: boolean
      service?: string
      status?: string
      detail?: string
    }>
  }
}
