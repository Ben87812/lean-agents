# Tasks: five open Rich bugs

## Issue #4234: [BUG] Text.wrap(console, width=0) raises ValueError in chop_cells (range step 0)

**Describe the bug**

`Text.wrap(console, width=0)` raises `ValueError: range() arg 3 must not be zero` for ordinary (single-cell) text. The same call with double-width text does not crash, so the behaviour is inconsistent.

The crash is in `rich/cells.py::chop_cells`, whose single-cell fast path builds `range(0, len(text), width)`:

```python
if _is_single_cell_widths(text):
    return [text[index : index + width] for index in range(0, len(text), width)]
```

With `width == 0` the step is `0`, which `range` rejects. The general (wide-character) path below it has no such step and returns without raising, so `chop_cells("hello", 0)` crashes while `chop_cells("你好", 0)` does not.

It reaches the public API through `Text.wrap` -> `_wrap.divide_line` -> `chop_cells` (the `word_length > width` fold branch, taken by any non-empty word when `width` is 0). Width 0 is reachable when text is rendered into a zero-interior region (a table column squeezed to zero, a nested panel with no room, a console sized to 0); Rich otherwise degrades gracefully at tiny widths, so a hard crash here stands out.

**Minimal repro** (runs as-is):

```python
import io
from rich.console import Console
from rich.text import Text

console = Console(file=io.StringIO())
Text("hello world").wrap(console, 0)   # ValueError: range() arg 3 must not be zero
```

Lower-level, showing the single-cell vs wide-char inconsistency:

```python
from rich._wrap import divide_line
divide_line("hello", 0)   # ValueError: range() arg 3 must not be zero
divide_line("你好", 0)     # returns normally
```

Traceback:

```
  File ".../rich/text.py", line 1239, in wrap
    offsets = divide_line(str(line), width, fold=wrap_overflow == "fold")
  File ".../rich/_wrap.py", line 59, in divide_line
    folded_word = chop_cells(word, width=width)
  File ".../rich/cells.py", line 338, in chop_cells
    return [text[index : index + width] for index in range(0, len(text), width)]
ValueError: range() arg 3 must not be zero
```

**Suggested fix**

Guard `chop_cells` against a non-positive width (return `[text]` when `width <= 0`, since text cannot be chopped into zero-width lines). That removes the crash and also fixes the wide-character path, which for `width == 0` currently returns a surprising `["", "你", "好"]`. I am happy to open a PR with the guard and a regression test.

- [x] I've checked docs and closed issues for possible solutions.
- [x] I can't find my issue in the FAQ.

**Platform**
<details>
<summary>Click to expand</summary>

Reproduced on Rich `master` (commit 9d8f9a3, declared version 15.0.0), Python 3.10, Windows — but the code path is platform-independent (pure width arithmetic).
</details>


## Issue #4214: [BUG] `Columns(width=...)` raises `ZeroDivisionError` when the requested width does not fit

- [x] I've checked [docs](https://rich.readthedocs.io/en/latest/introduction.html) and [closed issues](https://github.com/Textualize/rich/issues?q=is%3Aissue+is%3Aclosed) for possible solutions.
- [x] I can't find my issue in the [FAQ](https://github.com/Textualize/rich/blob/master/FAQ.md).

<!-- 
WAIT! Is this a feature request?

Rich isn't accepting new features. If it can be implemented in a third-party library, then that is what I recommend.

Rich *may* accept enhancements to existing features, if they don't have a disruptive impact on the API.

If you think your feature is exceptional, then please make your case in a discussion.
-->

**Describe the bug**


With the default padding `(0, 1)`, `width_padding` is `1`. If the available console width is no greater than `width + 1`, this calculation returns `0`. This will result in an error.
This bug might be related to the following code in `rich\columns.py` within rich.
```
def __rich_console__:
       ...
        if self.width is not None:
            column_count = (max_width) // (self.width + width_padding)
```
 `__rich_console__`  then passes `column_count` to `iter_renderables`, which evaluates `item_count % column_count` and raises `ZeroDivisionError`.

**Reproduction**
```python
from io import StringIO

from rich.columns import Columns
from rich.console import Console

console = Console(
    file=StringIO(),
    width=16,
    height=24,
    force_terminal=True,
    color_system=None,
    highlight=False,
)
print("size", console.width, "x", console.height)
console.print(Columns([f"file_{i:02d}.txt" for i in range(8)], width=16))
```

Observed:

```
size 16 x 24
Traceback (most recent call last):
  File "/home/test01.py", line 15, in <module>
    console.print(Columns([f"file_{i:02d}.txt" for i in range(8)], width=16))
  File "/home/rich/rich/console.py", line 1731, in print
    extend(render(renderable, render_options))
  File "/home/rich/rich/console.py", line 1339, in render
    for render_output in iter_render:
  File "/home/rich/rich/columns.py", line 145, in __rich_console__
    _renderables = [
                   ^
  File "/home/rich/rich/columns.py", line 115, in iter_renderables
    if item_count % column_count:
       ~~~~~~~~~~~^~~~~~~~~~~~~~
ZeroDivisionError: integer modulo by zero
```

Same function, zero divisor (optional second case):

```python
console.print(Columns(["alpha", "beta"], width=0, padding=0))
```

```
  File "/home/rich/rich/columns.py", line 124, in __rich_console__
    column_count = (max_width) // (self.width + width_padding)
                   ~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ZeroDivisionError: integer division or modulo by zero
```

**Platform**
- Python version: 3.12.3
- Rich version: 15.0.0 (`9d8f9a37`)
- Linux x86_64



## Issue #4216: Console.print(text) silently drops Text's own justify unless justify= is also passed to print()

**AI disclosure (per AI_POLICY.md):** this was investigated and written with the assistance of Claude (Anthropic). I independently reproduced it against a fresh clone of `main` myself before filing — repro below, runnable standalone, no dependencies beyond Rich itself.

## Summary

A `Text` object's own `.justify` attribute is silently dropped when the `Text` is passed directly as a top-level argument to `Console.print()`, unless `justify=` is *also* passed to `print()` itself — even though `Text.__rich_console__` documents/implements `self.justify` as taking priority over the console-level default.

## Reproduction

```python
from rich.console import Console
from rich.text import Text
import io

buf1 = io.StringIO()
Console(file=buf1, width=20).print(Text("hi", justify="center"))
print(repr(buf1.getvalue()))
# -> 'hi\n'                    <- not centered, despite Text's own justify="center"

buf2 = io.StringIO()
Console(file=buf2, width=20).print(Text("hi", justify="center"), justify="center")
print(repr(buf2.getvalue()))
# -> '         hi         \n'  <- only works if justify is ALSO passed to print()
```

## Root cause

`Console._collect_renderables()` (`rich/console.py:1550-1554`, inside `check_text()`) funnels every `Text` object through:
```python
sep_text = Text(sep, justify=justify, end=end)   # justify = print()'s own kwarg, default None
append(sep_text.join(text))
```
`Text.join()` (`rich/text.py:788`) builds the merged result via `self.blank_copy()`, where `self` is the *separator* `sep_text` — so the joined result inherits the **separator's** `justify`/`overflow`/`no_wrap`, silently clobbering whatever the joined-in `Text`'s own `.justify` was set to.

The same `Text` object centers correctly when wrapped in `Panel(...)` or `Group(...)`, because those containers call `console.render()` on the inner `Text` directly, bypassing this join path — so the bug is specific to passing a `Text` as a direct top-level argument to `Console.print()`.

## Checked

`gh search issues --repo Textualize/rich` for "justify" (30+ related hits reviewed) — found related-but-distinct issues (#460 `console.log` missing a `justify` kwarg entirely, fixed 2020; #3948/#4021 `Table` title justify with `soft_wrap`) but nothing matching this specific "`Text.justify` silently dropped by `print()`" defect. Appears unreported.

Happy to put together a PR (something like: preserve the joined item's own `justify`/`overflow`/`no_wrap` when it's a single `Text` and `print()`'s own `justify` wasn't explicitly passed) if this is confirmed as worth fixing.


## Issue #4225: [BUG] Traceback rendering fails on ParseError with a non-string message

- [x] Checked the traceback documentation and searched open/closed issues for `SyntaxError`, `ParseError`, and `ExpatError`.
- [x] Checked the FAQ.

**Describe the bug**

Rendering an `xml.etree.ElementTree.ParseError` whose message is an `ExpatError` raises a secondary `TypeError`, masking the original XML parse error. This occurs with the pure-Python ElementTree parser used by defusedxml (see tiran/defusedxml#105). The reproduction below needs only Rich and the standard library:

```python
import io
import sys
from xml.etree.ElementTree import ParseError
from xml.parsers.expat import ExpatError

from rich.console import Console
from rich.traceback import Traceback

try:
    raise ParseError(ExpatError("syntax error"))
except ParseError:
    Console(file=io.StringIO()).print(Traceback.from_exception(*sys.exc_info()))
```

Actual result:

```text
TypeError: str or Text instance required, not ExpatError('syntax error')
```

Expected: render the original exception without raising a new exception.

`ParseError` subclasses `SyntaxError`. `Traceback.extract()` currently stores `exc_value.msg` directly in `_SyntaxError`, although it already has a `safe_str()` helper for the main exception value. Would normalizing this field with that helper, with tests for non-string messages and a failing `__str__`, be an acceptable fix?

**Platform**

macOS arm64, CPython 3.13.5, Rich 15.0.0. Also reproduced using the current `main` checkout. Output is directed to `StringIO`, so no terminal-specific rendering is involved. The original end-to-end example also fails with defusedxml 0.8.0rc2 and structlog 26.1.0. Explicitly selecting `structlog.dev.plain_traceback` is a verified workaround for that integration.

This report and local reproduction were prepared with OpenAI Codex. Per the AI policy, no PR is being submitted without maintainer approval of the proposed solution.


## Issue #4215: [BUG] `export_svg()` generates a dangling clip-path reference for the last line

- [x] I've checked [docs](https://rich.readthedocs.io/en/latest/introduction.html) and [closed issues](https://github.com/Textualize/rich/issues?q=is%3Aissue+is%3Aclosed) for possible solutions.
- [x] I can't find my issue in the [FAQ](https://github.com/Textualize/rich/blob/master/FAQ.md).

<!-- 
WAIT! Is this a feature request?

Rich isn't accepting new features. If it can be implemented in a third-party library, then that is what I recommend.

Rich *may* accept enhancements to existing features, if they don't have a disruptive impact on the API.

If you think your feature is exceptional, then please make your case in a discussion.
-->

**Describe the bug**

`Console.export_svg()` generates a `clip-path` reference for each line of text, but does not emit the corresponding `<clipPath>` definition for the final line. 
For example, a three-line recording contains references to `line-0`, `line-1`, and `line-2`, while the `<defs>` section only defines `line-0` and `line-1`. 
This might be due to `Console.export_svg()`.  After iterating over `N` lines, `y` is `N - 1`, but `line_offsets = [line_no * line_height + 1.5 for line_no in range(y)]`(in `\rich\console.py` line 2540)  stops at `N - 2`.

**Reproduction**
```python
import re
from io import StringIO

from rich.console import Console

console = Console(
    file=StringIO(),
    record=True,
    width=40,
    height=10,
    force_terminal=True,
    color_system=None,
    highlight=False,
    markup=False,
)
console.print("alpha")
console.print("bravo")
console.print("charlie")
svg = console.export_svg(clear=False, title="poc")

ids = re.findall(r'<clipPath id="([^"]+-line-\d+)"', svg)
refs = sorted(set(re.findall(r'clip-path="url\(#([^"]+-line-\d+)\)"', svg)))
print("clipPath ids:", ids)
print("clip-path refs:", refs)
print("dangling:", sorted(set(refs) - set(ids)))
```

Output:

```
clipPath ids: ['terminal-3078692677-line-0', 'terminal-3078692677-line-1']
clip-path refs: ['terminal-3078692677-line-0', 'terminal-3078692677-line-1', 'terminal-3078692677-line-2']
dangling: ['terminal-3078692677-line-2']
```


**Platform**
- Python version: 3.12.3
- Rich version: 15.0.0 (`9d8f9a37`)
- Linux x86_64


