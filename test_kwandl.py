import kwandl
import pytest


def function1(kwarg1=None):
    return {'kwarg1': kwarg1}


def function2(kwarg2=None):
    return {'kwarg2': kwarg2}


def function_1_and_2(**kwargs):
    function1_result = function1(**kwargs)
    function2_result = function2(**kwargs)
    return function1_result, function2_result


# decorated version:
function_1_and_2_kwandled = kwandl.forward(function_1_and_2)


def test_forward():
    with pytest.raises(TypeError, match=r"function1\(\) got an unexpected keyword argument 'kwarg2'"):
        function_1_and_2(kwarg1=1, kwarg2=2)
    result = function_1_and_2_kwandled(kwarg1=1, kwarg2=2)
    assert(result[0] == {'kwarg1': 1})
    assert(result[1] == {'kwarg2': 2})


def test_forward_throw_type_error_on_unexpected_kwarg():
    with pytest.raises(TypeError, match=r"function_1_and_2\(\) got an unexpected keyword argument 'nonexistent_kwarg'"):
        function_1_and_2_kwandled(nonexistent_kwarg=1)


def function_with_dict_parameter(just_a_dict=None):
    return just_a_dict


@kwandl.forward
def function_with_unexpanded_kwargs(**kwargs):
    result1 = function1(**kwargs)
    result2 = function2(**kwargs)
    result3 = function_with_dict_parameter(kwargs)
    return result1, result2, result3


def test_forward_with_unexpanded_kwargs():
    """
    Test the corner case of kwargs being passed just as a dictionary.
    
    In this case, kwargs in function_with_dict_parameter(kwargs) becomes a non-keyword
    argument in the AST (i.e. it will be in the args attribute of the ast.Call, instead of
    the keywords attribute), which means it won't trigger the forwarding decorator at all.
    """
    result = function_with_unexpanded_kwargs(kwarg1=1, kwarg2=2)
    assert(result == ({'kwarg1': 1}, {'kwarg2': 2}, {'kwarg1': 1, 'kwarg2': 2}))


@kwandl.forward
def function_with_kwargs_as_dict(**kwargs):
    result1 = function1(**kwargs)
    result2 = function2(**kwargs)
    result3 = function_with_dict_parameter(just_a_dict=kwargs)
    return result1, result2, result3


def test_forward_with_kwargs_as_dict():
    """
    Test the corner case of kwargs being passed just as a dictionary via a keyword argument.
    
    The exceptional part about this is that kwargs in that call to function_with_dict_parameter
    should not be kwandl.forwarded, in contrast to the two calls to function1 and function2.
    For this, we added a check on `kw.arg is None` in the AST, because that distinguishes the
    "double starred" kwargs argument from a regular keyword argument like `just_a_dict=kwargs`.
    """
    result = function_with_kwargs_as_dict(kwarg1=1, kwarg2=2)
    assert(result == ({'kwarg1': 1}, {'kwarg2': 2}, {'kwarg1': 1, 'kwarg2': 2}))


def test_forward_value_error_when_nothing_to_forward():
    """Tests whether the decorator throws an exception when there is nothing valid to forward."""
    with pytest.raises(ValueError, match=r"decorator kwandl.forward cannot find any kwargs object to forward in function_with_just_unexpanded_kwargs"):
        @kwandl.forward
        def function_with_just_unexpanded_kwargs(**kwargs):
            function_with_dict_parameter(kwargs)
    with pytest.raises(ValueError, match=r"decorator kwandl.forward cannot find any kwargs object to forward in function_with_just_kwargs_as_dict"):
        @kwandl.forward
        def function_with_just_kwargs_as_dict(**kwargs):
            function_with_dict_parameter(just_a_dict=kwargs)
