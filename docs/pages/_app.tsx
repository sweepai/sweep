import type { AppProps } from "next/app";
import "../styles/global.css";


function MyApp({ Component, pageProps }: AppProps) {
  return (
    <main style={{ backgroundColor: "#0E0E1C" }}>
      <Component {...pageProps} />
    </main>
  );
}

export default MyApp;
