"use client"

import posthog from "../lib/posthog";
import DashboardDisplay from "../components/dashboard/DashboardDisplay";
import { PostHogProvider} from 'posthog-js/react'
import React from "react";

export default function Home() {
  return (
    <PostHogProvider client={posthog}>
      <main className="flex min-h-screen flex-col items-center justify-center p-4">
        <DashboardDisplay />
      </main>
    </PostHogProvider>
  );
}
