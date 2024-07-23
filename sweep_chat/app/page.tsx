import App from '@/components/App'
import authOptions from '@/lib/authOptions'
import { getServerSession } from 'next-auth'

export default async function Home({ searchParams }: { searchParams: { repo_name?: string; query?: string } }) {
  const session = await getServerSession(authOptions)
  const { repo_name, query } = searchParams
  return <App session={session} initialRepoName={repo_name} initialQuery={query} />
}