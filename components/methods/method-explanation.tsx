"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { MethodDescription } from "@/lib/methods/method-descriptions";

interface MethodExplanationProps {
  description: MethodDescription;
}

export function MethodExplanation({ description }: MethodExplanationProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-lg">{description.name}</CardTitle>
          {description.aliases.map((alias) => (
            <Badge key={alias} variant="secondary" className="text-xs">
              {alias}
            </Badge>
          ))}
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          <span className="font-medium">Ballot:</span> {description.ballotType}
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm">{description.howItWorks}</p>

        <Accordion type="single" collapsible>
          <AccordionItem value="strengths-weaknesses">
            <AccordionTrigger className="text-sm">
              Strengths & Weaknesses
            </AccordionTrigger>
            <AccordionContent>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-sm font-medium text-green-700 dark:text-green-400 mb-1">
                    Strengths
                  </p>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    {description.strengths.map((s, i) => (
                      <li key={i}>+ {s}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-sm font-medium text-red-700 dark:text-red-400 mb-1">
                    Weaknesses
                  </p>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    {description.weaknesses.map((w, i) => (
                      <li key={i}>- {w}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="real-world">
            <AccordionTrigger className="text-sm">
              Real-world usage
            </AccordionTrigger>
            <AccordionContent>
              <ul className="text-sm text-muted-foreground space-y-1">
                {description.realWorldUsage.map((u, i) => (
                  <li key={i}>{u}</li>
                ))}
              </ul>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
}
