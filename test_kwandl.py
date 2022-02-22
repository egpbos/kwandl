import kwandl


def function1(kwarg1=None):
    return {'kwarg1': kwarg1}

def function2(kwarg2=None):
    return {'kwarg2': kwarg2}


# @kwandl.it
def function_1_and_2(**kwargs):
    function1_result = function1(**kwargs)
    function2_result = function2(**kwargs)
    return function1_result, function2_result


def test_passing_kwargs():
    result = function_1_and_2(kwarg1=1, kwarg2=2)
    assert(result[0] == {'kwarg1': 1})
    assert(result[1] == {'kwarg2': 2})
