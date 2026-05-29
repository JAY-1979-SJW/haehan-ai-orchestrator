const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  submitLicense: (key) => ipcRenderer.send("license-submit", key),
  onLicenseError: (cb) => ipcRenderer.on("license-error", cb),
  connectYouTube: () => ipcRenderer.send("youtube-connect"),
  onYouTubeStatus: (cb) => ipcRenderer.on("youtube-status", (_, s) => cb(s)),
});
