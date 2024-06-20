import App from '@/components/App'
import authOptions from '@/lib/authOptions'
import { getServerSession } from 'next-auth'

export default async function Home({
  params,
}: {
  params: { messageId: string }
}) {
  const session = await getServerSession(authOptions)
  return <App session={session} defaultMessageId={params.messageId} />
}
