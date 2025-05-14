import { AuthOptions } from 'next-auth'
import GitHubProvider from 'next-auth/providers/github'
import { refreshToken } from '@octokit/oauth-methods'
import { Octokit } from 'octokit'
import { cache } from 'react'

const getUserData = cache(async (accessToken: string, sub: string) => {
  const octokit = new Octokit({
    auth: accessToken,
  })
  const response = await octokit.request('GET /user/{id}', {
    id: sub,
  })
  return response.data
})

const authOptions: AuthOptions = {
  providers: [
    GitHubProvider({
      clientId: process.env.GITHUB_ID || '',
      clientSecret: process.env.GITHUB_SECRET || '',
    }),
  ],
  debug: process.env.NODE_ENV === 'development',
  callbacks: {
    async session({ session, token }: any) {
      const { sub } = token
      const data = await getUserData(token.accessToken, sub)
      session.user = {
        name: data.name,
        username: data.login,
        image: data.avatar_url,
        accessToken: token.accessToken,
        refreshToken: token.refreshToken,
        expires_at: token.expires_at,
      }
      return session
    },
    async signIn({ user, account, profile }: any) {
      if (account.provider === 'github') {
        user.username = profile.login
      }
      return true
    },
    async jwt({ token, account }) {
      const hasExpired = token.expires_at
        ? Date.now() >= (token.expires_at as number) * 1000
        : false
      if (account && !hasExpired) {
        return {
          ...token,
          accessToken: account?.access_token,
          refreshToken: account?.refresh_token,
          expires_at: account?.expires_at,
        }
      }
      if (hasExpired) {
        const { data, authentication } = await refreshToken({
          clientType: 'github-app',
          clientId: process.env.GITHUB_ID || '',
          clientSecret: process.env.GITHUB_SECRET || '',
          refreshToken: token.refreshToken as string,
        })
        token.accessToken = data.access_token
        token.refreshToken = data.refresh_token
        token.expires_at = data.expires_in
        return {
          ...token,
          accessToken: data.access_token,
          refreshToken: data.refresh_token,
          expires_at: Date.now() + 1000 * 60 * 60 * 8,
        }
      }
      return token
    },
  },
}

declare module 'next-auth' {
  interface Session {
    user: {
      email: string
      name: string
      username: string
      image: string
      accessToken: string
      refreshToken: string
      expires_at: number
    }
  }
}

export default authOptions
