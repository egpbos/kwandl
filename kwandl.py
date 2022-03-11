import inspect
import ast
import functools
import __future__


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

    Inspired by https://www.georgeho.org/manipulating-python-asts/
    """
    def __init__(self, calling_decorator_name: str):
        """Pass the name of the decorator that calls this as a string argument."""
        self.calling_decorator_name = calling_decorator_name

    def visit_Call(self, node):  # noqa: N802
        # first also visit possible child nodes
        self.generic_visit(node)
        for ix, kw in enumerate(node.keywords):
            if isinstance(kw.value, ast.Name) and kw.value.id == "kwargs":
                # then do the transformation on this node:
                new_node = node
                wrapper_function = ast.Attribute(value=ast.Name(id='kwandl', ctx=ast.Load()), attr='get_kwargs_applicable_to_function', ctx=ast.Load())
                wrapped_kwargs = ast.Call(func=wrapper_function, args=[new_node.func, kw.value], keywords=[])
                new_node.keywords.remove(kw)
                new_node.keywords.insert(ix, ast.keyword(value=wrapped_kwargs))

                # AST logistics
                ast.copy_location(new_node, node)
                ast.fix_missing_locations(new_node)
                return new_node
        # if no kwargs argument was found, just return the node unchanged:
        return node

    def visit_FunctionDef(self, node):  # noqa: N802
        """Rename and remove the decorator, otherwise we get infinite recursion."""
        # first also visit possible child nodes
        self.generic_visit(node)
        # then this node itself:
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
        new_node.name = "_func_with_kwargs_in_calls_replaced"

        # AST logistics
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
    tree = ReplaceKwargsInCallsNodeTransformer('replace_kwargs_in_calls').visit(tree)
    uncompiled[0] = tree

    # Recompile wrapped function
    recompiled = recompile(*uncompiled)

    exec_output = {}
    # Note: using func.__globals__ is critical, otherwise names of functions used in func cannot be found
    exec(recompiled, func.__globals__, exec_output)
    wrapper = exec_output['_func_with_kwargs_in_calls_replaced']
    functools.update_wrapper(wrapper, func)

    return wrapper
