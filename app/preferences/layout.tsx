import { PreferencesNav } from "@/components/preferences/preferences-nav";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

export default async function PreferencesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { userId } = await auth();
  if (!userId) {
    redirect("/sign-in");
  }

  return (
    <div className="container max-w-3xl px-4 py-10 mx-auto">
      <h1 className="text-3xl font-bold text-center mb-6">Your Political Preferences</h1>
      <PreferencesNav />
      <div className="mt-6">
        {children}
      </div>
    </div>
  );
} 