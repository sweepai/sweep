const withNextra = require('nextra')({
  theme: 'nextra-theme-docs',
  themeConfig: './theme.config.tsx',
  defaultShowCopyCode: true,
  latex: true,
  // images: {
  //   remotePatterns: [
  //     {
  //       protocol: 'https',
  //       hostname: 'raw.githubusercontent.com',
  //       port: '80',
  //       pathname: '**',
  //     },
  //   ],
  // }
})

module.exports = withNextra()
