"use client";

import { ArrowRightLeft, Minus, Plus, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PersonProfile } from "@/types/delegation";
import { useAccount } from "./account-provider";
import { AppLink as Link } from "./app-link";
import { ago, personName, profileHref } from "./people";

const OWN = "border-primary/50 bg-primary/15 text-violet-200";
const GAINED = "border-sky-400/50 bg-sky-400/10 text-sky-200";
const LOST = "border-border bg-muted text-muted-foreground";

/**
 * The dated changes to one person's delegations, newest first: the ones
 * they made, and the ones other people made that handed them a category or
 * took one away. Changes the viewer makes in the demo are not here; those
 * are on the viewer's own Activity screen.
 */
export function ChangesList({ profile, isViewer }: { profile: PersonProfile; isViewer: boolean }) {
  const { directory } = useAccount();
  const subject = profile.person.id;
  const name = isViewer ? "You" : profile.person.name.split(" ")[0];
  const them = isViewer ? "you" : name;

  const person = (id: string | null) =>
    id === null ? null : id === subject ? (
      them
    ) : (
      <Link href={profileHref(directory, id)} className="font-medium underline-offset-4 hover:underline">
        {personName(directory, id)}
      </Link>
    );

  if (profile.changes.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {isViewer ? "Your" : `${name}'s`} delegations have not changed in the past year, and
        nobody has handed {them} a category or taken one back.
      </p>
    );
  }

  return (
    <ol className="space-y-1">
      {profile.changes.map((change, index) => {
        const category = <>“{change.category}”</>;
        const own = change.delegator === subject;
        let Icon = Plus;
        let tone = OWN;
        let body: React.ReactNode;
        if (own) {
          if (change.before === null) {
            body = (
              <>
                {name} handed {category} to {person(change.after)}.
              </>
            );
          } else if (change.after === null) {
            Icon = Minus;
            tone = LOST;
            body = (
              <>
                {name} took {category} back from {person(change.before)}.
              </>
            );
          } else {
            Icon = ArrowRightLeft;
            body = (
              <>
                {name} moved {category} from {person(change.before)} to {person(change.after)}.
              </>
            );
          }
        } else if (change.after === subject) {
          Icon = Users;
          tone = GAINED;
          body = (
            <>
              {person(change.delegator)} handed {them} {category}
              {change.before !== null && <>, moving it from {person(change.before)}</>}.
            </>
          );
        } else {
          Icon = Minus;
          tone = LOST;
          body = (
            <>
              {person(change.delegator)} moved {category} away from {them}
              {change.after !== null && <>, to {person(change.after)}</>}.
            </>
          );
        }
        return (
          <li key={index} className="flex gap-3 py-1.5">
            <span
              className={cn(
                "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border",
                tone
              )}
              aria-hidden="true"
            >
              <Icon className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0 text-sm leading-relaxed">
              <p>{body}</p>
              <p className="font-mono text-xs text-muted-foreground">{ago(-change.day)}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
