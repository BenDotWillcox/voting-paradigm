"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AppLink as Link } from "./app-link";
import { usePathname, useRouter } from "next/navigation";
import {
  Bell,
  ChevronDown,
  History,
  Inbox,
  Info,
  Landmark,
  Maximize,
  Menu,
  Minimize,
  Network,
  RotateCcw,
  Search,
  UserRound,
  Waypoints,
} from "lucide-react";
import { getPersonProfileAction } from "@/actions/delegation-actions";
import { cn } from "@/lib/utils";
import type { HistoryEntry } from "@/types/delegation";
import { useAccount } from "./account-provider";
import { AppWindowContext, useAppWindow } from "./app-window";
import {
  ago,
  closing,
  personHandle,
  personHome,
  personName,
  profileHref,
  searchPeople,
} from "./people";
import { PersonAvatar, PersonLine } from "./person-bits";
import { choiceShort, findQuestion, outcomeLabel } from "./ballots";
import { delegateIsLate, needsViewer } from "./votes";

/** Close a dropdown when the pointer goes down outside it or Escape is pressed. */
function useDismiss(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    const escape = (event: KeyboardEvent) =>
      event.key === "Escape" && onClose();
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open, onClose]);
  return ref;
}

// How far the app's top edge can be above the viewport, in pixels, with a
// screen's heading still showing under the top bar.
const HEADING_ROOM = 80;

const DROPDOWN =
  "absolute right-0 top-full z-30 mt-2 rounded-xl border bg-popover p-2 shadow-2xl shadow-black/60";

/**
 * The frame of the account app: a top bar with people search, notifications
 * and the signed-in account, a side menu, and the current screen.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  // Picking a destination on a phone closes the menu.
  useEffect(() => setMenuOpen(false), [pathname]);

  // Moving between screens never sends the reader to the top of the page
  // (the app's links do not scroll). The one adjustment: if the reader has
  // scrolled far enough into a screen that the next one's heading would be
  // off the top, bring the app's top edge back into view. Back and forward
  // are left alone, so the browser can return to where the reader was.
  const shell = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  // The frame is also where sheets and overlays are drawn, so they cover the
  // app and nothing else. State, not a ref: they render once it exists.
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  // Full screen: the frame fills the browser window and scrolls inside itself.
  const [full, setFull] = useState(false);
  useEffect(() => {
    if (!full) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [full]);
  const arrived = useRef(false);
  const viaHistory = useRef(false);
  useEffect(() => {
    const mark = () => {
      viaHistory.current = true;
    };
    window.addEventListener("popstate", mark);
    return () => window.removeEventListener("popstate", mark);
  }, []);
  useEffect(() => {
    if (!arrived.current) {
      arrived.current = true; // the first render is the page load, not a move
      return;
    }
    if (viaHistory.current) {
      viaHistory.current = false;
      return;
    }
    if (full) {
      // In full screen the app scrolls inside itself; a new screen starts at its top.
      scroller.current?.scrollTo({ top: 0 });
      return;
    }
    const frame = shell.current;
    if (frame && frame.getBoundingClientRect().top < -HEADING_ROOM) {
      frame.scrollIntoView({ block: "start" });
    }
    // `full` is read, not watched: entering or leaving full screen is not a move.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  const appWindow = useMemo(() => ({ host, full, setFull }), [host, full]);

  return (
    <AppWindowContext.Provider value={appWindow}>
      <div
        ref={(element) => {
          shell.current = element;
          setHost(element);
        }}
        className={cn(
          "liquid-app dark liquid-shell",
          full
            ? "fixed inset-0 z-50 flex flex-col"
            : "relative scroll-mt-3 rounded-2xl border shadow-2xl shadow-indigo-950/40",
        )}
      >
        <header
          className={cn(
            "liquid-grid relative z-20 flex h-14 shrink-0 items-center gap-3 border-b px-3 sm:px-4",
            !full && "rounded-t-2xl",
          )}
        >
          <button
            type="button"
            className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground md:hidden"
            aria-label="Menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
          <Link href="/liquid" className="flex shrink-0 items-center gap-2.5">
            <span className="liquid-glow flex h-8 w-8 items-center justify-center rounded-lg bg-primary/15 text-primary">
              <Waypoints className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="hidden leading-tight sm:block">
              <span className="block text-sm font-semibold tracking-tight">
                Liquid
              </span>
              <span className="liquid-label block !text-[0.6rem]">
                Civic account
              </span>
            </span>
          </Link>
          <PeopleSearch className="ml-auto hidden flex-1 sm:block sm:max-w-sm" />
          <span className="flex-1 sm:hidden" />
          <Notifications />
          <AccountMenu />
        </header>

        <div
          ref={scroller}
          className={cn(
            "md:grid md:grid-cols-[13.5rem_minmax(0,1fr)]",
            full && "min-h-0 flex-1 overflow-y-auto",
          )}
        >
          <SideMenu open={menuOpen} />
          {/* At least a screen tall. A short screen would otherwise shorten the
            page, and the browser would pull the view up to fit: the same jump
            the non-scrolling links are there to avoid. A full screen, with
            the top bar above it, leaves room for every position that
            HEADING_ROOM allows. */}
          <div
            className={cn(
              "min-w-0 p-4 sm:p-6 md:border-l lg:p-7",
              full ? "min-h-full" : "min-h-screen",
            )}
          >
            {children}
          </div>
        </div>
      </div>
    </AppWindowContext.Provider>
  );
}

function SideMenu({ open }: { open: boolean }) {
  const pathname = usePathname();
  const { directory, openVotes, votes, reset } = useAccount();
  const { full, setFull } = useAppWindow();
  const waiting =
    openVotes?.filter(
      (entry) =>
        needsViewer(entry, directory.viewer) && !votes[entry.question.id],
    ).length ?? 0;

  const items = [
    {
      href: "/liquid",
      label: "Hub",
      Icon: Network,
      active: pathname === "/liquid",
    },
    {
      href: "/liquid/votes",
      label: "Incoming Votes",
      Icon: Inbox,
      active: pathname.startsWith("/liquid/votes"),
      badge: waiting,
    },
    {
      href: "/liquid/city",
      label: "City Results",
      Icon: Landmark,
      active: pathname.startsWith("/liquid/city"),
    },
    {
      href: "/liquid/activity",
      label: "Activity",
      Icon: History,
      active: pathname.startsWith("/liquid/activity"),
    },
    {
      href: profileHref(directory, directory.viewer),
      label: "Profile",
      Icon: UserRound,
      active: pathname.startsWith("/liquid/people"),
    },
  ];

  const link = (active: boolean) =>
    cn(
      "relative flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
      active
        ? "bg-primary/15 font-medium text-foreground before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-primary"
        : "text-muted-foreground hover:bg-accent hover:text-foreground",
    );

  return (
    <nav
      aria-label="App"
      className={cn(
        // It stays in view while the screen beside it scrolls.
        "flex-col gap-6 border-b p-3 md:sticky md:top-0 md:flex md:self-start md:border-b-0",
        open ? "flex" : "hidden",
      )}
    >
      <div className="space-y-1">
        {/* On a phone the top bar has no room for the search, so it lives here. */}
        <PeopleSearch className="mb-3 sm:hidden" />
        <p className="liquid-label px-3 pb-1.5 pt-1">Menu</p>
        {items.map(({ href, label, Icon, active, badge }) => (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={link(active)}
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="flex-1">{label}</span>
            {badge ? (
              <span
                className="rounded-full bg-primary px-1.5 py-0.5 font-mono text-[0.65rem] font-semibold leading-none text-primary-foreground"
                aria-label={`${badge} waiting for your vote`}
              >
                {badge}
              </span>
            ) : null}
          </Link>
        ))}
      </div>
      <div className="space-y-1">
        <Link
          href="/liquid/about"
          aria-current={pathname === "/liquid/about" ? "page" : undefined}
          className={link(pathname === "/liquid/about")}
        >
          <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
          About this demo
        </Link>
        <button
          type="button"
          className={link(false)}
          aria-pressed={full}
          onClick={() => setFull(!full)}
        >
          {full ? (
            <Minimize className="h-4 w-4 shrink-0" aria-hidden="true" />
          ) : (
            <Maximize className="h-4 w-4 shrink-0" aria-hidden="true" />
          )}
          {full ? "Exit full screen" : "View in full screen"}
        </button>
        <button
          type="button"
          className={link(false)}
          onClick={reset}
          title="Put the delegations and votes back to how the demo starts"
        >
          <RotateCcw className="h-4 w-4 shrink-0" aria-hidden="true" />
          Reset demo
        </button>
      </div>
    </nav>
  );
}

/** Find anyone in the city by name or @username and open their profile. */
function PeopleSearch({ className }: { className?: string }) {
  const router = useRouter();
  const { directory } = useAccount();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  const matches = useMemo(
    () => searchPeople(directory, query),
    [directory, query],
  );
  const shown = matches.slice(0, 6);

  const go = (id: string) => {
    setOpen(false);
    setQuery("");
    router.push(profileHref(directory, id), { scroll: false });
  };

  return (
    <div ref={ref} className={cn("relative min-w-0", className)}>
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <input
        type="search"
        value={query}
        placeholder="Search people"
        aria-label="Search people by name or username"
        autoComplete="off"
        className="h-9 w-full rounded-lg border bg-background/60 pl-9 pr-3 text-sm outline-none placeholder:text-muted-foreground focus:border-primary"
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && shown[0]) go(shown[0].id);
        }}
      />
      {open && query.trim() && (
        <div className={cn(DROPDOWN, "left-0 right-auto w-full min-w-[17rem]")}>
          {shown.length === 0 ? (
            <p className="p-2 text-sm text-muted-foreground">
              Nobody by that name or username.
            </p>
          ) : (
            <ul>
              {shown.map((person) => (
                <li key={person.id}>
                  <button
                    type="button"
                    className="flex w-full rounded-lg p-2 text-left text-sm hover:bg-accent"
                    onClick={() => go(person.id)}
                  >
                    <PersonLine directory={directory} id={person.id} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {matches.length > shown.length && (
            <p className="liquid-label px-2 pb-1 pt-2">
              {shown.length} of {matches.length} · keep typing
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Votes that close soon and wait on the viewer, and what delegates recently decided for them. */
function Notifications() {
  const { scenario, directory, openVotes, votes } = useAccount();
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  const [recent, setRecent] = useState<HistoryEntry[] | null>(null);

  const closingSoon = useMemo(
    () =>
      (openVotes ?? []).filter(
        (entry) =>
          needsViewer(entry, directory.viewer) &&
          !votes[entry.question.id] &&
          entry.paper.closes_in_days <= 7,
      ),
    [openVotes, votes, directory.viewer],
  );
  // Votes a delegate holds and has not cast, with a week or less to go.
  const unanswered = useMemo(
    () => (openVotes ?? []).filter((entry) => delegateIsLate(entry, directory.viewer)),
    [openVotes, directory.viewer],
  );
  const alerts = closingSoon.length + unanswered.length;

  useEffect(() => {
    if (!open || recent !== null) return;
    let stale = false;
    void getPersonProfileAction(directory.viewer).then((result) => {
      if (stale) return;
      setRecent(
        (result.data?.history ?? [])
          .filter((entry) => entry.how === "delegated")
          .slice(0, 4),
      );
    });
    return () => {
      stale = true;
    };
  }, [open, recent, directory.viewer]);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        className="relative rounded-lg p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
        aria-label={`Notifications, ${closingSoon.length} need you soon, ${unanswered.length} with a delegate who has not voted`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Bell className="h-5 w-5" aria-hidden="true" />
        {alerts > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 font-mono text-[0.6rem] font-semibold leading-none text-primary-foreground">
            {alerts}
          </span>
        )}
      </button>
      {open && (
        <div className={cn(DROPDOWN, "w-[min(22rem,calc(100vw-3rem))]")}>
          <p className="liquid-label px-2 pb-1 pt-1.5">Needs you soon</p>
          {closingSoon.length === 0 ? (
            <p className="px-2 pb-2 text-sm text-muted-foreground">
              Nothing closes in the next week without your answer.
            </p>
          ) : (
            <ul>
              {closingSoon.map((entry) => (
                <li key={entry.question.id}>
                  <Link
                    href={`/liquid/votes/${entry.question.id}`}
                    className="block rounded-lg p-2 text-sm hover:bg-accent"
                    onClick={() => setOpen(false)}
                  >
                    <span className="block font-medium">
                      {entry.question.title}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {closing(entry.paper.closes_in_days)}
                      {entry.result.inbox.votes_for_others > 0 &&
                        ` · ${entry.result.inbox.votes_for_others} other ${entry.result.inbox.votes_for_others === 1 ? "person waits" : "people wait"} on you`}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {unanswered.length > 0 && (
            <>
              <p className="liquid-label mt-1 border-t px-2 pb-1 pt-3">
                Your delegate has not voted
              </p>
              <ul>
                {unanswered.map((entry) => (
                  <li key={entry.question.id}>
                    <Link
                      href={`/liquid/votes/${entry.question.id}`}
                      className="block rounded-lg p-2 text-sm hover:bg-accent"
                      onClick={() => setOpen(false)}
                    >
                      <span className="block">
                        <span className="font-medium">
                          {personName(directory, entry.result.receipt?.chain[1] ?? "")}
                        </span>{" "}
                        has yet to decide
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {entry.question.title} · {closing(entry.paper.closes_in_days).toLowerCase()}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="liquid-label mt-1 border-t px-2 pb-1 pt-3">
            Decided for you
          </p>
          {recent === null ? (
            <p className="px-2 pb-2 text-sm text-muted-foreground">Loading…</p>
          ) : recent.length === 0 ? (
            <p className="px-2 pb-2 text-sm text-muted-foreground">
              No delegate has voted for you yet.
            </p>
          ) : (
            <ul>
              {recent.map((entry) => (
                <li key={entry.question_id}>
                  <Link
                    href={`/liquid/votes/${entry.question_id}`}
                    className="block rounded-lg p-2 text-sm hover:bg-accent"
                    onClick={() => setOpen(false)}
                  >
                    <span className="block">
                      <span className="font-medium">
                        {personName(directory, entry.resolver)}
                      </span>{" "}
                      voted{" "}
                      {entry.choice === null
                        ? "nothing"
                        : choiceShort(
                            findQuestion(scenario, entry.question_id),
                            entry.choice,
                          )}{" "}
                      for you
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {entry.title} ·{" "}
                      {outcomeLabel(
                        findQuestion(scenario, entry.question_id),
                        entry.winners,
                      )}{" "}
                      · {ago(entry.closed_days_ago)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <Link
            href="/liquid/votes"
            className="mt-1 block rounded-lg border-t p-2 pt-3 text-center text-sm text-primary hover:underline"
            onClick={() => setOpen(false)}
          >
            Open Incoming Votes
          </Link>
        </div>
      )}
    </div>
  );
}

/** The signed-in account, top right. */
function AccountMenu() {
  const { directory, reset } = useAccount();
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  const viewer = directory.viewer;

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        className="flex items-center gap-2.5 rounded-lg border bg-background/50 py-1 pl-1 pr-2 hover:bg-accent"
        aria-label="Your account"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <PersonAvatar directory={directory} id={viewer} size="sm" />
        <span className="hidden text-left leading-tight sm:block">
          <span className="block text-sm font-medium">
            {personName(directory, viewer)}
          </span>
          <span className="block font-mono text-[0.65rem] text-muted-foreground">
            {personHandle(directory, viewer)}
          </span>
        </span>
        <ChevronDown
          className="h-3.5 w-3.5 text-muted-foreground"
          aria-hidden="true"
        />
      </button>
      {open && (
        <div className={cn(DROPDOWN, "w-60")}>
          <div className="flex items-center gap-3 p-2">
            <PersonAvatar directory={directory} id={viewer} />
            <div className="min-w-0 leading-tight">
              <p className="text-sm font-medium">
                {personName(directory, viewer)}
              </p>
              <p className="font-mono text-xs text-muted-foreground">
                {personHandle(directory, viewer)}
              </p>
              <p className="text-xs text-muted-foreground">
                {personHome(directory, viewer)}
              </p>
            </div>
          </div>
          <div className="mt-1 border-t pt-1">
            <Link
              href={profileHref(directory, viewer)}
              className="flex items-center gap-2.5 rounded-lg p-2 text-sm hover:bg-accent"
              onClick={() => setOpen(false)}
            >
              <UserRound
                className="h-4 w-4 text-muted-foreground"
                aria-hidden="true"
              />
              View profile
            </Link>
            <button
              type="button"
              className="flex w-full items-center gap-2.5 rounded-lg p-2 text-left text-sm hover:bg-accent"
              onClick={() => {
                reset();
                setOpen(false);
              }}
            >
              <RotateCcw
                className="h-4 w-4 text-muted-foreground"
                aria-hidden="true"
              />
              Reset demo
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
