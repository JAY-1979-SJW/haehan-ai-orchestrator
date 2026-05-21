import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  base: './',   // file:// 로드 시 상대 경로 사용 (Electron)
  build: {
    outDir: '../ui_dist',
    emptyOutDir: true,
  },
})
