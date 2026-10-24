# Reproducible SMT evidence

Use `make formal-check` from the project root. It checks pinned source files
and executes the Z3 solver, emitting individual `.smt2` queries and JSON proof
results. For independent inspection, run any emitted SMT-LIB2 file with
`z3 -smt2 <file>`; counterexample-free safety queries should print `unsat`.
The intentional mutation case should print `sat`.

Source pins identify the files associated with model review. Coverage and
frontend assumptions are described in `docs/FORMAL_VERIFICATION.md`.
