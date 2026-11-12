"use client";

import { createContext, useContext } from "react";
import { createPortal } from "react-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

type AppWindow = {
  /** The app's frame. Panels and overlays are drawn inside it, never over the whole page. */
  host: HTMLElement | null;
  /** Whether the frame itself fills the browser window. */
  full: boolean;
  setFull: (full: boolean) => void;
};

export const AppWindowContext = createContext<AppWindow>({
  host: null,
  full: false,
  setFull: () => undefined,
});

export function useAppWindow(): AppWindow {
  return useContext(AppWindowContext);
}

/**
 * A panel that slides in from the right edge of the app's window. It belongs
 * to the app: it covers the app's frame and nothing outside it, and stays in
 * view while the frame is taller than the screen.
 */
export function AppSheet({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const { host } = useAppWindow();
  if (!host) return null;
  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <Dialog.Portal container={host}>
        <div className="absolute inset-0 z-40 overflow-clip rounded-[inherit]">
          <Dialog.Overlay className="absolute inset-0 bg-black/55 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
          <div className="pointer-events-none sticky top-0 flex h-screen max-h-full justify-end">
            <Dialog.Content className="liquid-shell pointer-events-auto relative h-full w-full max-w-md overflow-y-auto border-l p-6 shadow-2xl shadow-black/60 outline-none data-[state=open]:animate-in data-[state=open]:slide-in-from-right data-[state=open]:duration-300">
              {children}
              <Dialog.Close className="absolute right-4 top-4 rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                <X className="h-4 w-4" aria-hidden="true" />
                <span className="sr-only">Close</span>
              </Dialog.Close>
            </Dialog.Content>
          </div>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Something that takes over the whole app window, and only the app window. */
export function WindowOverlay({ children }: { children: React.ReactNode }) {
  const { host } = useAppWindow();
  if (!host) return null;
  return createPortal(
    <div className="liquid-shell absolute inset-0 z-30 overflow-y-auto rounded-[inherit]">
      {children}
    </div>,
    host
  );
}
