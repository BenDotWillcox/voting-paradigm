"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { resolveProfileAction } from "@/actions/methods-actions";
import { encodeProfile, totalVoters } from "@/lib/methods/profile";
import type { ProfileResolveResponse, UtilityProfile } from "@/types/methods";

export type ElectorateStatus =
  | { kind: "ready" }
  | { kind: "counting" }
  | { kind: "empty" }
  | { kind: "offline"; message: string };

// Wait this long after the last edit before asking the API to count
const DEBOUNCE_MS = 250;
// Every gallery specimen, resolved at build time (scripts/build_methods_artifacts.py)
const SPECIMEN_RESOLUTIONS = "/data/methods/specimen-resolutions.json";

export interface Electorate {
  profile: UtilityProfile;
  /** The latest count; it lags the profile while an edit is being counted. */
  resolution: ProfileResolveResponse;
  status: ElectorateStatus;
  /** Whether the resolution is the current profile's. */
  showing: boolean;
  /** The profile's URL form and cache key. */
  key: string;
  /** Show a profile, with its count when the caller already has it. */
  load: (profile: UtilityProfile, resolution?: ProfileResolveResponse) => void;
}

/**
 * The one electorate the slides and the playground share, and its count.
 * Presets and specimens resolve from static artifacts; edits are counted by
 * the Python API (POST /api/voting/profile/resolve), cached by profile.
 */
export function useElectorate({
  presets,
  initialProfile,
  initialResolution,
}: {
  presets: { profile: UtilityProfile; resolution: ProfileResolveResponse }[];
  initialProfile: UtilityProfile;
  initialResolution: ProfileResolveResponse | null;
}): Electorate {
  const cache = useRef(
    new Map([
      ...presets.map((preset) => [encodeProfile(preset.profile), preset.resolution] as const),
      ...(initialResolution ? [[encodeProfile(initialProfile), initialResolution] as const] : []),
    ])
  );
  const [profile, setProfile] = useState(initialProfile);
  const [resolution, setResolution] = useState<ProfileResolveResponse>(
    () => cache.current.get(encodeProfile(initialProfile)) ?? presets[0].resolution
  );
  const [status, setStatus] = useState<ElectorateStatus>({ kind: "ready" });
  const [staticVersion, setStaticVersion] = useState(0);
  const latest = useRef(0);

  const key = useMemo(() => encodeProfile(profile), [profile]);
  const resolvedKey =
    resolution.profile.ballot_type === "utility" ? encodeProfile(resolution.profile) : "";

  // Specimens resolve from a static file, fetched once in the background
  useEffect(() => {
    let cancelled = false;
    fetch(SPECIMEN_RESOLUTIONS)
      .then((response) => (response.ok ? response.json() : null))
      .then((data: { resolutions?: Record<string, ProfileResolveResponse> } | null) => {
        if (cancelled || !data?.resolutions) return;
        for (const [k, v] of Object.entries(data.resolutions)) cache.current.set(k, v);
        setStaticVersion((version) => version + 1);
      })
      .catch(() => {
        // The API resolves specimens too; nothing to do
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const request = ++latest.current;
    if (totalVoters(profile) === 0) {
      setStatus({ kind: "empty" });
      return;
    }
    const cached = cache.current.get(key);
    if (cached) {
      setResolution(cached);
      setStatus({ kind: "ready" });
      return;
    }
    setStatus({ kind: "counting" });
    const timer = window.setTimeout(async () => {
      const result = await resolveProfileAction({ profile });
      if (request !== latest.current) return;
      if (result.isSuccess && result.data) {
        cache.current.set(key, result.data);
        setResolution(result.data);
        setStatus({ kind: "ready" });
      } else {
        setStatus({ kind: "offline", message: result.message });
      }
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [profile, key, staticVersion]);

  return {
    profile,
    resolution,
    status,
    showing: resolvedKey === key,
    key,
    load: (next, counted) => {
      if (counted) cache.current.set(encodeProfile(next), counted);
      setProfile(next);
    },
  };
}
