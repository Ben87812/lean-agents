# Tasks: four open pytest feature requests

## Issue #13580: Support OSC 8 hyperlinks

<!--
Thanks for suggesting a feature!

Quick check-list while suggesting features:
-->

#### What's the problem this feature will solve?
<!-- What are you trying to do, that you are unable to achieve with pytest as it currently stands? -->
Being able to quickly open any file mentioned when a test fails or crashes.

#### Describe the solution you'd like
<!-- A clear and concise description of what you want to happen. -->
Terminal emulators now have hyperlinks! 🎉🎉🎉

It's supported by most terminal emulators, as well as application like `ls` and `less`:  
https://github.com/Alhadis/OSC8-Adoption/

`pytest` should have a new `--hyperlinks` command line option, similar to the one that [`ls` now has](https://www.gnu.org/software/coreutils/manual/html_node/General-output-formatting.html#index-_002d_002dhyperlink).

All paths in `pytest`'s output should be links when this option is turned on (which it should be by default, IMO. Terminal emulators that don't support hyperlinks fail gracefully (the escape sequences and the target URL are simply ignored)).

<!-- Provide examples of real-world use cases that this would enable and how it solves the problem described above. -->
Then you can configure your terminal emulator / tmux to open the link in your favorite text editor / IDE.


### Discussion (each comment cut to 800 characters)

- Hi! I’d like to work on this issue. I’m new to open source but happy to help improve the docs. Let me know if it’s okay to proceed.

- Hi @candresz,

>  Let me know if it’s okay to proceed.

In general, unless someone specifically mentioned that they were working in an issue, feel free to start on any issue you like.

>  but happy to help improve the docs

Note, however, that this issue is about adding a new future, not to only improve the docs (but updating the docs will certainly part of it).

 

- Thanks for the clarification @nicoddemus 

I'm new to open source, so I wanted to start by contributing to the docs. I'm happy to adjust this PR or move it to a different place if needed. Let me know what's best.


- > so I wanted to start by contributing to the docs

Sorry, do you mean to the docs of *this issue*, or docs *in general*? Note that this issue has no work in progress yet, so it is difficult to provide docs for it.

But if you are asking in a general manner, we have a [`docs label`](https://github.com/pytest-dev/pytest/issues?q=state%3Aopen%20label%3A%22type%3A%20docs%22) that you can use to search for documentation-related issues. 👍 

- Thanks for the clarification @nicoddemus 
I now understand that this issue is about a future feature, so it's not the best fit for a docs-only contribution. I'll take a look at other open issues with the `docs` label. Appreciate the help!


## Issue #13169: Add "pre setup" log entry when enabling "--show-setup"

#### What's the problem this feature will solve?

I've spent a long time trying to debug a fixture that was interacting with the environment and got stuck because the subprocess was trying to read from the PTY (It spawned an SSH that accidentally asked for host key verification) and it's been really hard trying to figure out what was going on (read: 4-6hs spent debugging this). Due to further environmental restrictions (being run in a NixOS vm test environment) I also had a hard time using strace not giving me relevant output.

I started with the process being stuck in collection (but this was an IO buffering issue) and then noticed that it's likely stuck while setting up some fixture. When using `--show-setup` I noticed that this only reports on the success of a fixture - I would have needed to get info which fixture is currently being set up.

#### Describe the solution you'd like

I'd like to add more output (maybe introducing the `-vvv` level if this becomes too verbose for the `-vv` level) that shows a "PRESETUP" stage (or something similar) before calling the setup of a fixture.

This would have allowed me to more quickly pinpoint where my code is going wrong.

#### Alternative Solutions

I normally have pytest-timeout report those kinds of things to me, but for some reason it didn't trigger here. If it did trigger then it would have shown me the subprocess call which is stuck. We could ask the pytest-timeout authors whether they could take a look at that behaviour, too.

#### Additional context

I'd be happy to work on the PR if this is interesting.

### Discussion (each comment cut to 800 characters)

- Thanks for bringing this to attention 

Getting the currently under setup fixture indicated before it's completed is most helpful the moment one thinks about any larger scoped expensive fixture 

- So, what's the way you'd like this to be built? Is another level of -vvv good or would you rather see start/stop output always when running --setup-show? Multiple lines or a single line?

I'm kinda inclined to go with multiple lines, as I'm a bit afraid of line buffering in the cases I'm dealing with ... (so alternatively calling explicit flushes would be fine I guess).

- This needs some bikeshedding as I haven't been able to make time for this


I'm still down with a flu 

- No worries, I'm fighting through my current issues with some print debugging ... please get well first. We can figure this out when you're back!

## Issue #13198: assertion introspection is missing when pytest produces a diff

```py
def get_data(last):
    return [1, 2, last]

def test_list_compare():
    assert [1, 2, 3] == get_data(2)

def test_int_compare():
    assert 1 == get_data(2)
```
```
> uv run pytest tests
...
======================== FAILURES ==============================================
____________________________ test_list_compare __________________________________

    def test_list_compare():
>       assert [1, 2, 3] == get_data(2)
E       assert [1, 2, 3] == [1, 2, 2]
E         
E         At index 2 diff: 3 != 2
E         
E         Full diff:
E           [
E               1,
E               2,
E         -     2,
E         ?     ^
E         +     3,
E         ?     ^
E           ]

tests\test_it.py:5: AssertionError
______________________________ test_int_compare _______________________________

    def test_int_compare():
>       assert 1 == get_data(2)
E       assert 1 == [1, 2, 2]
E        +  where [1, 2, 2] = get_data(2)

tests\test_it.py:8: AssertionError
```

while this minification doesn't represent an actual use-case, only the issue in question, there are many cases where the diff of the lists is not as useful to me as the breakdown of how it came to be, could there be a verbosity option to display both the diff, and the breakdown?

### Discussion (each comment cut to 800 characters)

- Not sure I follow, are you referring to the `+  where [1, 2, 2] = get_data(2)` missing in the first case?

- yes, exactly. "assertion introspection" was the name for this feature that I could find in the docs

## Issue #14063: short test summary should be short, even for higher verbosity

<!--
Thanks for submitting an issue!

Quick check-list while reporting bugs:
-->

- [x] a detailed description of the bug or problem you are having
- [x] output of `pip list` from the virtual environment you are using
- [x] pytest and operating system versions
- [x] minimal example if possible

By default, pytest shows the error message even in the "short test summary", which - at least for the libraries that I'm working with - often blows up the lengths of the summary to the point that it becomes useless. Here's a recent example from numpy where 17 test failures cause >900 lines of "short summary".

<details>
<summary>default short test summary</summary>

```
=========================== short test summary info ============================
FAILED linalg/tests/test_linalg.py::TestSolve::test_generalized_sq_cases - AssertionError: In test case: <LinalgCase: single_tile213_stride_+1_+1_+3_+1_stride_+1_+1_+1_+1>
Traceback (most recent call last):
  File "$PREFIX/lib/python3.13/site-packages/numpy/linalg/tests/test_linalg.py", line 386, in check_cases
    case.check(self.do)
    ~~~~~~~~~~^^^^^^^^^
  File "$PREFIX/lib/python3.13/site-packages/numpy/linalg/tests/test_linalg.py", line 116, in check
    do(self.a, self.b, tags=self.tags)
    ~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PREFIX/lib/python3.13/site-packages/numpy/linalg/tests/test_linalg.py", line 484, in do
    assert_almost_equal(b, adotx)
    ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^
  File "$PREFIX/lib/python3.13/site-packages/numpy/linalg/tests/test_linalg.py", line 72, in assert_almost_equal
    old_assert_almost_equal(a, b, decimal=decimal, **kw)
    ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PREFIX/lib/python3.13/site-packages/numpy/testing/_private/utils.py", line 616, in assert_almost_equal
    return assert_array_almost_equal(actual, desired, decimal, err_msg)
  File "$PREFIX/lib/python3.13/site-packages/numpy/testing/_private/utils.py", line 1222, in assert_array_almost_equal
    assert_array_compare(compare, actual, desired, err_msg=err_msg,
    ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                         verbose=verbose,
                         ^^^^^^^^^^^^^^^^
             header=('Arrays are not almost equal to %d decimals' % decimal),
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
             precision=decimal)
             ^^^^^^^^^^^^^^^^^^
  File "$PREFIX/lib/python3.13/site-packages/numpy/testing/_private/utils.py", line 983, in assert_array_compare
    raise AssertionError(msg)
AssertionError: 
Arrays are not almost equal to 6 decimals
Mismatched elements: 12 / 24 (50%)
First 5 mismatches are at indices:
 [0, 0, 1, 0]: 2.0 (ACTUAL), 0.0 (DESIRED)
 [0, 0, 1, 1]: 1.0 (ACTUAL), 0.0 (DESIRED)
 [0, 1, 1, 0]: 2.0 (ACTUAL), 0.0 (DESIRED)
 [0, 1, 1, 1]: 1.0 (ACTUAL), 0.0 (DESIRED)
 [1, 0, 1, 0]: 2.0 (ACTUAL), 0.0 (DESIRED)
Max absolute difference among violations: 2.
Max relative difference among violations: inf
 ACTUAL: array([[[[2., 1.],
         [2., 1.]],
...
 DESIRED: array([[[[2., 1.],
         [0., 0.]],
...
FAILED linalg/tests/test_linalg.py::TestInv::test_generalized_sq_cases - AssertionError: In test case: <LinalgCase: single_tile3_stride_+1_+3_+1_stride_+1>
Traceback (most recent call last):
  File "$PREFIX/lib/python3.13/site-packages/numpy/linalg/tests/test_linalg.py", line 386, in check_cases
    case.check(self.do)
    ~~~~~~~~~~^^^^^^^^^
  File "$PREFIX/lib/python3.13/site-packages/numpy/linalg/tests/test_linalg.py", line 116, in check
    do(self.a, self.b, tags=self.tags)
    ~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PREFIX/lib/python3.13/site-packages/numpy/linalg/tests/test_linalg.py", line 567, in do
    assert_almost_equal(matmul(a, a_inv),
    ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^
                        identity_like_generalized(a))
                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PREFIX/lib/python3.13/site-packages/numpy/linalg/tests/test_linalg.py", 

### Discussion (each comment cut to 800 characters)

- I will look into this!

- https://github.com/pytest-dev/pytest/blob/3422c67a3a46ccb4b5549c88821d5d768843418e/doc/en/reference/reference.rst?plain=1#L3064-L3066 

- the error messages are actually helpful?? like they tell you what went wrong AND how to fix it?? wild concept. more tools should do this.

- The summary is not the same thing as the section that details the specific errors per test (for the latter the details are obviously relevant).

