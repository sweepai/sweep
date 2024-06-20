import App from '@/components/App'
import authOptions from '@/lib/authOptions'
import { getServerSession } from 'next-auth'

export default async function Home() {
  const session = await getServerSession(authOptions)
  return <App session={session} />
}
