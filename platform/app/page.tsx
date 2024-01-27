"use client"

import DashboardDisplay from "../components/dashboard/DashboardDisplay";


export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-12">
      <DashboardDisplay></DashboardDisplay>
    </main>
  );
}
