# Contributing

Issues and pull requests are welcome.

1. Fork the repository and create a focused branch.
2. Keep paid API calls out of automated tests.
3. Install report dependencies with `python -m pip install -r requirements-report.txt`, then run `pnpm check` before opening a pull request. CI tests Python 3.10 and 3.12 on Windows and Linux.
4. Document changes to billing estimates, matching behavior, or output formats.
5. Never commit credentials, private prospect lists, or unreviewed raw API responses.

By contributing, you agree that your contribution is licensed under the MIT License.

Report changes require generated synthetic examples and visual inspection in addition to automated layout checks. Exercise at least two contrasting business profiles, long titles and narratives, incomplete observations, and arbitrary query counts. Keep real client records and generated proof artifacts out of the public source tree. Recommendations must identify their supporting observations and distinguish a hypothesis from an established finding. Never infer business outcomes from sampled rank shares.
