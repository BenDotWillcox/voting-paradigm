import { AppLink as Link } from "./app-link";
import { ArrowRight, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  avatarTone,
  initials,
  personHandle,
  personHome,
  personName,
  profileHref,
  type Directory,
} from "./people";

const SIZES = {
  sm: "h-7 w-7 text-[0.65rem]",
  md: "h-10 w-10 text-sm",
  lg: "h-16 w-16 text-xl",
};

/** A round avatar with the person's initials, in their own steady colour. */
export function PersonAvatar({
  directory,
  id,
  size = "md",
  className,
}: {
  directory: Directory;
  id: string;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold",
        SIZES[size],
        // The account's owner is gold everywhere, so they are easy to find.
        id === directory.viewer ? "bg-amber-300 text-amber-950" : avatarTone(id),
        className
      )}
    >
      {initials(personName(directory, id))}
    </span>
  );
}

/** Avatar, name, handle and district on one row. */
export function PersonLine({ directory, id }: { directory: Directory; id: string }) {
  return (
    <span className="flex min-w-0 items-center gap-3">
      <PersonAvatar directory={directory} id={id} />
      <span className="min-w-0">
        <span className="block truncate font-medium">{personName(directory, id)}</span>
        <span className="block truncate text-xs text-muted-foreground">
          {personHandle(directory, id)} · {personHome(directory, id)}
        </span>
      </span>
    </span>
  );
}

/** A small icon button that opens a person's profile; sits at the end of their row. */
export function ProfileButton({ directory, id }: { directory: Directory; id: string }) {
  return (
    <Link
      href={profileHref(directory, id)}
      aria-label={`View ${personName(directory, id)}'s profile`}
      title="View profile"
      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:border-primary hover:bg-accent hover:text-foreground"
    >
      <UserRound className="h-4 w-4" aria-hidden="true" />
    </Link>
  );
}

/** A chain of people a vote passed through, each linking to their profile. */
export function Chain({ directory, chain }: { directory: Directory; chain: string[] }) {
  return (
    <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm">
      {chain.map((id, index) => (
        <span key={`${id}-${index}`} className="inline-flex items-center gap-1.5">
          {index > 0 && (
            <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" aria-label="hands to" />
          )}
          <Link
            href={profileHref(directory, id)}
            className="rounded border bg-background px-1.5 py-0.5 hover:bg-accent"
          >
            {personName(directory, id)}
          </Link>
        </span>
      ))}
    </p>
  );
}
