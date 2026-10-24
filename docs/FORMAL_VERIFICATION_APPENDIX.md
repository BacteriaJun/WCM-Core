# Additional model evidence

The 32-query suite includes `TIME_OVERFLOW_TO_FAILED`, `TIME_NO_WRAP_AT_LIMIT`,
`TIME_OVERFLOW_NO_REPORT` and `TIME_RESET_ZERO`. These quantify over 16-bit
elapsed values and Boolean inputs in the synchronous transition specification.
Physical pulse capture, reset timing, sensor validity and settlement provenance
are target-frontend assumptions.

`test_c_mission_differential.py` compares C17, Python and the Film behavioral
oracle using 6,000 raw images, 1,000 valid missions, 8,000 scheduling comparisons
and 8,192 single-bit perturbations. These sampled comparisons detect model
drift alongside the symbolic specification checks.
