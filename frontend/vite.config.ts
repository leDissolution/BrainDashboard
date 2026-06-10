import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const allowedHosts = parseAllowedHosts(env.BRAINDASHBOARD_FRONTEND_ALLOWED_HOSTS)
  const apiProxyTarget = env.BRAINDASHBOARD_API_PROXY_TARGET || 'http://127.0.0.1:9500'

  return {
    plugins: [react()],
    server: {
      allowedHosts,
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})

function parseAllowedHosts(value: string | undefined): string[] {
  if (!value) {
    return ['brainsrv']
  }

  return value
    .split(',')
    .map((host) => host.trim())
    .filter(Boolean)
}
