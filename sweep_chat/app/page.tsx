import App from '@/components/App';
import { getServerSession } from 'next-auth';

export default async function Home() {
  const session = await getServerSession();
  return (
    <App session={session} />
  );
}