"use client";

import * as React from "react";

interface DistrictingStateLayoutProps {
  sidebar: React.ReactNode;
  children: React.ReactNode;
}

export function DistrictingStateLayout({
  sidebar,
  children,
}: DistrictingStateLayoutProps) {
  const contentRef = React.useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = React.useState<number | null>(null);

  React.useLayoutEffect(() => {
    const node = contentRef.current;
    if (!node) return;

    const updateHeight = () => {
      setContentHeight(Math.ceil(node.getBoundingClientRect().height));
    };

    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)] lg:items-start">
      <div
        className="min-h-[36rem] w-full overflow-hidden lg:min-h-0"
        style={{ height: contentHeight ?? 640 }}
      >
        {sidebar}
      </div>
      <div ref={contentRef} className="min-h-[40rem] space-y-6">
        {children}
      </div>
    </div>
  );
}
