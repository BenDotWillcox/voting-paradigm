import * as React from "react";

import { cn } from "@/lib/utils";

export interface DataTableColumn {
  key: string;
  label: string;
  /** Right-aligned with tabular figures. */
  numeric?: boolean;
}

export interface DataTableProps {
  columns: DataTableColumn[];
  /** Pre-formatted values; numbers are locale-formatted. */
  rows: Array<Record<string, string | number>>;
  caption?: string;
}

interface StoryFigureProps {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Data source line, e.g. "2020 Census apportionment counts". */
  source?: React.ReactNode;
  note?: React.ReactNode;
  /**
   * The table view. Every figure ships one: it is the accessibility
   * fallback for color-only identity and the relief for light-mode palette
   * slots under 3:1 contrast.
   */
  table?: DataTableProps;
  /** Omit the surface panel (e.g. inside a Scrolly graphic column). */
  bare?: boolean;
  className?: string;
  children: React.ReactNode;
}

/** A titled chart with source line and a collapsible data table. */
export function StoryFigure({
  title,
  subtitle,
  source,
  note,
  table,
  bare = false,
  className,
  children,
}: StoryFigureProps) {
  return (
    <figure
      className={cn(
        "w-full",
        !bare && "rounded-xl bg-story-surface p-4 ring-1 ring-story-rule sm:p-6",
        className
      )}
    >
      {title || subtitle ? (
        <figcaption className="mb-4">
          {title ? (
            <div className="text-base font-semibold text-story-ink">{title}</div>
          ) : null}
          {subtitle ? (
            <div className="mt-1 text-sm text-story-ink-2">{subtitle}</div>
          ) : null}
        </figcaption>
      ) : null}
      {children}
      {source || note || table ? (
        <div className="mt-4 space-y-1 text-xs leading-relaxed text-story-muted">
          {note ? <p>{note}</p> : null}
          {source ? <p>Source: {source}</p> : null}
          {table ? (
            <details className="group/table pt-1">
              <summary className="cursor-pointer text-story-ink-2 select-none hover:text-story-ink">
                <span className="group-open/table:hidden">View data</span>
                <span className="hidden group-open/table:inline">Hide data</span>
              </summary>
              <DataTable {...table} />
            </details>
          ) : null}
        </div>
      ) : null}
    </figure>
  );
}

export function DataTable({ columns, rows, caption }: DataTableProps) {
  return (
    <div className="mt-3 max-h-80 overflow-auto rounded-md ring-1 ring-story-rule">
      <table className="w-full border-collapse text-sm text-story-ink">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead className="sticky top-0 bg-story-surface">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn(
                  "border-b border-story-grid px-3 py-2 font-medium text-story-ink-2",
                  column.numeric ? "text-right" : "text-left"
                )}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-story-grid last:border-0">
              {columns.map((column) => {
                const value = row[column.key];
                return (
                  <td
                    key={column.key}
                    className={cn(
                      "px-3 py-1.5",
                      column.numeric ? "text-right tabular-nums" : "text-left"
                    )}
                  >
                    {typeof value === "number" ? value.toLocaleString("en-US") : value}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
