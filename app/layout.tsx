import { Toaster } from "sonner";
import { Providers } from "@/components/utilities/providers";
import { createProfile, getProfileByUserId } from "@/db/queries/profiles-queries";
import { ClerkProvider } from "@clerk/nextjs";
import { auth } from "@clerk/nextjs/server";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Header from "@/components/header";
const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Voting Paradigm",
  description: "A voting paradigm for the future."
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const { userId } = await auth();

  if (userId) {
    const profile = await getProfileByUserId(userId);
    if (!profile) {
      await createProfile({ userId });
    }
  }

  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} dark`}>
        <ClerkProvider>
          <Providers
            attribute="class"
            defaultTheme="dark"
            disableTransitionOnChange
            enableSystem={false}
          >
            <Header />
            {children}
            <Toaster />
          </Providers>
        </ClerkProvider>
      </body>
    </html>
  );
}
