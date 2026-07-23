# Model validation record

## Automated mechanical checks

The deterministic runner checks that:

1. the specification is bound to the exact input bytes;
2. every transition row is complete and sums to one;
3. death is absorbing;
4. costs are non-negative and utilities are within zero and one;
5. cohort mass is conserved through every cycle;
6. the exact base-case result is byte-reproducible.

These checks verify implementation arithmetic and file integrity only.

## Human review still required

- face validity of the disease process and treatment pathway;
- relevance and completeness of included states and events;
- appropriateness of the cycle length, horizon, discounting, and reward timing;
- selection, applicability, and uncertainty of every parameter source;
- plausibility of scenario and uncertainty assumptions;
- independent review of structure, implementation, results, and interpretation.

Independent validation has not been performed.
