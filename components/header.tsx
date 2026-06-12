import { CheckSquare } from "lucide-react";
import Link from "next/link";

const navItems = [
  { href: "/methods", label: "Methods" },
  { href: "/preferences", label: "Preferences" },
  { href: "/districts", label: "Districts" },
  { href: "/liquid", label: "Liquid" },
];

export default function Header() {
  return (
    <header className="bg-primary text-primary-foreground shadow-md">
      <div className="container mx-auto flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <Link
          href="/"
          className="flex items-center space-x-2 transition-opacity hover:opacity-80"
        >
          <CheckSquare className="h-6 w-6" />
          <h1 className="text-xl font-bold">Nebula Civitas</h1>
        </Link>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm font-medium">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-primary-foreground transition-colors hover:text-primary-foreground/80"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
