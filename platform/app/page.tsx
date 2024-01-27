"use client"

import DashboardContext from "@/components/dashboard/DashboardContext";


export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-12">
      {/* <DashboardDisplay></DashboardDisplay> */}
      <DashboardContext></DashboardContext>
    </main>
  );
}
