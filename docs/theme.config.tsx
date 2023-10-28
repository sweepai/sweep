import React from 'react'
import { DocsThemeConfig } from 'nextra-theme-docs'

const config: DocsThemeConfig = {
  logo: <img width={120} src="https://docs.sweep.dev/banner.png" style={{borderRadius: 5}}/>,
  head: (
    <>
      <link rel="icon" type="image/png" href="./favicon.png" />
      <link rel="icon" type="image/png" sizes="16x16" href="/final-sweep-wizard_16x16.png" />
      <link rel="icon" type="image/png" sizes="32x32" href="/final-sweep-wizard_32x32.png" />
      <link rel="icon" type="image/png" sizes="48x48" href="/final-sweep-wizard_48x48.png" />
      <link rel="icon" type="image/png" sizes="64x64" href="/final-sweep-wizard_64x64.png" />
      <link rel="icon" type="image/png" sizes="128x128" href="/final-sweep-wizard_128x128.png" />
      <link rel="icon" type="image/png" sizes="256x256" href="/final-sweep-wizard_256x256.png" />
      <meta property="og:title" content="Sweep AI Documentation" />
      <meta property="og:description" content="The official documentation for Sweep AI." />
      <meta property="og:image" content="/og_image.png" />
      <script defer src="/_vercel/insights/script.js" />
      <script>{`
        window.intercomSettings = {
          api_base: "https://api-iam.intercom.io",
          app_id: "ce8fl00z",
          action_color: "#6b46c1",
          background_color: "#342867",
        };
        (function(){var w=window;var ic=w.Intercom;if(typeof ic==="function"){ic('reattach_activator');ic('update',w.intercomSettings);}else{var d=document;var i=function(){i.c(arguments);};i.q=[];i.c=function(args){i.q.push(args);};w.Intercom=i;var l=function(){var s=d.createElement('script');s.type='text/javascript';s.async=true;s.src='https://widget.intercom.io/widget/ce8fl00z';var x=d.getElementsByTagName('script')[0];x.parentNode.insertBefore(s,x);};if(document.readyState==='complete'){l();}else if(w.attachEvent){w.attachEvent('onload',l);}else{w.addEventListener('load',l,false);}}})();
      `}</script>
    </>
  ),
  project: {
    link: 'https://github.com/sweepai/sweep',
  },
  chat: {
    link: 'https://discord.gg/sweep',
  },
  docsRepositoryBase: 'https://github.com/sweepai/sweep/tree/main/docs',
  darkMode: false,
  nextThemes: {
    forcedTheme: 'dark',
    defaultTheme: 'dark',
  },
  primaryHue: 220,
  footer: {
    text: `Sweep AI © ${new Date().getFullYear()}`
  },
  useNextSeoProps() {
    return {
      titleTemplate: '%s'
    }
  }
}

export default config
