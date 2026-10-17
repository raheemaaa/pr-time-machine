# Two-minute demo script

**0:00 Problem.** "A pull request changes one function. Tests for that function pass. But five other places use it. Which ones break? Diff viewers can't tell you, and connected doesn't mean broken."

**0:20 Run it.** Built-in sample → Analyze. "This PR switches `calculate_total` from percent discounts to fractions. The AST engine found one changed symbol, a signature change, and five dependents, each with a file and line."

**0:45 Map.** Open Dependency map. "Every arrow is a proven static link. Static analysis says all four callers are high priority, because it can't read intent."

**1:05 Gemma 4.** Open Findings. "Gemma 4 reads each call site and the before/after code. Checkout passes the old keyword, so it crashes. Refunds passes 10, which now means 1000%. Invoices and reports never pass a discount, so they're likely unaffected. Every file and line Gemma cites was checked against the repo. Anything it claims without a dependency path is labelled not verified."

**1:30 Proof.** Local Git repo with tests enabled → Test plan. "We ran the real tests at both revisions. Three tests newly fail: exactly the paths through checkout and refunds. Static analysis alone flagged 5 tests (60% precision); here's what the Gemma verdicts flagged."

**1:50 Open source.** "MIT-licensed engine, a 10-scenario benchmark with real results, 41 tests, and a provider interface so the open-weight Gemma model can run locally for private code."
