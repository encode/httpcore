# Contributing

Thanks for considering contributing to HTTP Core!

We welcome contributors to:

- Try [HTTPX](https://www.python-httpx.org), as it is HTTP Core's main entry point,
and [report bugs/issues you find](https://github.com/encode/httpx/issues/new)
- Help triage [issues](https://github.com/encode/httpcore/issues) and investigate
root causes of bugs
- [Review Pull Requests of others](https://github.com/encode/httpcore/pulls)
- Review, clarify and write documentation
- Participate in discussions

## Reporting Bugs or Other Issues

HTTP Core is a fairly specialized library and its main purpose is to provide a
solid base for [HTTPX](https://www.python-httpx.org). HTTPX should be considered
the main entry point to HTTP Core and as such we encourage users to test and raise
issues in [HTTPX's issue tracker](https://github.com/encode/httpx/issues/new)
where maintainers and contributors can triage and move to HTTP Core if appropriate.

If you are convinced that the cause of the issue is on HTTP Core you're more than
welcome to [open an issue](https://github.com/encode/httpcore/issues/new).

Please attach as much detail as possible and, in case of a
bug report, provide information like:

- OS platform or Docker image
- Python version
- Installed dependencies and versions (`python -m pip freeze`)
- Code snippet to reproduce the issue
- Error traceback and output

It is quite helpful to increase the logging level of HTTP Core and include the
output of your program. To do so set the `HTTPCORE_LOG_LEVEL` or `HTTPX_LOG_LEVEL`
environment variables to `TRACE`, for example:

```console
$ HTTPCORE_LOG_LEVEL=TRACE python test_script.py
TRACE [2020-06-06 09:55:10] httpcore._async.connection_pool - get_connection_from_pool=(b'https', b'localhost', 5000)
TRACE [2020-06-06 09:55:10] httpcore._async.connection_pool - created connection=<httpcore._async.connection.AsyncHTTPConnection object at 0x1110fe9d0>
...
```

The output will be quite long but it will help dramatically in diagnosing the problem.

For more examples please refer to the
[environment variables documentation in HTTPX](https://www.python-httpx.org/environment_variables/#httpx_log_level).

## Development

To start developing HTTP Core create a **fork** of the
[repository](https://github.com/encode/httpcore) on GitHub.

Then clone your fork with the following command replacing `YOUR-USERNAME` with
your GitHub username:

```shell
$ git clone https://github.com/YOUR-USERNAME/httpcore
```

You can now install the project and its dependencies using:

```shell
$ cd httpcore
$ scripts/install
```

## Unasync

HTTP Core provides synchronous and asynchronous interfaces. As you can imagine,
keeping two almost identical versions of code in sync can be quite time consuming.
To work around this problem HTTP Core uses a technique called _unasync_, where
the development is focused on the asynchronous version of the code and a script
generates the synchronous version from it.

As such developers should:

- Only make modifications in the asynchronous and shared portions of the code.
In practice this roughly means avoiding the `httpcore/_sync` directory.
- Write tests _only under `async_tests`_, synchronous tests are also generated
as part of the unasync process.
- Run `scripts/unasync` to generate the synchronous versions. Note the script
is ran as part of other scripts as well, so you don't usually need to run this
yourself.
- Run the entire test suite as decribed below.

## Testing and Linting

We use custom shell scripts to automate testing, linting,
and documentation building workflow.

To run the tests, use:

```shell
$ scripts/test
```

!!! warning
    The test suite spawns testing servers on ports **8000** and **8001**.
    Make sure these are not in use, so the tests can run properly.

You can run a single test script like this:

```shell
$ scripts/test -- tests/async_tests/test_interfaces.py
```

To run the code auto-formatting:

```shell
$ scripts/lint
```

Lastly, to run code checks separately (they are also run as part of `scripts/test`), run:

```shell
$ scripts/check
```

## Documenting

Documentation pages are located under the `docs/` folder.

To run the documentation site locally (useful for previewing changes), use:

```shell
$ scripts/docs
```

## Resolving Build / CI Failures

Once you've submitted your pull request, the test suite will automatically run, and the results will show up in GitHub.
If the test suite fails, you'll want to click through to the "Details" link, and try to identify why the test suite failed.

<p align="center" style="margin: 0 0 10px">
  <img src="https://raw.githubusercontent.com/encode/httpx/master/docs/img/gh-actions-fail.png" alt='Failing PR commit status'>
</p>

Here are some common ways the test suite can fail:

### Check Job Failed

<p align="center" style="margin: 0 0 10px">
  <img src="https://raw.githubusercontent.com/encode/httpx/master/docs/img/gh-actions-fail-check.png" alt='Failing GitHub action lint job'>
</p>

This job failing means there is either a code formatting issue or type-annotation issue.
You can look at the job output to figure out why it's failed or within a shell run:

```shell
$ scripts/check
```

It may be worth it to run `$ scripts/lint` to attempt auto-formatting the code
and if that job succeeds commit the changes.

### Docs Job Failed

This job failing means the documentation failed to build. This can happen for
a variety of reasons like invalid markdown or missing configuration within `mkdocs.yml`.

### Python 3.X Job Failed

<p align="center" style="margin: 0 0 10px">
  <img src="https://raw.githubusercontent.com/encode/httpx/master/docs/img/gh-actions-fail-test.png" alt='Failing GitHub action test job'>
</p>

This job failing means the unit tests failed or not all code paths are covered by unit tests.

If tests are failing you will see this message under the coverage report:

`=== 1 failed, 435 passed, 1 skipped, 1 xfailed in 11.09s ===`

If tests succeed but coverage is lower than our current threshold, you will see this message under the coverage report:

`FAIL Required test coverage of 100% not reached. Total coverage: 99.00%`

## Releasing

*This section is targeted at HTTPX maintainers.*

Before releasing a new version, create a pull request that includes:

- **An update to the changelog**:
    - We follow the format from [keepachangelog](https://keepachangelog.com/en/1.0.0/).
    - [Compare](https://github.com/encode/httpcore/compare/) `master` with the tag of the latest release, and list all entries that are of interest to our users:
        - Things that **must** go in the changelog: added, changed, deprecated or removed features, and bug fixes.
        - Things that **should not** go in the changelog: changes to documentation, tests or tooling.
        - Try sorting entries in descending order of impact / importance.
        - Keep it concise and to-the-point. 🎯
- **A version bump**: see `__version__.py`.

For an example, see [#99](https://github.com/encode/httpcore/pull/99).

Once the release PR is merged, create a
[new release](https://github.com/encode/httpcore/releases/new) including:

- Tag version like `0.9.3`.
- Release title `Version 0.9.3`
- Description copied from the changelog.

Once created this release will be automatically uploaded to PyPI.

If something goes wrong with the PyPI job the release can be published using the
`scripts/publish` script.
