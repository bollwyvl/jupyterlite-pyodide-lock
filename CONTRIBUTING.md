# Contributing

Thank you for considering a contribution to `jupyterlite-pyodide-lock`.

We use [pixi] for local development and GitHub [issues][issues] and [pull requests][prs]
to collaboration.

[issues]: (https://github.com/deathbeds/jupyterlite-pyodide-lock/issues)
[prs]: https://github.com/deathbeds/jupyterlite-pyodide-lock/pulls

## Pull Requests

Before making a [pull request][prs], please ensure:

- you've got a local [setup](#set-up)
- the following command runs without error:

```bash
pixi run pr
```

## Local Development

### Set Up

This project is developed locally and in CI with [pixi], a relatively new approach to
`conda` package management and task running.

> **Note**
>
> Refer to `pixi.toml#/$schema` for the current development version

[pixi]: https://pixi.sh/latest/#installation

If using `mamba` or `conda` (or some other `$CONDA_EXE`):

```bash
mamba install -c conda-forge "pixi ==0.61.0"  # replace `mamba` with your CONDA_EXE
```

<details><summary><i>Why <code>pixi</code>?</i></summary>

`pixi` provides the necessary primitives to:

- capture complex environments, with python and other runtimes
- install environments quickly, and cache well, but only when needed
- run tasks, in the right environment, in the right order
- skip tasks that have already run, and dependencies have not changed

</details>

<br />

### Tasks and Environments

See all the project info:

```bash
pixi info
```

See the available top-level `pixi` tasks:

```bash
pixi task list
```

### Running Tasks

Most tasks `run` just fine, and then stop:

```bash
pixi run all     # does all of the following, as needed
pixi run fix
pixi run build
pixi run lint
pixi run docs
pixi run check
pixi run test   # this takes a pretty long time
```

Some tasks run until stopped with <kbd>ctrl+c</kbd>:

```bash
pixi run serve-lab
pixi run serve-docs
```
