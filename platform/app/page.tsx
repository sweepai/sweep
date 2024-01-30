"use client";

// import DashboardContext from "@/components/dashboard/DashboardContext";
import DashboardDisplay from "../components/dashboard/DashboardDisplay";
import React from "react";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-around p-4">
      <DashboardDisplay></DashboardDisplay>
      {/* <DashboardContext></DashboardContext> */}
    </main>
  );
}
