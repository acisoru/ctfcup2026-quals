import ast


def parse_formula(source: str) -> ast.expr:
    tree = ast.parse(source, mode="eval")
    return tree.body


def calc_grade(formula: str):
    expr = parse_formula(formula)
    code = compile(ast.Expression(expr), "<grade>", "eval")
    return eval(code)
