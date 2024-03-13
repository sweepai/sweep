import type { AppProps } from "next/app";
import "../styles/global.css";


function MyApp({ Component, pageProps }: AppProps) {
    return (
        // <main className="bg-[#020817]" style={{backgroundColor: "#020817"}}>
        // <main className="bg-[#020817]" style={{backgroundColor: "#0d0a19"}}>
        // <main className="bg-[#020817]" style={{backgroundColor: "#161625"}}>
        <main className="bg-[#020817]" style={{backgroundColor: "#13131A"}}>
          <Component {...pageProps} />
        </main>
    );
}

export default MyApp;
