/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  // 移除 output: 'export' 以支持开发模式的热重载
  // output: 'export',
  trailingSlash: true,
  // 使用相对路径，让Nginx代理处理
  env: {
    HOSTNAME: 'localhost',
    NEXT_PUBLIC_API_URL: '/api',
    NEXT_PUBLIC_WS_URL: 'ws://localhost:18000/ws/status',
  },
  // 配置CSP以允许WebSocket连接（宽松配置）
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: http: https: ws: wss:; connect-src 'self' 'unsafe-inline' 'unsafe-eval' http: https: ws: wss: data: blob: localhost:* 127.0.0.1:* d4e493f5176147d1b141b4fc2b948384.cloud.lanyun.net:* ws://localhost:* ws://127.0.0.1:*; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: http: https:; font-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
          }
        ]
      }
    ]
  },
  // 允许跨域请求
  allowedDevOrigins: [
    'localhost',
    '127.0.0.1',
    'd4e493f5176147d1b141b4fc2b948384.cloud.lanyun.net'
  ],
  // 配置WebSocket代理
  webpack: (config, { dev, isServer }) => {
    if (dev && !isServer) {
      // 修复热重载WebSocket连接
      config.watchOptions = {
        ...config.watchOptions,
        poll: 1000,
        aggregateTimeout: 300,
      }
      
      // 强制热重载使用localhost
      config.devServer = {
        ...config.devServer,
        host: 'localhost',
        port: 3000,
        // 禁用热重载WebSocket
        hot: false,
        liveReload: false,
      }
    }
    return config
  },
  // 移除rewrites，使用Nginx代理
}

export default nextConfig
