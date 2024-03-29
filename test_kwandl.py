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


def test_forwarded_global_dict():
    """kwandl.forward registers decorated functions internally; this test makes sure"""
    # Note that the key is actually different here than the actual local name of
    # the function. This is an exceptional situation, caused by the fact that this
    # function is not actually decorated (and hence given the same name as the original
    # decorated function), but stored in a new variable:
    assert(kwandl._forwarded_global["function_1_and_2"] is function_1_and_2_kwandled)
    number_forwarded_now = len(kwandl._forwarded_global)
    @kwandl.forward
    def lets_try_another_one_here_just_for_kicks(**kwargs):
        return function_1_and_2_kwandled(**kwargs)
    # In this case, function keyname actually is the same as the local variable name:
    assert(kwandl._forwarded_global["lets_try_another_one_here_just_for_kicks"] is lets_try_another_one_here_just_for_kicks)
    assert(len(kwandl._forwarded_global) == number_forwarded_now + 1)


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


def test_forward_nested():
    """
    Tests whether nested functions work.

    This was not trivial, since the original uncompile claimed to not support nested functions.
    """
    @kwandl.forward
    def function_1_and_2_nested(**kwargs):
        function1_result = function1(**kwargs)
        function2_result = function2(**kwargs)
        return function1_result, function2_result
    result = function_1_and_2_nested(kwarg1=1, kwarg2=2)
    assert(result[0] == {'kwarg1': 1})
    assert(result[1] == {'kwarg2': 2})


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


class MyClass:
    @staticmethod
    def method(kwarg1=None):
        return {'kwarg1': kwarg1}


@kwandl.forward
def function_that_calls_attribute(**kwargs):
    return MyClass.method(**kwargs)


def test_forward_to_attribute():
    """Calling functions in modules or classes makes things a bit more complicated in the AST; this tests that."""
    # a globally defined function:
    result = function_that_calls_attribute(kwarg1=1)
    assert(result == {'kwarg1': 1})


@kwandl.forward
def function_that_calls_non_global_attribute(**kwargs):
    MyLocalClass = MyClass
    return MyLocalClass.method(**kwargs)


def test_forward_to_non_global_attribute():
    """Calling functions in modules or classes makes things a bit more complicated in the AST; this tests that."""
    # a function that forwards to non-global function:
    with pytest.raises(TypeError, match=r"function_that_calls_non_global_attribute\(\) got an unexpected keyword argument 'days'"):
        result = function_that_calls_non_global_attribute(days=365)
    result = function_that_calls_non_global_attribute(kwarg1=1)
    assert(result == {'kwarg1': 1})


class StatefulClass:
    """This class changes output when called (i.e. instances are created) multiple times."""
    used = False
    def __init__(self):
        if not StatefulClass.used:
            self.fresh = True
            StatefulClass.used = True
        else:
            self.fresh = False

    def run(self, ding=1):
        if self.fresh:
            return "first call!"
        return f"fail. also: ding={ding}"


@kwandl.forward
def function_that_calls_attribute_of_changing_stateful_class(**kwargs):
    return StatefulClass().run(**kwargs)


def test_forward_to_attribute_of_changing_expression():
    """
    When the called expression changes between calls, the simple method fails.
    
    Simple method: replace call(**kwargs) with (more or less):
        call(**kwandl.get_kwargs_applicable_to_func(call, kwargs))
    But if "call" is an expression that can give different outputs, e.g. when we
    replace "call" with "random_callable_thing()", then the "call" passed to 
    get_kwargs_applicable_to_func will be a different object than the one that is
    actually called and thus the wrong kwargs will have been returned by
    get_kwargs_applicable_to_func. To remedy this, we need to store the expression
    in a variable before passing it to get_kwargs_applicable_to_func and calling it.
    We didn't do this in the first versions. This test makes sure we keep taking
    this into account.
    """
    result = function_that_calls_attribute_of_changing_stateful_class(ding=3.14)
    assert(result == "first call!")


class MyClass2:
    @staticmethod
    def method(kwarg2=None):
        return {'kwarg2': kwarg2}

@kwandl.forward
def function_that_calls_reassigned_local_attribute(**kwargs):
    MyLocalClass = MyClass
    result1 = MyLocalClass.method(**kwargs)
    MyLocalClass = MyClass2
    result2 = MyLocalClass.method(**kwargs)
    return result1, result2


def test_forward_to_reassigned_local_attribute():
    """The local variable which/whose attribute is called can be reassigned, so we must check kwargs before each call."""
    result = function_that_calls_reassigned_local_attribute(kwarg1=1, kwarg2=2)
    assert(result == ({'kwarg1': 1}, {'kwarg2': 2}))


@kwandl.forward
def function_1_and_2_local_copies(**kwargs):
    function1_local = function1
    function2_local = function2
    function1_result = function1_local(**kwargs)
    function2_result = function2_local(**kwargs)
    return function1_result, function2_result


def test_forward_local():
    result = function_1_and_2_local_copies(kwarg1=1, kwarg2=2)
    assert(result[0] == {'kwarg1': 1})
    assert(result[1] == {'kwarg2': 2})


class ClassWithForwardedStaticMethods:
    @staticmethod
    @kwandl.forward
    def method1(**kwargs):
        function1_result = function1(**kwargs)
        function2_result = function2(**kwargs)
        return function1_result, function2_result

    # @kwandl.forward
    # @staticmethod
    # def method2(**kwargs):
    #     function1_result = function1(**kwargs)
    #     function2_result = function2(**kwargs)
    #     return function1_result, function2_result


def test_forward_staticmethod():
    result = ClassWithForwardedStaticMethods.method1(kwarg1=1, kwarg2=2)
    assert(result[0] == {'kwarg1': 1})
    assert(result[1] == {'kwarg2': 2})
    # result = ClassWithForwardedStaticMethods.method2(kwarg1=1, kwarg2=2)
    # assert(result[0] == {'kwarg1': 1})
    # assert(result[1] == {'kwarg2': 2})


class RandomDescriptor:
    """A descriptor that changes the fetched function object between calls."""
    def __init__(self):
        self.switch = True

    def __get__(self, obj, objtype=None):
        self.switch = not self.switch
        if self.switch:
            return function1
        return function2


class CallableWithRandomDescriptor:
    # note that there is only one descriptor instance per class attribute, not per instance!
    descriptor = RandomDescriptor()

    @kwandl.forward
    def __call__(self, **kwargs):
        return self.descriptor(**kwargs)


def test_forward_random_descriptor():
    """A descriptor can dynamically change between retrievals, so it should only be gotten once.
    
    If it's gotten more than once inside kwandl.forward, it will fail, because the keywords it
    passes will be wrong (will belong to the previous "get").
    """
    with pytest.raises(TypeError, match=r"__call__\(\) got an unexpected keyword argument 'kwarg1'"):
        result = CallableWithRandomDescriptor()(kwarg1=1)
    result = CallableWithRandomDescriptor()(kwarg1=1)
    assert(result == {'kwarg1': 1})


class CallableWithRandomDescriptorAndNestedIf:
    descriptor = RandomDescriptor()

    @kwandl.forward
    def __call__(self, **kwargs):
        call_this = lambda **x: {}
        if False:
            return {'we should never': 'get here'}
        elif True:
            call_this = self.descriptor
            return call_this(**kwargs)
        return {'we should never': 'get here either'}


def test_forward_random_descriptor_nested_orelse():
    """Like test_forward_random_descriptor, but from inside a nested conditional or `else` statement.

    The complication here is that we need to keep track of where exactly the statement with
    the forwarded call is inside the conditional. If it is in the test expression of an `if` statement,
    the replaced caller name must be above the `if test:` line. If the replaced call is somewhere
    inside the body, it should be in the body as well. Similarly, `orelse` attributes are nested in
    the AST inside `ast.If` objects, but also in `for` and `try`. These `orelse` fields can contain
    `if` statements as well (e.g. when using `elif`), that again contain a `test` field. In that case,
    the replaced caller name assignment must *still* be above the first `if` corresponding to the
    `else`. This requires some bookkeeping that we should test.
    """
    result = CallableWithRandomDescriptorAndNestedIf()(kwarg2=2)
    assert(result == {'kwarg2': 2})


@kwandl.forward_transitive
def function_1_and_2_transitive(**kwargs):
    return function_1_and_2_kwandled(**kwargs)


def test_forward_transitivity():
    """
    Transitivity test that tries to run on a function that calls another
    kwandl.forwarded function in turn. Expected keywords of both functions should
    be combined in the top-level call.
    """
    result = function_1_and_2_transitive(kwarg1=1, kwarg2=2)
    assert(result[0] == {'kwarg1': 1})
    assert(result[1] == {'kwarg2': 2})

@kwandl.forward
def function_1_and_2_transitive_level1(**kwargs):
    function1_result = function1(**kwargs)
    function2_result = function2(**kwargs)
    return function1_result, function2_result


@kwandl.forward_transitive
def function_1_and_2_transitive_level2(**kwargs):
    return function_1_and_2_transitive_level1(**kwargs)


@kwandl.forward_transitive
def function_1_and_2_transitive_level3(**kwargs):
    return function_1_and_2_transitive_level2(**kwargs)


@kwandl.forward_transitive
def function_1_and_2_transitive_level4(**kwargs):
    return function_1_and_2_transitive_level3(**kwargs)


def test_forward_transitivity_deep():
    """
    Like test_forward_transitivity, but tests multiple levels of transitivity.
    """
    result = function_1_and_2_transitive_level4(kwarg1=1, kwarg2=2)
    assert(result[0] == {'kwarg1': 1})
    assert(result[1] == {'kwarg2': 2})


@kwandl.forward_transitive
def function_1_and_2_transitive_level2_no_decorator(**kwargs):
    return function_1_and_2_transitive(**kwargs)


def test_forward_transitivity_deep_no_decorator():
    """
    Like test_forward_transitivity_deep, but now for the case when the first
    decorated function is not actually decorated with a decorator, but rather
    built with a function call to the decorator:

    decorated_function = kwandl.forward(function)

    This failed in the initial implementation, so that's why we test it.
    """
    result = function_1_and_2_transitive_level2_no_decorator(kwarg1=1, kwarg2=2)
    assert(result[0] == {'kwarg1': 1})
    assert(result[1] == {'kwarg2': 2})


# TODO:
# - Fix test_forward_staticmethod (relevant for dianna)
# - Add test case that checks if the function has **kwargs at all
