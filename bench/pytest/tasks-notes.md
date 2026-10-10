## Notes for every task

- Where an issue leaves a design choice open, choose the simplest reasonable design that fits pytest's existing options and style, and say what you chose in the commit message.
- Run tests with `.venv/Scripts/python -m pytest` (Windows). The environment is already installed. The full suite is `.venv/Scripts/python -m pytest testing -q -n 8` and takes about 7 minutes.
- Before any change, these already fail on this machine and are out of scope; the bar is no new failures:
  testing/python/raises.py::TestRaises::test_raises_with_invalid_regex, testing/acceptance_test.py::TestInvocationVariants::test_pydoc, and testing/test_legacypath.py::test_cache_makedir (error).
- Add a changelog fragment in `changelog/` for each change, as pytest's contributing guide asks.
