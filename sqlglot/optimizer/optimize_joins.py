import sqlglot.expressions as exp
from sqlglot.helper import tsort


def optimize_joins(expression):
    """
    Removes cross joins if possible and reorder joins based on predicate dependencies.
    """
    for select in expression.find_all(exp.Select):
        references = {}
        cross_joins = []

        for join in select.args.get("joins", []):
            name = join.this.alias_or_name
            tables = other_table_names(join, name)

            if tables:
                for table in tables:
                    references[table] = references.get(table, []) + [join]
            else:
                cross_joins.append((name, join))

        for name, join in cross_joins:
            for dep in references.get(name, []):
                on = dep.args["on"].unnest()
                if isinstance(on, exp.Connector):
                    for predicate in on.flatten():
                        if name in exp.column_table_names(predicate):
                            predicate.replace(exp.TRUE)
                            join.set(
                                "on",
                                exp.and_(join.args.get("on") or exp.TRUE, predicate),
                            )
                            if join_kind(join) == "CROSS":
                                join.set("kind", None)

    expression = reorder_joins(expression)
    expression = normalize(expression)
    return expression


def reorder_joins(expression):
    """
    Reorder joins by topological sort order based on predicate references.
    """
    for from_ in expression.find_all(exp.From):
        head = from_.args["expressions"][0]
        parent = from_.parent
        joins = {join.this.alias_or_name: join for join in parent.args.get("joins", [])}
        dag = {head.alias_or_name: []}

        for name, join in joins.items():
            dag[name] = other_table_names(join, name)
            parent.set(
                "joins",
                [joins[name] for name in tsort(dag) if name != head.alias_or_name],
            )
    return expression


def normalize(expression):
    """
    Remove INNER and OUTER from joins as they are optional.
    """
    for join in expression.find_all(exp.Join):
        if join_kind(join) != "CROSS":
            join.set("kind", None)
    return expression


def other_table_names(join, exclude):
    return [
        name
        for name in (exp.column_table_names(join.args.get("on") or exp.TRUE))
        if name != exclude
    ]


def join_kind(join):
    return (join.args.get("kind") or "").upper()
