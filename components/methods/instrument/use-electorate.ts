"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { requestProfile } from "@/lib/methods-client";
import { encodeProfile, totalVoters } from "@/lib/methods/profile";
import { RequestTimeoutError, withRequestDeadline } from "@/lib/request-deadline";
import type { ProfileResolveResponse, UtilityProfile } from "@/types/methods";

export type ElectorateStatus =
  | { kind: "ready" }
  | { kind: "counting" }
  | { kind: "empty" }
  | { kind: "offline"; message: string };

// Wait this long after the last edit before asking the API to count
const DEBOUNCE_MS = 250;
const COUNT_TIMEOUT_MS = 15_000;
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
  /** Retry the current edits without replacing them with a preset. */
  retry: () => void;
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
  const [retryVersion, setRetryVersion] = useState(0);
  const latest = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);

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
    const active = new AbortController();
    activeRequest.current = active;
    const timer = window.setTimeout(async () => {
      try {
        // Direct HTTP can be cancelled without leaving retries queued behind
        // a stalled Server Action transport.
        const result = await withRequestDeadline((signal) => requestProfile({ profile }, signal), {
          timeoutMs: COUNT_TIMEOUT_MS,
          signal: active.signal,
        });
        if (active.signal.aborted || request !== latest.current) return;
        if (result.isSuccess && result.data) {
          cache.current.set(key, result.data);
          setResolution(result.data);
          setStatus({ kind: "ready" });
        } else {
          setStatus({ kind: "offline", message: result.message });
        }
      } catch (error) {
        if (active.signal.aborted || request !== latest.current) return;
        setStatus({
          kind: "offline",
          message: error instanceof RequestTimeoutError
            ? "Counting took too long. Your edits are preserved; try again."
            : "Live counting is unavailable right now. Your edits are preserved; try again.",
        });
      } finally {
        if (activeRequest.current === active) activeRequest.current = null;
      }
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      active.abort();
      if (activeRequest.current === active) activeRequest.current = null;
    };
  }, [profile, key, staticVersion, retryVersion]);

  return {
    profile,
    resolution,
    status,
    showing: resolvedKey === key,
    key,
    load: (next, counted) => {
      latest.current++;
      activeRequest.current?.abort();
      if (counted) cache.current.set(encodeProfile(next), counted);
      setProfile(next);
      // A caller may supply this same object with a fresh count, or ask to
      // reload it while a request is pending; React otherwise skips the effect.
      if (next === profile) setRetryVersion((version) => version + 1);
    },
    retry: () => {
      latest.current++;
      activeRequest.current?.abort();
      setRetryVersion((version) => version + 1);
    },
  };
}
