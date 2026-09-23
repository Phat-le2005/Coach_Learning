# Math 12 real-data audit

Status: **DATA-MATH12-001 started**

## Source baseline

The Grade 12 Mathematics baseline is the Ministry-issued Mathematics curriculum attached to Circular 32/2018/TT-BGDĐT. Currentness was checked against Circular 17/2025/TT-BGDĐT; that amendment does not amend Mathematics.

The canonical source inventory is stored in `backend/data/provenance/sources.json`.

## Confirmed Grade 12 core scope

The official Grade 12 core scope contains:

- Applications of derivatives to function analysis and graphing.
- Antiderivatives and integrals.
- Coordinate methods in three-dimensional geometry.
- Dispersion measures for grouped data.
- Conditional probability, total probability and Bayes-related rules.
- Software-supported mathematical practice and experiential activities.

Grade 12 also has optional study topics covering discrete random variables, optimization and financial applications.

## Existing prototype dataset: do not treat as verified

The current files under `backend/data/curriculum/math/grade12/gdpt2018/` predate this source audit and are still prototype taxonomy.

Important mismatches/gaps to resolve in DATA-MATH12-002:

1. `EXPONENTIAL_LOGARITHM` is not part of the verified Grade 12 core scope recorded in the official Grade 12 section.
2. `PROBABILITY_CHAPTER` is too generic for Grade 12; the verified core scope is conditional probability plus total-probability/Bayes rules.
3. The official Grade 12 statistics scope on grouped-data dispersion is missing from the current prototype hierarchy.
4. The derivative area is too shallow: maxima/minima, asymptotes, graph survey and real-world applications need explicit coverage.
5. The coordinate-geometry area must cover vector coordinates, planes, lines, angles/distances and spheres.
6. Current `ProblemType`, `Concept`, prerequisite and weight mappings are internal derived data and must be rebuilt/reviewed separately.

## Data integrity rule

Do not modify `verified_at` in the importable curriculum manifest until the derived Coach Learning taxonomy has been reviewed against this official scope.

## Next task

`DATA-MATH12-002` will create the **Coach Learning derived taxonomy** for the first official area only:
`Ứng dụng đạo hàm để khảo sát và vẽ đồ thị của hàm số`.

That task must label all ProblemTypes, Concepts, prerequisite edges and weights as derived/internal rather than Ministry-issued data.
