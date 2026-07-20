# Basalt MVP v1.5 Demo Script

1. Run `basalt demo`.
2. Show `demo_good` verified.
3. Show `demo_weak` had passing tests but weak proof.
4. Open the mutation section: `age >= 18` became `age > 18`, and the test suite missed it.
5. Show Basalt generated boundary tests.
6. Show before/after proof comparison: weak proof became verified.
7. Show `demo_policy_violation` blocked by policy because secrets are not allowed.
8. End with: "Basalt does not just generate code. Basalt proves whether the software can be trusted."
