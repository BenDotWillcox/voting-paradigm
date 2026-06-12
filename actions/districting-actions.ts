"use server";

import { getApportionment } from "@/lib/districting-api";
import { CAP_MAX, CAP_MIN } from "@/lib/districting-cap-scale";
import type { ApportionmentDto } from "@/types/districting";
import type { ActionResult } from "@/types/actions/action-types";

/**
 * Fetch the apportionment for a given cap. Used by the client-side slider
 * to pull fresh numbers on every settled drag.
 *
 * Returns an `ActionResult` so the client can surface the API being down
 * without crashing the explorer.
 */
export async function fetchApportionmentAction(
  cap: number
): Promise<ActionResult<ApportionmentDto>> {
  if (!Number.isInteger(cap) || cap < CAP_MIN || cap > CAP_MAX) {
    return {
      isSuccess: false,
      message: `Cap must be an integer in [${CAP_MIN}, ${CAP_MAX}]; got ${cap}.`,
    };
  }
  try {
    const data = await getApportionment(cap);
    return {
      isSuccess: true,
      message: `Apportionment computed for cap=${cap}.`,
      data,
    };
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Unknown districting API error.";
    return { isSuccess: false, message };
  }
}
