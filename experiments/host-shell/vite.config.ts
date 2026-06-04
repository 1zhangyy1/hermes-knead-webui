import { defineConfig } from 'vite'
import type { ProxyOptions } from 'vite'
import react from '@vitejs/plugin-react'

const stripBrowserOrigin: NonNullable<ProxyOptions['configure']> = (proxy) => {
  proxy.on('proxyReq', (proxyReq) => {
    proxyReq.removeHeader('origin')
  })
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/hermes-dashboard': {
        target: process.env.HERMES_DASHBOARD_URL || 'http://127.0.0.1:9119',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/hermes-dashboard/, ''),
      },
      '/hermes': {
        target: process.env.HERMES_API_URL || 'http://127.0.0.1:8642',
        changeOrigin: true,
        configure: stripBrowserOrigin,
        rewrite: (path) => path.replace(/^\/hermes/, ''),
      },
    },
  },
})
