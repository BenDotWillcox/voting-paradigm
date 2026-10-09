import * as React from "react";

import { Scrolly } from "@/components/story/scrolly";
import type { EssayData } from "@/lib/apportionment/essay-data";

import { ActFourSteps, actFourHouseSteps } from "./act-four";
import { ActOneSteps, actOneHouseSteps } from "./act-one";
import { ActThreeSteps, actThreeHouseSteps } from "./act-three";
import { ActTwoSteps, actTwoHouseSteps } from "./act-two";
import { HouseStageFigure } from "./house-stage";

/**
 * Acts I to IV on one stage: a single pinned figure carries the reader
 * from one person to a seat, through the House's growth, to its freeze and
 * what the freeze has done to a seat, then deals the seats out again and
 * asks whether more of them would help, so the chamber never leaves the
 * screen between acts. Each act supplies its words (scrolly steps) and, in
 * the same order, what the figure shows at each.
 */
export function HouseStory({ data }: { data: EssayData }) {
  const present = data.history[data.history.length - 1];
  const nationalAverage = Math.round(data.totalPopulation / present.houseSize);
  const houseSteps = [
    ...actOneHouseSteps(data),
    ...actTwoHouseSteps(data),
    ...actThreeHouseSteps(),
    ...actFourHouseSteps(),
  ];

  return (
    <Scrolly
      label="From one person to one seat in the House, the House across its history, its freeze at 435 seats, how those seats are dealt, and what a bigger House would change"
      layout="stage"
      graphic={
        <HouseStageFigure
          seats={present.stateSeats}
          order={data.westToEast}
          nationalAverage={nationalAverage}
          history={data.history}
          houseSteps={houseSteps}
          stage
        />
      }
    >
      <ActOneSteps data={data} nationalAverage={nationalAverage} />
      <ActTwoSteps data={data} />
      <ActThreeSteps data={data} />
      <ActFourSteps />
    </Scrolly>
  );
}
