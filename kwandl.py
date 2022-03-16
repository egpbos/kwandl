import __future__
import ast
import functools
import inspect


def get_kwargs_applicable_to_function(function, kwargs):
    """Returns a subset of `kwargs` of only arguments and keyword arguments of `function`."""
    return {key: value for key, value in kwargs.items()
            if key in inspect.getfullargspec(function).args}


class ReplaceKwargsInCallsNodeTransformer(ast.NodeTransformer):
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
        ReplaceKwargsInCallsNodeTransformer initializer.

        Input:
            func: the function object we're decorating.
            calling_decorator_name: the name of the decorator that calls this as a string argument.
        """
        self.calling_decorator_name = calling_decorator_name
        self.func = func
        self.expected_kwargs = []

    def visit_Call(self, node):  # noqa: N802
        """
        Replace `func(...,**kwargs)` with `func(...,**get_kwargs_applicable_to_function(func, kwargs))`.

        Also stores the names of the keyword arguments of all such `func`s in self.expected_kwargs.
        """
        # first also visit possible child nodes
        self.generic_visit(node)
        # then check if this is a call with **kwargs argument
        for ix, kw in enumerate(node.keywords):
            if isinstance(kw.value, ast.Name) and kw.value.id == "kwargs":
                # then do the transformation on this node:
                new_node = node
                wrapper_function = ast.Attribute(value=ast.Name(id='kwandl', ctx=ast.Load()), attr='get_kwargs_applicable_to_function', ctx=ast.Load())
                wrapped_kwargs = ast.Call(func=wrapper_function, args=[new_node.func, kw.value], keywords=[])
                new_node.keywords.remove(kw)
                new_node.keywords.insert(ix, ast.keyword(value=wrapped_kwargs))

                # add func's actual keyword parameters to expected_kwargs:
                called_function_object = self.func.__globals__[new_node.func.id]
                # note: normal arguments (without default value) can also be used as keyword arguments
                # by the caller, so we can just take all args here:
                called_function_arguments = inspect.getfullargspec(called_function_object).args
                self.expected_kwargs += called_function_arguments

                # AST logistics
                ast.copy_location(new_node, node)
                ast.fix_missing_locations(new_node)
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
        # first visit all child nodes
        self.generic_visit(node)
        # then add the statement at the top:
        new_node = node

        # now add the expected_kwargs check
        expected_kwargs_ast = ast.List(elts=[ast.Constant(value=element) for element in self.expected_kwargs], ctx=ast.Load())

        # AST for raising TypeError if unexpected key used:
        typeerror_message = self.func.__name__ + "() got an unexpected keyword argument '"
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
        # next line represents: `raise TypeError(typeerror_message + unexpected_keywords.pop() + "'")`
        # so it just pops one unexpected_keyword off the difference set, which is in line with how
        # unexpected keyword arguments normally get handled (trigger exceptions one by one)
        type_error_ast = ast.Raise(exc=ast.Call(
            func=ast.Name(id='TypeError', ctx=ast.Load()), args=[
                ast.JoinedStr(values=[
                    ast.Constant(value=typeerror_message),
                    ast.FormattedValue(value=ast.Call(
                        func=ast.Attribute(value=ast.Name(id='unexpected_keywords', ctx=ast.Load()), attr='pop', ctx=ast.Load()),
                        args=[], keywords=[]), conversion=-1),
                    ast.Constant(value="'"),
                ])
            ], keywords=[])
        )

        # if-statement checking for unexpected_keywords:
        check_unexpected_keywords_ast = ast.If(test=ast.Name(id='unexpected_keywords', ctx=ast.Load()),
                                               body=[type_error_ast], orelse=[])

        # DEBUG PRINT:
        debug_print_ast = ast.Expr(value=ast.Call(func=ast.Name(id='print', ctx=ast.Load()), args=[ast.Constant(value='hoi')], keywords=[]))
        # put it all together:
        expected_kwargs_check = [debug_print_ast, unexpected_keywords_ast, check_unexpected_keywords_ast]

        new_node.body = expected_kwargs_check + new_node.body

        # === 3. rename the returned function so we can access it easily from replace_kwargs_in_calls ===
        new_node.name = "_func_with_kwargs_in_calls_replaced"

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
    if c.co_flags & inspect.CO_NESTED or c.co_freevars:
        raise NotImplementedError("Nested functions not supported")
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


def replace_kwargs_in_calls(func):
    # Parse AST and modify it.
    uncompiled = uncompile(func.__code__)

    # Parse AST and modify it
    tree = parse_snippet(*uncompiled)
    tree = ReplaceKwargsInCallsNodeTransformer(func, 'replace_kwargs_in_calls').visit(tree)
    uncompiled[0] = tree

    # Recompile wrapped function
    recompiled = recompile(*uncompiled)

    exec_output = {}
    # Note: using func.__globals__ is critical, otherwise names of functions used in func cannot be found
    exec(recompiled, func.__globals__, exec_output)
    wrapper = exec_output['_func_with_kwargs_in_calls_replaced']
    functools.update_wrapper(wrapper, func)

    return wrapper
