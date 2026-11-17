# Contributing to vpp-mcp

Thanks for helping. The README and `docs/` are in Polish; issues and pull requests may be written in Polish or English.

## Reporting bugs and requesting features

Use the [issue forms](https://github.com/Nikodem5/vpp-mcp/issues/new/choose):

- **Bug report**: include the vpp-mcp version (`python -m pip show vpp-mcp`), your Visual Paradigm version, OS, MCP client, the prompt or tool call you used, and the logs/error text.
- **Feature request**: describe the problem or use case first, then the solution you have in mind.

**Do not attach confidential or graded coursework `.vpp` files to public issues or PRs.** Share a minimal reproduction instead: a small new project (or a few classes) that still shows the problem.

## Contributing code

1. Fork the repository and create a branch from `main`.
2. Set up the environment (Python 3.10+):

   ```
   python -m pip install -e . pytest
   ```

3. Make your change and run the tests:

   ```
   python -m pytest -q
   ```

   Tests that need a real Visual Paradigm project are skipped unless you point them at one:

   ```
   VPP_SAMPLE=path/to/project.vpp python -m pytest -q
   ```

   (On Windows PowerShell: `$env:VPP_SAMPLE = "path\to\project.vpp"`.) The sample is only read, never modified.
   `tests/smoke_test.py` works on any `.vpp` with a class diagram: `python tests/smoke_test.py path/to/project.vpp`. It writes an edited copy to the temp directory and prints its path.

4. Open a pull request against `main`.

`docs/` describes the `.vpp` format (SQLite container, DEFINITION syntax, class and sequence diagrams). Read it before changing anything that writes files, and update it if you learn something new about the format.

## Pull request expectations

- Keep PRs small and focused: one change per PR.
- Describe what changed and why, and how you verified it.
- Format correctness is verified in Visual Paradigm itself, not only by tests. If your change affects the `.vpp` files the server produces, open the result in Visual Paradigm, save it (Ctrl+S), and state which VP version you used.
- Add or update tests where practical. Add a sample-based test if it needs `VPP_SAMPLE`; it must skip cleanly without it.
- Do not edit generated or ignored files (`build/`, `*.egg-info/`, `*.vpp`).

## Review and merging

`main` is protected, so all changes go through a pull request. The maintainer (Nikodem5) reviews and merges every PR.

## License

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
