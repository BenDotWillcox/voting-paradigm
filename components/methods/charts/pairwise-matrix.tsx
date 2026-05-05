"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { CandidateData } from "@/types/methods";
import { cn } from "@/lib/utils";

interface PairwiseMatrixProps {
  candidates: CandidateData[];
  matrix: Record<string, Record<string, number>>;
  winners: string[];
}

export function PairwiseMatrix({
  candidates,
  matrix,
  winners,
}: PairwiseMatrixProps) {
  const winnerSet = new Set(winners);

  return (
    <TooltipProvider>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[140px]">vs.</TableHead>
              {candidates.map((c) => (
                <TableHead key={c.id} className="text-center min-w-[80px]">
                  <span
                    className={cn(
                      winnerSet.has(c.id) && "font-bold text-primary"
                    )}
                  >
                    {c.name}
                  </span>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {candidates.map((row) => (
              <TableRow key={row.id}>
                <TableCell
                  className={cn(
                    "font-medium",
                    winnerSet.has(row.id) && "font-bold text-primary"
                  )}
                >
                  {row.name}
                </TableCell>
                {candidates.map((col) => {
                  if (row.id === col.id) {
                    return (
                      <TableCell
                        key={col.id}
                        className="text-center bg-muted text-muted-foreground"
                      >
                        &mdash;
                      </TableCell>
                    );
                  }

                  const rowVsCol = matrix[row.id]?.[col.id] ?? 0;
                  const colVsRow = matrix[col.id]?.[row.id] ?? 0;
                  const rowWins = rowVsCol > colVsRow;
                  const tie = rowVsCol === colVsRow;

                  return (
                    <TableCell key={col.id} className="text-center p-0">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div
                            className={cn(
                              "w-full h-full p-2 font-mono text-sm",
                              rowWins &&
                                "bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-400",
                              !rowWins &&
                                !tie &&
                                "bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-400",
                              tie && "bg-muted text-muted-foreground"
                            )}
                          >
                            {rowVsCol}
                          </div>
                        </TooltipTrigger>
                        <TooltipContent>
                          {rowVsCol} voters prefer {row.name} over {col.name}
                          <br />
                          {colVsRow} voters prefer {col.name} over {row.name}
                          <br />
                          Margin: {rowVsCol - colVsRow > 0 ? "+" : ""}
                          {rowVsCol - colVsRow}
                        </TooltipContent>
                      </Tooltip>
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </TooltipProvider>
  );
}
