import { cn } from "@/lib/utils";

/**
 * The site's mark: two ballot choices on a blue-to-rose tile, the first
 * filled in.
 */
export function SiteMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid size-7 flex-none place-items-center rounded-lg bg-[linear-gradient(135deg,var(--color-site-blue),var(--color-site-violet)_55%,var(--color-site-rose))] shadow-[inset_0_1px_0_rgb(255_255_255/0.22)]",
        className
      )}
    >
      <svg viewBox="0 0 32 32" className="size-full">
        <ellipse cx="10.5" cy="12" rx="3.6" ry="2.7" fill="#ffffff" />
        <rect x="16.5" y="11" width="9" height="2" rx="1" fill="#ffffff" opacity="0.9" />
        <ellipse cx="10.5" cy="20" rx="3" ry="2.1" fill="none" stroke="#ffffff" strokeWidth="1.4" opacity="0.7" />
        <rect x="16.5" y="19" width="6" height="2" rx="1" fill="#ffffff" opacity="0.55" />
      </svg>
    </span>
  );
}
