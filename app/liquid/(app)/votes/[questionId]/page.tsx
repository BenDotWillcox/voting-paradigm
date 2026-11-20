import type { Metadata } from "next";
import { VoteDetail } from "@/components/liquid/vote-detail";

export const metadata: Metadata = { title: "Vote · Liquid democracy" };

export default async function LiquidVotePage({
  params,
}: {
  params: Promise<{ questionId: string }>;
}) {
  const { questionId } = await params;
  return <VoteDetail questionId={questionId} />;
}
