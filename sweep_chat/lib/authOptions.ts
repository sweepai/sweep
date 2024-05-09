import { AuthOptions } from "next-auth";
import GitHubProvider from "next-auth/providers/github"

const authOptions: AuthOptions = {
    providers: [
        GitHubProvider({
            clientId: process.env.GITHUB_ID || "",
            clientSecret: process.env.GITHUB_SECRET || "",
        }),
    ],
    secret: process.env.NEXTAUTH_SECRET,
    debug: true,
    callbacks: {
        async session({ session, token }: any) {
            const { sub } = token;
            const response = await fetch(`https://api.github.com/user/${sub}`)
            const data = await response.json()
            const { login } = data;
            session.user.username = login; 
            return session;
        },
        async signIn({ user, account, profile }: any) {
            if (account.provider === "github") {
                user.username = profile.login; 
            }
            return true;
        },
        async jwt({ token, account }) {
            if (account) {
              token.accessToken = account.access_token;
            }
            return token;
        },
        async session({ session, token }) {
            session.accessToken = token.accessToken;
            return session;
        },
    },
}

export default authOptions