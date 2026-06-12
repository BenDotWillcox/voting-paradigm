import type { CachedDistrictPlan } from "@/types/districting";

interface DistrictPlanMetricsProps {
  plan: CachedDistrictPlan;
}

export function DistrictPlanMetrics({ plan }: DistrictPlanMetricsProps) {
  const populations = Object.values(plan.district_populations);
  const min = Math.min(...populations);
  const max = Math.max(...populations);
  const pctDeviation =
    plan.target_population > 0
      ? (plan.max_population_imbalance / plan.target_population) * 100
      : 0;

  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
      <dt className="text-muted-foreground">Cached unit</dt>
      <dd className="text-right capitalize">{plan.unit}</dd>
      <dt className="text-muted-foreground">Districts</dt>
      <dd className="text-right tabular-nums">{plan.seats}</dd>
      <dt className="text-muted-foreground">Target</dt>
      <dd className="text-right tabular-nums">
        {plan.target_population.toLocaleString()}
      </dd>
      <dt className="text-muted-foreground">Min / max</dt>
      <dd className="text-right tabular-nums">
        {min.toLocaleString()} / {max.toLocaleString()}
      </dd>
      <dt className="text-muted-foreground">Max deviation</dt>
      <dd className="text-right tabular-nums">
        {plan.max_population_imbalance.toLocaleString()} ({pctDeviation.toFixed(2)}%)
      </dd>
      <dt className="text-muted-foreground">Iterations</dt>
      <dd className="text-right tabular-nums">{plan.iterations}</dd>
      <dt className="text-muted-foreground">Converged</dt>
      <dd className="text-right">{plan.converged ? "Yes" : "No"}</dd>
    </dl>
  );
}
