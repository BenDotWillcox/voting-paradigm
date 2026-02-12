"use client";

import { CheckSquare } from "lucide-react";
import Link from "next/link";

export default function Header() {

  return (
    <header className="bg-primary text-primary-foreground shadow-md">
      <div className="container mx-auto px-4 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center space-x-2 hover:opacity-80 transition-opacity">
          <CheckSquare className="h-6 w-6" />
          <h1 className="text-xl font-bold">Nebula Civitas</h1>
        </Link>
        <nav className="flex items-center space-x-4">
          <Link 
            href="/proposals/new" 
            className="text-primary-foreground hover:text-primary-foreground/80 transition-colors"
          >
            Create Proposal
          </Link>
          <Link 
            href="/ballots/new" 
            className="text-primary-foreground hover:text-primary-foreground/80 transition-colors"
          >
            Create Ballot
          </Link>
          <Link 
            href="/whitepaper" 
            className="text-primary-foreground hover:text-primary-foreground/80 transition-colors"
          >
            Whitepaper
          </Link>
        </nav>
      </div>
    </header>
  );
}