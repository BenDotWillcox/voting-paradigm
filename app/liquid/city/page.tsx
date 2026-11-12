import type { Metadata } from "next";
import { CityView } from "@/components/liquid/city-view";
import { getCityResults } from "@/lib/delegation-api";
import type { CityResults } from "@/types/delegation";

export const metadata: Metadata = { title: "City results · Liquid democracy" };

/** Every closed vote across the city; null when the service cannot be reached. */
async function loadCity(): Promise<CityResults | null> {
  try {
    return await getCityResults();
  } catch (error) {
    console.error("Error loading the liquid democracy city results:", error);
    return null;
  }
}

export default async function LiquidCityPage() {
  const city = await loadCity();
  if (!city) {
    return <p className="text-sm text-muted-foreground">The city&apos;s results could not be loaded.</p>;
  }
  return <CityView city={city} />;
}
