import { getProfileByUserId } from "@/db/queries/profiles-queries";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

export default async function TodoPage() {
  const { userId } = await auth();

  if (!userId) {
    return redirect("/login");
  }

  const profile = await getProfileByUserId(userId);

  if (!profile) {
    return redirect("/signup");
  }

  return (
    <div>
      <h1>Chat</h1>
    </div>
  );
}