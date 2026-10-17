# Known limitations

- **Python only.** Other languages in a diff are listed but not analyzed.
- **Static analysis misses runtime wiring:** `getattr()`, dictionaries of functions, plugin registries, dependency injection, monkey-patching, and method calls on objects whose type is unknown (`obj.save()`). These are reported as unresolved calls where detectable. Benchmark scenario 08 shows this blind spot (recall 0 for that scenario).
- **Local variables can shadow names.** A parameter named like a top-level function may create a false link.
- **Shortest path only.** Each dependent shows one shortest path; other paths exist but are not listed.
- **Priority is structural.** It ranks where to look first, not how likely a bug is.
- **Model reasoning is a hypothesis.** Evidence citations are validated; the explanation itself is not. A test run is the only confirmation the tool offers.
- **Context budget.** Large changes may not fit; omitted symbols are listed in the report.
- **Test execution** needs pytest and the repository's dependencies in the same Python environment as the app, and is not sandboxed.
- **Benchmark size.** Ten small synthetic scenarios show behaviour on known patterns; they do not measure accuracy on real-world repositories.
- **Not verified live in the build environment.** The Gemma 4 integration follows the official documentation and is tested against a simulated client; the first live call happens on your machine.
