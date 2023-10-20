from graphviz import Digraph

from sweepai.core.entities import FileChangeRequest


def create_digraph(file_change_requests: list[FileChangeRequest]):
    dot = Digraph(comment="FileChangeRequest Tree")
    dot.attr(pad="0.5")

    ranks = {}

    for i, fcr in enumerate(file_change_requests):
        if fcr.parent is None:
            ranks[fcr.id_] = 0
        else:
            ranks[fcr.id_] = ranks[fcr.parent.id_] + 1

    for layer in range(max(ranks.values()) + 1):
        with dot.subgraph() as c:
            if layer == 0:
                c.attr(label="Original plan", labelloc="t", labeljust="l", rank="same")
                c.node("start", "", shape="none", width="0")
            else:
                c.attr(label=f"Layer {layer}", rank="same")
            if layer == max(ranks.values()):
                c.node("end", "", shape="none", width="0")
            for fcr in file_change_requests:
                if ranks[fcr.id_] == layer:
                    if fcr.change_type == "check":
                        c.node(
                            fcr.id_,
                            fcr.summary,
                            shape="rectangle",
                            fillcolor=fcr.color,
                            style="filled",
                        )
                    else:
                        c.node(
                            fcr.id_, fcr.summary, fillcolor=fcr.color, style="filled"
                        )

    last_item_per_layer = {layer: None for layer in range(max(ranks.values()) + 1)}

    for fcr in file_change_requests:
        if fcr.parent:
            if fcr.change_type == "check":
                dot.edge(fcr.parent.id_, fcr.id_, label="Check changes", style="dashed")
            elif fcr.parent.change_type == "check":
                dot.edge(fcr.parent.id_, fcr.id_, label="More changes required")
            else:
                dot.edge(fcr.parent.id_, fcr.id_)
        elif last_item_per_layer[ranks[fcr.id_]] is not None:
            dot.edge(last_item_per_layer[ranks[fcr.id_]].id_, fcr.id_, label="Continue")
        last_item_per_layer[ranks[fcr.id_]] = fcr

    dot.edge("start", file_change_requests[0].id_, label="Start")
    dot.edge(file_change_requests[-1].id_, "end", label="Finish")

    return dot


def create_digraph_svg(file_change_requests: list[FileChangeRequest]):
    if len(file_change_requests) == 0:
        return ""
    return create_digraph(file_change_requests).pipe(format="svg").decode("utf-8")
