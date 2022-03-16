
<!--
To add:

[![RSD](https://img.shields.io/badge/rsd-kwandl-00a3e3.svg)](https://www.research-software.nl/software/kwandl) [![workflow pypi badge](https://img.shields.io/pypi/v/kwandl.svg?colorB=blue)](https://pypi.python.org/project/kwandl/)

[![DOI](https://zenodo.org/badge/DOI/<replace-with-created-DOI>.svg)](https://doi.org/<replace-with-created-DOI>)

[![workflow cii badge](https://bestpractices.coreinfrastructure.org/projects/<replace-with-created-project-identifier>/badge)](https://bestpractices.coreinfrastructure.org/projects/<replace-with-created-project-identifier>)

-->
[![fair-software badge](https://img.shields.io/badge/fair--software.eu-%E2%97%8F%20%20%E2%97%8F%20%20%E2%97%8F%20%20%E2%97%8F%20%20%E2%97%8B-yellow)](https://fair-software.eu)
[![build](https://github.com/egpbos/kwandl/actions/workflows/build.yml/badge.svg)](https://github.com/egpbos/kwandl/actions/workflows/build.yml)

# `kwandl`: Keyword arguments handled
## Installation

To install `kwandl` from the GitHub repository, do:

```console
git clone https://github.com/egpbos/kwandl.git
cd kwandl
python3 -m pip install .
```

## Usage

`kwandl` is essentially a box of magic tricks to make working with `kwargs` smoother.

### Passing only relevant `kwargs`
Say you have a function `top` which takes `**kwargs` and passes them on to `ding` and `boop`:
```python
def top(**kwargs):
    ding(**kwargs)
    boop(**kwargs)
```
Only problem is: `ding` and `boop` have different sets of keyword arguments:
```python
def ding(dingo=1, dinga=2):
    ...

def boop(boopie=3, boonk=4):
    ...
```
This means `top(dingo="blurg", boonk=None)` will fail with a `TypeError`, because `boonk` will be passed to `ding` and `dingo` will be passed to `boop`, both of which are invalid.

`kwandl` solves this for you with one simple decorator:
```python
@kwandl.replace_kwargs_in_calls
def top(**kwargs):
    ding(**kwargs)
    boop(**kwargs)
```
This _Just Works™_.

It does so by modifying the abstract syntax tree (AST) of the function calls with `kwargs` as argument so that `kwargs` is effectively replaced by `kwandl.get_kwargs_applicable_to_function(ding, kwargs)` (or `boop` instead of `ding` depending on the calling function).
An alternative way to use this `kwandl` functionality then is to use `get_kwargs_applicable_to_function` directly:

```python
def top(**kwargs):
    ding(**kwandl.get_kwargs_applicable_to_function(ding, kwargs))
    boop(**kwandl.get_kwargs_applicable_to_function(boop, kwargs))
```

Note, however, that `@kwandl.replace_kwargs_in_calls` does a bit more: it also checks whether kwargs contains keyword arguments that are a match to neither `ding` nor `boop` and raises a `TypeError` if so.
A complete alternative notation for `@kwandl.replace_kwargs_in_calls` would then be:

```python
def top(**kwargs):
    ding_kwargs = kwandl.get_kwargs_applicable_to_function(ding, kwargs)
    boop_kwargs = kwandl.get_kwargs_applicable_to_function(boop, kwargs)

    unexpected_keywords = set(kwargs) - set(ding_kwargs) - set(boop_kwargs)

    if unexpected_keywords:
        raise TypeError(f"top() got an unexpected keyword argument '{unexpected_keywords.pop()}'")

    ding(**ding_kwargs)
    boop(**boop_kwargs)
```
The motivation behind this package should now become clearer: the amount of boilerplate necessary to solve what in my mind should not be such a huge problem is ... well, huge.

## Documentation
[![Documentation Status](https://readthedocs.org/projects/kwandl/badge/?version=latest)](https://kwandl.readthedocs.io/en/latest/?badge=latest)

For more details, see the [full documentation on Readthedocs](https://kwandl.readthedocs.io/en/latest#Contents).
## Contributing

If you want to contribute to the development of `kwandl`,
have a look at the [contribution guidelines](https://kwandl.readthedocs.io/en/latest/CONTRIBUTING.html).

## Credits

This package was created with [Cookiecutter](https://github.com/audreyr/cookiecutter) and the [NLeSC/python-template](https://github.com/NLeSC/python-template).
