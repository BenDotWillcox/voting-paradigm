import { Toaster } from "sonner";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Header from "@/components/header";
const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Nebula Civitas",
  description:
    "A portfolio of demos exploring voting methods, preference modeling, districting, and delegation.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} light`}>
        <Header />
        {children}
        <Toaster />
      </body>
    </html>
  );
}
