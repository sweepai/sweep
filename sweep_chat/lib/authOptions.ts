import { AuthOptions } from "next-auth";
import GitHubProvider from "next-auth/providers/github"

const authOptions: AuthOptions = {
    providers: [
        GitHubProvider({
            clientId: process.env.GITHUB_ID || "",
            clientSecret: process.env.GITHUB_SECRET || "",
        }),
    ],
    debug: process.env.NODE_ENV === "development",
    callbacks: {
        async session({ session, token }: any) {
            const { sub } = token;
            const response = await fetch(`https://api.github.com/user/${sub}`)
            const data = await response.json()
            const { login } = data;
            session.user.username = login; 
            session.accessToken = token.accessToken;
            return session;
        },
        async signIn({ user, account, profile }: any) {
            if (account.provider === "github") {
                user.username = profile.login; 
                user.expiry = new Date(Date.now() + 1000 * 60 * 60 * 8); // 8 hours
            }
            return true;
        },
        async jwt({ token, account }) {
            if (account) {
              token.accessToken = account.access_token;
            }
            return token;
        },
    },
}

export default authOptions