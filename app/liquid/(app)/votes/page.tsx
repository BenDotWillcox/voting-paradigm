import type { Metadata } from "next";
import { Suspense } from "react";
import { VotesList } from "@/components/liquid/votes-list";

export const metadata: Metadata = { title: "Incoming votes · Liquid democracy" };

export default function LiquidVotesPage() {
  // VotesList reads the query string, which needs a Suspense boundary above it.
  return (
    <Suspense fallback={null}>
      <VotesList />
    </Suspense>
  );
}
