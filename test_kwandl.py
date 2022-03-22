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
function_1_and_2_kwandled = kwandl.replace_kwargs_in_calls(function_1_and_2)


def test_replace_kwargs_in_calls():
    with pytest.raises(TypeError, match=r"function1\(\) got an unexpected keyword argument 'kwarg2'"):
        function_1_and_2(kwarg1=1, kwarg2=2)
    result = function_1_and_2_kwandled(kwarg1=1, kwarg2=2)
    assert(result[0] == {'kwarg1': 1})
    assert(result[1] == {'kwarg2': 2})


def test_replace_kwargs_in_calls_throw_type_error_on_unexpected_kwarg():
    with pytest.raises(TypeError, match=r"function_1_and_2\(\) got an unexpected keyword argument 'nonexistent_kwarg'"):
        function_1_and_2_kwandled(nonexistent_kwarg=1)


def function_with_dict_parameter(just_a_dict=None):
    return just_a_dict


@kwandl.replace_kwargs_in_calls
def function_with_unexpanded_kwargs(**kwargs):
    result1 = function1(**kwargs)
    result2 = function2(**kwargs)
    result3 = function_with_dict_parameter(kwargs)
    return result1, result2, result3


def test_replace_kwargs_in_calls_with_unexpanded_kwargs():
    """
    Test the corner case of kwargs being passed just as a dictionary.
    
    In this case, kwargs in function_with_dict_parameter(kwargs) becomes a non-keyword
    argument in the AST (i.e. it will be in the args attribute of the ast.Call, instead of
    the keywords attribute), which means it won't trigger the forwarding decorator at all.
    """
    result = function_with_unexpanded_kwargs(kwarg1=1, kwarg2=2)
    assert(result == ({'kwarg1': 1}, {'kwarg2': 2}, {'kwarg1': 1, 'kwarg2': 2}))
