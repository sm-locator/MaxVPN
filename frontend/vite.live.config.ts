import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const port = Number(process.env.MAXVPN_LIVE_API_PORT)
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('A disposable API port is required')

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 4179, strictPort: true, proxy: {
    '/api': { target: `http://127.0.0.1:${port}`, changeOrigin: true },
  } },
})
