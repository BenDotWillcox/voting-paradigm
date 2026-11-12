import type { ComponentProps } from "react";
import Link from "next/link";

/**
 * A link between screens of the account app.
 *
 * Next.js scrolls to the top of the page on every navigation. The app sits
 * below the demo's header, so that would throw the reader out of the app on
 * each click. These links leave the scroll position alone; AppShell then
 * brings the app's own top edge into view only if it has scrolled out.
 */
export function AppLink(props: ComponentProps<typeof Link>) {
  return <Link scroll={false} {...props} />;
}
