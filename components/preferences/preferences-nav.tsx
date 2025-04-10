"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Sliders, List } from "lucide-react";

const navItems = [
  {
    name: "Ratings",
    href: "/preferences/ratings",
    icon: <Sliders className="h-4 w-4 mr-2" />,
  },
  {
    name: "Importance",
    href: "/preferences/importance",
    icon: <List className="h-4 w-4 mr-2" />,
  },
];

export function PreferencesNav() {
  const pathname = usePathname();
  
  return (
    <nav className="flex bg-card p-1 rounded-lg shadow-sm border">
      {navItems.map((item) => {
        const isActive = pathname === item.href;
        
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex-1 flex items-center justify-center py-2 px-3 text-sm font-medium rounded-md transition-all",
              isActive 
                ? "bg-primary text-primary-foreground shadow-sm" 
                : "hover:bg-muted"
            )}
          >
            {item.icon}
            {item.name}
          </Link>
        );
      })}
    </nav>
  );
} 