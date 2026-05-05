/**
 * 2020 census apportionment populations, FIPS-keyed.
 *
 * Mirror of `districting/data/apportionment_2020.py` for the TS side.
 * Used by the state detail page to show "avg. district size" without
 * round-tripping to the Python API for static reference data.
 *
 * Source: US Census Bureau, "Apportionment Population and Number of
 * Representatives by State: 2020 Census" (released April 26, 2021).
 *
 * If these numbers ever drift, the regression test on the Python side
 * (`districting.tests.test_apportionment.TestRegression2020Apportionment`)
 * is the source of truth — keep this dict in sync with the Python file.
 */

export const US_2020_APPORTIONMENT_POPULATIONS: Readonly<Record<string, number>> = {
  "01": 5_030_053, // Alabama
  "02": 736_081, // Alaska
  "04": 7_158_923, // Arizona
  "05": 3_013_756, // Arkansas
  "06": 39_576_757, // California
  "08": 5_782_171, // Colorado
  "09": 3_608_298, // Connecticut
  "10": 990_837, // Delaware
  "12": 21_570_527, // Florida
  "13": 10_725_274, // Georgia
  "15": 1_460_137, // Hawaii
  "16": 1_841_377, // Idaho
  "17": 12_822_739, // Illinois
  "18": 6_790_280, // Indiana
  "19": 3_192_406, // Iowa
  "20": 2_940_865, // Kansas
  "21": 4_509_342, // Kentucky
  "22": 4_661_468, // Louisiana
  "23": 1_363_582, // Maine
  "24": 6_185_278, // Maryland
  "25": 7_033_469, // Massachusetts
  "26": 10_084_442, // Michigan
  "27": 5_709_752, // Minnesota
  "28": 2_963_914, // Mississippi
  "29": 6_160_281, // Missouri
  "30": 1_085_407, // Montana
  "31": 1_963_333, // Nebraska
  "32": 3_108_462, // Nevada
  "33": 1_379_089, // New Hampshire
  "34": 9_294_493, // New Jersey
  "35": 2_120_220, // New Mexico
  "36": 20_215_751, // New York
  "37": 10_453_948, // North Carolina
  "38": 779_702, // North Dakota
  "39": 11_808_848, // Ohio
  "40": 3_963_516, // Oklahoma
  "41": 4_241_500, // Oregon
  "42": 13_011_844, // Pennsylvania
  "44": 1_098_163, // Rhode Island
  "45": 5_124_712, // South Carolina
  "46": 887_770, // South Dakota
  "47": 6_916_897, // Tennessee
  "48": 29_183_290, // Texas
  "49": 3_275_252, // Utah
  "50": 643_503, // Vermont
  "51": 8_654_542, // Virginia
  "53": 7_715_946, // Washington
  "54": 1_795_045, // West Virginia
  "55": 5_897_473, // Wisconsin
  "56": 577_719, // Wyoming
};
