__version__ = "0.2.0"

import __future__
import ast
import functools
import inspect
import sys


if sys.version_info < (3, 9):
    from astunparse import unparse
    ast.unparse = unparse


def get_kwargs_applicable_to_function(function, kwargs):
    """Returns a subset of `kwargs` of only arguments and keyword arguments of `function`."""
    return {key: value for key, value in kwargs.items()
            if key in inspect.getfullargspec(function).args}


def _get_kwargs_applicable_to_function_and_check_expected_keywords(function, function_call_name, kwargs, expected_keywords,  # noqa: too-many-arguments
                                                                   local_function_names, typeerror_message):
    """
    Like get_kwargs_applicable_to_function, but also check expected keywords.
    
    This function is meant for use from @forward decorated functions that call
    non-global (i.e. local or non-local) objects. It adds the keywords from
    the local call (`function`) to `expected_keywords`, deletes `function`'s name
    from `local_function_names` and if `local_function_names` is empty (meaning all local
    functions have had their keywords added to `expected_keywords`) it finally
    does the unexpected keywords check. At this point it may raise an exception.

    Input:
        function_call_name: The name of function as it is used at the call site.
                            For instance, when calling `thing.bla(kwarg=1)`
                            function_call_name must be "thing.bla". This name
                            will then be removed from `local_function_names`.
    """
    applicable_kwargs = get_kwargs_applicable_to_function(function, kwargs)
    expected_keywords += applicable_kwargs
    local_function_names.remove(function_call_name)
    if not local_function_names:
        unexpected_keywords = set(kwargs.keys()) - set(expected_keywords)
        if unexpected_keywords:
            raise TypeError(typeerror_message + unexpected_keywords.pop() + "'")
    return applicable_kwargs


class ForwardNodeTransformer(ast.NodeTransformer):
    """
    Replace Call nodes with kwargs keywords in the AST of the decorated function.

    This NodeTransformer is made to be used from function decorators.
    The **kwargs are wrapped in a function that filters out keywords that are not
    applicable to the function.

    All applicable keywords of the called functions are also stored, so that
    they can be checked against in the modified function. This way, we can
    throw a TypeError when an unexpected keyword argument is given, except now it
    is unexpected by all the functions to which `kwargs` is forwarded.

    The NodeTransformer parts are inspired by https://www.georgeho.org/manipulating-python-asts/
    """
    def __init__(self, func, calling_decorator_name: str):
        """
        ForwardNodeTransformer initializer.

        Input:
            func: the function object we're decorating.
            calling_decorator_name: the name of the decorator that calls this as a string argument.
        """
        self.calling_decorator_name = calling_decorator_name
        self.func = func
        self.expected_kwargs = []
        # by default, we try to gather the expected kwargs in the AST, so the decorated function doesn't
        # need to get the expected_kwargs itself dynamically; the following flag is switched if this
        # is not possible (when local or at least non-global functions are called):
        self.use_expected_kwargs_in_ast = True
        self.forwardized_function_names = []
        self.local_function_names = []
        # this message will be necessary in both visit functions below, so define it here:
        self.typeerror_message = self.func.__name__ + "() got an unexpected keyword argument '"

    def _add_funcs_kwparams_to_expected_kwargs(self, new_node):
        """
        Returns: (called_name, non_global)
            called_name: the function as it is called at the call site, e.g. "thing.bla"
                         when calling `thing.bla(kwarg=1)`
            non_global: bool, True if the called function is a non-global (i.e. local or non-local)
        """
        non_global = False

        # add func's actual keyword parameters to expected_kwargs:
        if isinstance(new_node.func, ast.Name):
            called_name = new_node.func.id
            if called_name in self.func.__globals__:
                called_function_object = self.func.__globals__[called_name]
            else:
                non_global = True
        elif isinstance(new_node.func, ast.Attribute):
            called_name = ast.unparse(new_node.func)
            top_level_object_name = called_name.split('.')[0]
            if top_level_object_name in self.func.__globals__:
                called_function_object = eval(called_name, self.func.__globals__)  # noqa: eval-used
            else:
                non_global = True

        if non_global:
            # The call is on a non-global object, so we cannot get the keywords here.
            # We get them later then.
            self.local_function_names.append(called_name)
        else:
            # note: normal arguments (without default value) can also be used as keyword arguments
            # by the caller, so we can just take all args here:
            called_function_arguments = inspect.getfullargspec(called_function_object).args
            self.expected_kwargs += called_function_arguments

        return called_name, non_global

    def visit_Call(self, node):  # noqa: N802
        """
        Replace `func(...,**kwargs)` with `func(...,**get_kwargs_applicable_to_function(func, kwargs))`.

        Also stores the names of the keyword arguments of all such `func`s in self.expected_kwargs.
        """
        # first also visit possible child nodes
        self.generic_visit(node)
        # then check if this is a call with **kwargs argument
        for ix, kw in enumerate(node.keywords):
            # kw.arg must be None, otherwise it's not a double-starred keyword, but an object passed as keyword argument
            if isinstance(kw.value, ast.Name) and kw.value.id == "kwargs" and kw.arg is None:
                new_node = node

                # first get keywords and check whether the called function is global or not
                called_name, non_global = self._add_funcs_kwparams_to_expected_kwargs(new_node)

                # then do the appropriate transformation on this node:
                if non_global:
                    wrapper_function = ast.parse('kwandl._get_kwargs_applicable_to_function_and_check_expected_keywords').body[0].value
                    wrapped_kwargs = ast.Call(func=wrapper_function,
                                              args=[new_node.func, ast.Constant(value=called_name), kw.value,
                                                    ast.Name(id="expected_keywords", ctx=ast.Load()),
                                                    ast.Name(id="local_function_names", ctx=ast.Load()),
                                                    ast.Constant(value=self.typeerror_message)],
                                              keywords=[])
                else:
                    wrapper_function = ast.Attribute(value=ast.Name(id='kwandl', ctx=ast.Load()), attr='get_kwargs_applicable_to_function', ctx=ast.Load())
                    wrapped_kwargs = ast.Call(func=wrapper_function, args=[new_node.func, kw.value], keywords=[])
                new_node.keywords.remove(kw)
                new_node.keywords.insert(ix, ast.keyword(value=wrapped_kwargs))

                # AST logistics
                ast.copy_location(new_node, node)
                ast.fix_missing_locations(new_node)
                self.forwardized_function_names.append(called_name)
                return new_node
        # if no kwargs argument was found, just return the node unchanged:
        return node

    def visit_FunctionDef(self, node):  # noqa: N802
        """Modify the function definition itself.

        - Rename and remove the decorator, otherwise we get infinite recursion.
        - Add a statement to the top checking if all kwargs are expected.
        """
        # === first also visit possible child nodes ===
        self.generic_visit(node)

        # === then this node itself ===

        # === 1. remove the decorator: ===
        new_node = node
        new_decorator_list = []
        for decorator in new_node.decorator_list:
            # TODO: replace with pattern matching once Python 3.9 is EOL
            if isinstance(decorator, ast.Attribute):
                if self.calling_decorator_name not in ast.unparse(decorator):
                    new_decorator_list.append(decorator)
            else:
                if decorator.id != self.calling_decorator_name:
                    new_decorator_list.append(decorator)
        new_node.decorator_list = new_decorator_list

        # === 2. add a statement to the top checking if all kwargs are expected: ===
        if not self.forwardized_function_names:
            raise ValueError(f"decorator kwandl.forward cannot find any kwargs object to forward in {self.func.__name__}")

        new_node = node

        expected_kwargs_ast = ast.List(elts=[ast.Constant(value=element) for element in self.expected_kwargs], ctx=ast.Load())
        local_function_names_ast = ast.List(elts=[ast.Constant(value=element) for element in self.local_function_names], ctx=ast.Load())

        # AST for raising TypeError if unexpected key used:
        kwargs_keys_ast = ast.Call(func=ast.Attribute(value=ast.Name(id='kwargs', ctx=ast.Load()), attr='keys', ctx=ast.Load()), args=[], keywords=[])
        # next line represents: `unexpected_keywords = set(kwargs.keys()) - set(expected_keywords)`
        unexpected_keywords_ast = ast.Assign(
            targets=[ast.Name(id='unexpected_keywords', ctx=ast.Store())],
            value=ast.BinOp(left=ast.Call(func=ast.Name(id='set', ctx=ast.Load()),
                                        args=[kwargs_keys_ast], keywords=[]
                                        ),
                            op=ast.Sub(),
                            right=ast.Call(func=ast.Name(id='set', ctx=ast.Load()), args=[expected_kwargs_ast],
                                        keywords=[])
                            )
        )
        type_error_ast = ast.parse(f"""raise TypeError("{self.typeerror_message}" + unexpected_keywords.pop() + "'")""").body[0]

        # if-statement checking for unexpected_keywords:
        check_unexpected_keywords_ast = ast.If(test=ast.Name(id='unexpected_keywords', ctx=ast.Load()),
                                            body=[type_error_ast], orelse=[])

        if not self.local_function_names:
            # put it all together for the simple case (no non-globals):
            new_node.body = [unexpected_keywords_ast, check_unexpected_keywords_ast] + new_node.body
        else:
            # when we have called non-globals, we need to defer the check until we gathered all
            # expected keywords dynamically; the check is done in get_kwargs_applicable_to_function_and_check_expected_keywords,
            # but it needs expected_keywords from the non-dynamically defined calls and also
            # a list of local functions to keep track of when everything is collected
            expected_keywords_assign_ast = ast.Assign(targets=[ast.Name(id='expected_keywords', ctx=ast.Store())],
                                                      value=expected_kwargs_ast)
            local_function_names_assign_ast = ast.Assign(targets=[ast.Name(id='local_function_names', ctx=ast.Store())],
                                                         value=local_function_names_ast)
            new_node.body = [expected_keywords_assign_ast, local_function_names_assign_ast] + new_node.body

        # === 3. rename the returned function so we can access it easily from `forward` ===
        new_node.name = "_func_with_kwargs_forwarded"

        # === AST logistics ===
        ast.copy_location(new_node, node)
        ast.fix_missing_locations(new_node)
        return new_node


# The following is modified from https://github.com/eigenfoo/random/blob/master/python/ast-hiding-yield/00-prototype/hiding-yield.ipynb
# Copyright (c) 2018-2020 George Ho, MIT license
# That code itself was in turn modified from https://code.activestate.com/recipes/578353-code-to-source-and-back/
# Copyright (c) 2012 Oren Tirosh, MIT license

PyCF_MASK = sum(v for k, v in vars(__future__).items() if k.startswith("CO_FUTURE"))


def uncompile(c):
    """uncompile(codeobj) -> [source, filename, mode, flags, firstlineno]."""
    if c.co_name == "<lambda>":
        raise NotImplementedError("Lambda functions not supported")
    if c.co_filename == "<string>":
        raise NotImplementedError("Code without source file not supported")

    filename = inspect.getfile(c)

    try:
        lines, firstlineno = inspect.getsourcelines(c)
    except IOError:
        raise RuntimeError("Source code not available") from IOError

    source = "".join(lines)

    return [source, filename, "single", c.co_flags & PyCF_MASK, firstlineno]


def recompile(source, filename, mode, flags=0, firstlineno=1):
    """Recompile output of uncompile back to a code object. source may also be preparsed AST."""
    if isinstance(source, ast.AST):
        a = source
    else:
        a = parse_snippet(source, filename, mode, flags, firstlineno)

    node = a.body[0]

    if not isinstance(node, ast.FunctionDef):
        raise RuntimeError("Expecting function AST node")

    c0 = compile(a, filename, mode, flags, True)

    return c0


def parse_snippet(source, filename, mode, flags, firstlineno):
    """Like ast.parse, but accepts indented code snippet with a line number offset."""
    args = filename, mode, flags | ast.PyCF_ONLY_AST, True
    prefix = "\n"
    try:
        a = compile(prefix + source, *args)
    except IndentationError:
        # Already indented? Wrap with dummy compound statement
        prefix = "with 0:\n"
        a = compile(prefix + source, *args)
        # Peel wrapper
        a.body = a.body[0].body
    ast.increment_lineno(a, firstlineno - 2)
    return a


def forward(func):
    # Parse AST and modify it.
    uncompiled = uncompile(func.__code__)

    # Parse AST and modify it
    tree = parse_snippet(*uncompiled)
    tree = ForwardNodeTransformer(func, 'forward').visit(tree)
    uncompiled[0] = tree

    # Recompile wrapped function
    recompiled = recompile(*uncompiled)

    exec_output = {}
    # Note: using func.__globals__ is critical, otherwise names of functions used in func cannot be found
    exec(recompiled, func.__globals__, exec_output)
    wrapper = exec_output['_func_with_kwargs_forwarded']
    functools.update_wrapper(wrapper, func)

    return wrapper
