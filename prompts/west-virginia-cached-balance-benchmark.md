# West Virginia: cached connectivity checks and a larger balancing budget

The new three-district continuation passes independent strict shared-edge graph and unsimplified polygon validation. Its maximum population deviation is **0.667 people (0.00011150%)**, after **721 additional boundary moves** from the original connected endpoint. It stopped at `local_optimum`.

[Comparison and measured trace](http://127.0.0.1:8770/corrections/west-virginia-cached-balance-v1/) · [Validated corrected map](http://127.0.0.1:8770/corrections/west-virginia-cached-balance-v1/states/54/districts-3/) · [Original map](http://127.0.0.1:8770/states/54/districts-3/) · [Preserved diagnosis](http://127.0.0.1:8770/diagnostics/west-virginia/)

| Assignment | Additional moves after original endpoint | District populations | Maximum deviation |
|---|---:|---|---:|
| Original connected plan | 0 | 597,919 / 584,431 / 611,366 | 13,474.333 people (2.25358975%) |
| Preserved diagnostic probe | 100 | 597,919 / 586,313 / 609,484 | 11,592.333 people (1.93882421%) |
| Validated cached continuation | 721 | 597,906 / 597,905 / 597,905 | 0.667 people (0.00011150%) |

All **72,558 source blocks and 1,793,716 residents** remain assigned exactly once. Every final district has one physical shared-edge graph component and one valid unsimplified polygon. Source coverage and original district-union coverage are preserved exactly, with no water connections, source-geometry edits or new numerical power-diagram solve.

The endpoint **attains the integer-population arithmetic lower bound of 2/3 person** from the fractional ideal. District populations are the floor/ceiling values 597,905 and 597,906, with a range of 1 resident. No integer district populations can have a smaller maximum deviation. This certifies the best possible maximum population balance for this total/count, not globally optimal compactness or other districting objectives.

## Controlled 100-move comparison

Both verification runs start from the same original 1,000-move endpoint in serial fresh processes, using the same source, candidate ordering, move budget and current code. The only mode difference is cached versus traversal donor-connectivity checks. Every ordered move, final block assignment and stop reason matches, including the preserved diagnostic probe. The longer continuation reproduces this verified 100-move prefix.

| Mode | Balancing only | Full verification process pipeline | Peak process working set |
|---|---:|---:|---:|
| Traversal checks | 240.280 s | 244.291 s | 198.0 MiB |
| Cached checks | 9.564 s | 13.491 s | 198.3 MiB |

The measured balancing-only speedup is **25.12×** on this matched 100-move case. This is one serial measurement per mode, not a repeated statistical benchmark or a nationwide speedup claim. The earlier diagnostic probe took 244.189 s with guard profiling enabled and is retained separately; it is not the denominator of this fresh speedup comparison.

The cache records district membership and exact articulation points. Both donor and recipient caches are invalidated after each transfer. It changes how connectivity is checked, not the candidate ordering, population objective or whole-block/shared-edge constraints. The objective remains lexicographic: first maximum absolute population deviation, then squared deviations.

## Larger continuation and runtime

The new budget allows 10,000 additional moves, with 500-move checkpoints. The run used 721, giving 1,721 balancing moves including the original 1,000. The continuation starts afresh from the original endpoint; the earlier 100-move verification is not added to it.

| Measured stage | Wall time |
|---|---:|
| New balancing work | 64.689 s |
| New strict polygon validation and map export | 195.252 s |
| Exact old/new district-union comparison | 4.805 s |
| Complete correction pipeline | 269.759 s |

The corrected run's peak process working set is **671.2 MiB**. The original pipeline took 1797.681 s, including a 3.963 s power solve and 1598.964 s for repair plus balancing. Those original two-worker timings and the new continuation cover different work; their ratio is not a controlled algorithm-speedup result. Parent elapsed time across the three fresh child processes is 533.459 s.

## Delivered map and validation

- National outlines: 79,364 gzip bytes.
- State entry plus detail index: 480,793 gzip bytes.
- All county detail shards: 62,584,808 gzip bytes.
- Largest county shard: 3,308,832 gzip bytes.

Independent summary validation checked original DBF populations, exact move replay and objective progress, source graph identity, final district graph connectivity, every full-resolution district against its assigned source blocks, original and source union preservation, all county feature geometries/populations/labels, and 58 compressed payloads. All recorded processes exited; the state54 lock was acquired during validation.

All 304 protected original/diagnostic files remain byte-identical. The original failed diagnostic audit and geometry-only finalization remain preserved. Historical runtime hashes are not assumed to equal current code; the current matched mode comparison and saved pre-cache source snapshot establish the narrower provenance. The existing K2 legacy inner-optimizer warning is unchanged and no K2 rerun was performed.

Prelaunch test evidence is preserved separately from this follow-up: Prelaunch districting and script regressions: 1582 passed in 37.16 seconds. Separate summary regressions: 41 passed. Browser QA is recorded separately from the numerical and artifact audit. Independent summary validation took 176.829 s and is not included in the benchmark pipeline measurements. These offline block maps do not replace the app's cached tract plans.
