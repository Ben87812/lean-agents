## Notes for every task

- Run tests with `.venv/Scripts/python -m pytest` (Windows). The environment is already installed.
- Before any change, these 8 tests already fail on this machine (rendering differences unrelated to these bugs). They are out of scope; the bar is no new failures:
  tests/test_card.py::test_card_render, tests/test_markdown.py::test_inline_code_in_table_cells, and six in tests/test_syntax.py (test_python_render, test_python_render_simple, test_python_render_simple_passing_lexer_instance, test_python_render_indent_guides, test_option_no_wrap, test_syntax_highlight_ranges).
