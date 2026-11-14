import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Browser regressions intercept every API request. Never proxy to a backend.
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 4178, strictPort: true },
})
