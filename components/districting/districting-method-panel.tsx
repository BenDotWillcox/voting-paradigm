import { MapPinned } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const methodSteps = [
  {
    title: "1. Population units",
    description:
      "Each tract enters as an unsplit unit with a centroid and population count.",
  },
  {
    title: "2. Seed centers",
    description:
      "Population-weighted k-means++ places the first district centers where people actually are.",
  },
  {
    title: "3. Power assignment",
    description:
      "Each tract joins the center with the lowest distance-minus-weight score, while weights push cells toward equal population.",
  },
  {
    title: "4. Recenter and cache",
    description:
      "Centers move to population-weighted centroids until stable, then the GeoJSON and metrics are served as a static artifact.",
  },
];

export function DistrictingMethodPanel() {
  return (
    <section>
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <MapPinned className="h-5 w-5 text-primary" />
          <CardTitle>Balanced centroidal power diagrams</CardTitle>
          </div>
          <CardDescription>
            The district-drawing target is compact, population-balanced
            geography generated from tract centroids and population, without
            partisan inputs.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2">
            {methodSteps.map((step) => (
              <div key={step.title} className="rounded-md border p-3">
                <div className="text-sm font-semibold">{step.title}</div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {step.description}
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
