"""Bounded, escaped HTML/SVG presentation; rendering never reads external resources."""

from __future__ import annotations

from html import escape
from math import cos, pi, sin
from textwrap import wrap

from examples.notebooks._preview.catalogue import DefinitionRecord, ViewRecord
from examples.notebooks._preview.consistency import MAX_VIEW_NODES
from examples.notebooks._preview.models import Choice, Panel, Scene

STYLE = """
<style>
.dk-preview {--dk-bg:var(--vscode-editor-background,#fff);
 --dk-fg:var(--vscode-editor-foreground,#172b42);
 --dk-muted:var(--vscode-descriptionForeground,#60758a);
 --dk-line:var(--vscode-widget-border,#d7e2e9);
 --dk-soft:var(--vscode-editorWidget-background,#f2f7fa);
 --dk-accent:var(--vscode-textLink-foreground,#087e8b);
 color:var(--dk-fg);background:var(--dk-bg);font:14px/1.6 system-ui,sans-serif;
 border:1px solid var(--dk-line);border-radius:14px;margin:12px 0 20px;
 padding:26px 30px;max-width:1120px;box-sizing:border-box;}
.dk-preview * {box-sizing:border-box;}
.dk-preview .dk-eyebrow {font:600 11px/1.5 ui-monospace,monospace;
 letter-spacing:1.5px;color:var(--dk-accent);text-transform:uppercase;}
.dk-preview h2 {font-size:27px;line-height:1.25;letter-spacing:-.6px;margin:10px 0;}
.dk-preview h3 {font-size:16px;margin:23px 0 10px;}
.dk-preview .dk-lead {font-size:15px;max-width:850px;}
.dk-preview .dk-note {color:var(--dk-muted);font-size:12px;}
.dk-preview .dk-badge {display:inline-block;border:1px solid var(--dk-line);
 border-radius:20px;padding:3px 10px;margin:3px 6px 3px 0;font-size:11px;}
.dk-preview .dk-callout {border-left:3px solid var(--dk-accent);background:var(--dk-soft);
 padding:12px 16px;margin-top:18px;border-radius:0 8px 8px 0;}
.dk-preview .dk-scroll {overflow-x:auto;}
.dk-preview table {border-collapse:collapse;width:100%;text-align:left;font-size:13px;}
.dk-preview th {font-size:11px;text-transform:uppercase;letter-spacing:.6px;
 color:var(--dk-muted);background:var(--dk-soft);}
.dk-preview th,.dk-preview td {padding:10px 12px;border-bottom:1px solid var(--dk-line);
 vertical-align:top;text-align:left;overflow-wrap:anywhere;}
.dk-preview tr.dk-changed {border-left:3px solid var(--dk-accent);background:var(--dk-soft);}
.dk-preview tr.dk-unchanged {color:var(--dk-muted);}
.dk-preview svg {width:100%;height:auto;min-width:560px;display:block;}
.dk-preview pre {background:var(--dk-soft);padding:16px;border-radius:8px;
 white-space:pre-wrap;overflow-wrap:anywhere;color:var(--dk-fg);}
.dk-preview a {color:var(--dk-accent);text-decoration:underline;}
.dk-controls .widget-label,.dk-controls .widget-html-content {color:var(--dk-fg);}
.dk-controls select,.dk-controls textarea,.dk-controls .widget-button,
.dk-controls .p-Accordion-header,.dk-controls .jupyter-widgets.widget-container {
 color:var(--dk-fg);background:var(--dk-soft);border-color:var(--dk-line);}
.dk-controls .jupyter-widget-Collapse-header,
.dk-controls .jupyter-widget-Collapse-open>.jupyter-widget-Collapse-header,
.dk-controls .jupyter-widget-Collapse-contents {
 color:var(--dk-fg);background:var(--dk-soft);border-color:var(--dk-line);}
.dk-controls .widget-button.mod-info:not(:disabled) {
 color:var(--dk-bg);background:var(--dk-accent);}
.dk-controls button:focus-visible,.dk-controls select:focus-visible,
.dk-controls textarea:focus-visible {outline:2px solid var(--dk-accent);outline-offset:2px;}
.dk-controls .widget-button:disabled {opacity:.5;}
.dk-preview .dk-grid {display:grid;
 grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;}
.dk-preview h2 {font-family:Georgia,serif;font-weight:500;font-size:30px;}
.dk-preview summary {cursor:pointer;padding:12px 0;font-weight:600;}
.dk-preview details {border-top:1px solid var(--dk-line);margin-top:16px;}
.dk-preview summary:focus-visible,.dk-preview a:focus-visible {
 outline:2px solid var(--dk-accent);outline-offset:3px;}
.dk-preview .dk-focus {border-left:4px solid var(--dk-accent);padding:12px 20px;
 background:var(--dk-soft);margin:18px 0 24px;}
.dk-preview .dk-focus p {font-size:17px;margin:6px 0;max-width:780px;}
.dk-preview .dk-split {display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
 gap:18px;margin:20px 0;}
.dk-preview .dk-evidence {border:1px solid var(--dk-line);border-radius:8px;padding:20px;}
.dk-preview .dk-evidence h3 {margin-top:0;}
.dk-preview .dk-qualification {border-left:3px solid var(--dk-accent);padding-left:14px;}
.dk-preview .dk-stages {display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));
 gap:12px;list-style:none;padding:0;margin:24px 0;counter-reset:none;}
.dk-preview .dk-stage {border-top:3px solid var(--dk-accent);background:var(--dk-soft);
 padding:14px;min-width:0;}
.dk-preview .dk-stage h3 {margin:10px 0;font-size:16px;line-height:1.35;}
.dk-preview .dk-stage p {font-size:12px;margin:0;}
.dk-preview .dk-step {font:28px/1.4 Georgia,serif;color:var(--dk-muted);display:block;}
.dk-preview .dk-metrics {display:flex;flex-wrap:wrap;gap:14px;margin:20px 0;}
.dk-preview .dk-metrics>div {flex:1;min-width:150px;border-left:2px solid var(--dk-line);
 padding:8px 16px;}
.dk-preview .dk-metrics span {display:block;color:var(--dk-muted);font-size:12px;}
.dk-preview .dk-metrics strong {font-size:17px;font-weight:600;}
.dk-preview .dk-matrix {min-width:740px;table-layout:fixed;}
.dk-preview .dk-matrix th:first-child {width:230px;}
.dk-preview .dk-matrix td,.dk-preview .dk-matrix th {text-align:center;padding:9px 5px;}
.dk-preview .dk-matrix th[scope=row] {text-align:left;text-transform:none;letter-spacing:0;}
.dk-preview .dk-matrix .dk-connected {background:var(--dk-soft);font-weight:700;}
.dk-preview .dk-matrix abbr {text-decoration:none;}
.dk-preview .dk-progress {display:flex;gap:4px;margin:16px 0 20px;}
.dk-preview .dk-progress span {height:4px;background:var(--dk-line);flex:1;}
.dk-preview .dk-progress .dk-current {background:var(--dk-accent);}
.dk-controls .widget-text input[type=text],
.dk-controls .widget-toggle-buttons .widget-toggle-button {
 color:var(--dk-fg);background:var(--dk-soft);border-color:var(--dk-line);}
.dk-controls .widget-toggle-buttons .widget-toggle-button.mod-active {
 color:var(--dk-bg);background:var(--dk-accent);}
.dk-controls input:focus-visible {outline:2px solid var(--dk-accent);outline-offset:2px;}
@media print {.dk-preview details>* {display:block!important;}}
@media (prefers-color-scheme:dark) {
 .dk-preview {--dk-bg:var(--vscode-editor-background,#18232e);
 --dk-fg:var(--vscode-editor-foreground,#edf3f8);
 --dk-muted:var(--vscode-descriptionForeground,#b0c3d3);
 --dk-line:var(--vscode-widget-border,#425566);
 --dk-soft:var(--vscode-editorWidget-background,#233443);
 --dk-accent:var(--vscode-textLink-foreground,#5ad2d1);}
}
</style>
"""


def render_table(*, panel: Panel) -> str:
    """Render a bounded fixture table with explicit header associations."""
    if not panel.rows:
        return f"<p class='dk-note'>{escape(panel.note)}</p>" if panel.note else ""
    headings = "".join(f'<th scope="col">{escape(column)}</th>' for column in panel.columns)
    rows = "".join(
        (
            '<tr class="dk-changed">'
            if row[0] in {"Added", "Removed"}
            else '<tr class="dk-unchanged">'
            if row[0] == "Unchanged"
            else "<tr>"
        )
        + "".join(f"<td>{escape(cell)}</td>" for cell in row)
        + "</tr>"
        for row in panel.rows
    )
    return (
        f"<h3>{escape(panel.title)}</h3><div class='dk-scroll'><table>"
        f"<thead><tr>{headings}</tr></thead><tbody>{rows}</tbody></table></div>"
        f"<p class='dk-note'>{escape(panel.note)}</p>"
    )


def available_views(*, scene: Scene) -> tuple[ViewRecord, ...]:
    """Resolve bounded named viewports without hiding the full inventory."""
    names = {node.id for node in scene.nodes}
    views = tuple(
        view.model_copy(
            update={"definitions": tuple(name for name in view.definitions if name in names)}
        )
        for view in scene.views
        if any(name in names for name in view.definitions)
    )
    if views:
        return views
    return (
        ViewRecord(
            id="overview",
            title="Model overview",
            definitions=tuple(node.id for node in scene.nodes),
        ),
    )


def _connections(*, scene: Scene, view: ViewRecord) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        (edge.source, edge.target, edge.label, edge.kind)
        for edge in scene.edges
        if edge.source in view.definitions and edge.target in view.definitions
    ) + tuple(
        (item.name, field.target, field.name, "attribute reference")
        for item in scene.definitions
        for field in item.attributes
        if field.target is not None
        and item.name in view.definitions
        and field.target in view.definitions
    )


def render_connection_matrix(*, scene: Scene, view_id: str) -> str:
    """Read dense directed connections without intersecting edges or hidden labels."""
    view = next((item for item in available_views(scene=scene) if item.id == view_id), None)
    if view is None:
        return ""
    by_name = {node.id: node for node in scene.nodes}
    connections = _connections(scene=scene, view=view)
    headers = "".join(
        f'<th scope="col"><abbr title="{escape(by_name[name].label, quote=True)}">'
        f"{index}</abbr></th>"
        for index, name in enumerate(view.definitions, start=1)
    )
    rows = []
    for index, source in enumerate(view.definitions, start=1):
        cells = []
        for target in view.definitions:
            matches = [
                (label, kind) for a, b, label, kind in connections if (a, b) == (source, target)
            ]
            description = "; ".join(f"{label} ({kind})" for label, kind in matches)
            codes = " + ".join("R" if kind == "attribute reference" else "D" for _, kind in matches)
            content = (
                f'<abbr title="{escape(description, quote=True)}">{codes}</abbr>'
                if matches
                else "·"
            )
            accessible = f"{by_name[source].label} to {by_name[target].label}: " + (
                description or "no connection"
            )
            cells.append(
                f'<td class="{"dk-connected" if matches else ""}" '
                f'aria-label="{escape(accessible, quote=True)}">'
                f"{content}</td>"
            )
        rows.append(
            f'<tr><th scope="row">{index}. {escape(by_name[source].label)}</th>'
            + "".join(cells)
            + "</tr>"
        )
    return (
        "<h3>Connection matrix</h3><p>Rows are sources; numbered columns are targets. "
        "D = domain relationship; R = attribute reference. A dot means no connection "
        "in this view, not a prohibited relationship.</p>"
        '<div class="dk-scroll"><table class="dk-matrix"><caption>'
        f"{escape(view.title)} · {len(connections)} directed connections</caption>"
        f'<thead><tr><th scope="col">Source → target</th>{headers}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        + render_table(
            panel=Panel(
                title="Read each connection",
                columns=("Source", "Connection", "Target", "Role"),
                rows=tuple(
                    (by_name[a].label, label, by_name[b].label, kind)
                    for a, b, label, kind in connections
                ),
                note=(
                    "The diagram and matrix use exactly the same connections. "
                    "Evidence and formal assertions are inspected separately."
                ),
            )
        )
    )


def render_graph(
    *,
    scene: Scene,
    selected: str | None = None,
    view_id: str | None = None,
    collapse_table: bool = False,
) -> str:
    """Draw one named view with explicit edge roles and an equivalent table."""
    if not scene.nodes:
        return ""
    views = available_views(scene=scene)
    view = next((item for item in views if item.id == view_id), views[0])
    if len(view.definitions) > MAX_VIEW_NODES:
        raise ValueError("A diagram view must contain at most twelve definitions; split the view.")
    by_name = {node.id: node for node in scene.nodes}
    nodes = tuple(by_name[name] for name in view.definitions)
    connections = _connections(scene=scene, view=view)
    # Place nodes around the perimeter so connections cannot run behind an unrelated node.
    positions = {
        node.id: (
            585 + 470 * cos(-pi / 2 + index * 2 * pi / len(nodes)),
            350 + 270 * sin(-pi / 2 + index * 2 * pi / len(nodes)),
        )
        for index, node in enumerate(nodes)
    }
    height = 710
    marker = f"arrow-{scene.id}-{view.id}"
    diagram = [
        (
            f"<h3>{escape(view.title)}</h3><p class='dk-note'>{len(nodes)} of "
            f"{len(scene.nodes)} non-relationship definitions · {len(connections)} connections "
            "in this view. The complete inventory follows.</p>"
        ),
        (
            f'<div class="dk-scroll"><svg viewBox="0 0 1170 {height}" role="img" '
            f'aria-label="{escape(view.title)}: {len(nodes)} definitions">'
        ),
        (
            f'<defs><marker id="{escape(marker)}" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path d="M 0 0 L 10 5 L 0 10 z" fill="var(--dk-accent)"/></marker></defs>'
        ),
    ]
    label_positions: list[tuple[float, float]] = []
    labels: list[str] = []
    for number, (source, target, label, kind) in enumerate(connections, start=1):
        if target is None:
            continue
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            continue
        factor = max(abs(dx) / 105, abs(dy) / 50)
        start_x, start_y = x1 + dx / factor, y1 + dy / factor
        end_x, end_y = x2 - dx / factor, y2 - dy / factor
        opacity = "1" if selected in (None, source, target) else ".25"
        dash = 'stroke-dasharray="5 5"' if kind == "attribute reference" else ""
        # Curved lanes separate parallel associations. Numbers resolve to exact table rows,
        # avoiding overlapping long relationship names without dropping connections.
        lane = 26 + (number % 3) * 20
        distance = (dx * dx + dy * dy) ** 0.5
        control_x = (x1 + x2) / 2 - dy / distance * lane
        control_y = (y1 + y2) / 2 + dx / distance * lane
        # Shift a number along its own curve when a prior number occupies the midpoint.
        candidates = (
            (
                (1 - t) ** 2 * start_x + 2 * (1 - t) * t * control_x + t**2 * end_x,
                (1 - t) ** 2 * start_y + 2 * (1 - t) * t * control_y + t**2 * end_y,
            )
            for t in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8)
        )
        label_x, label_y = next(
            (x, y)
            for x, y in candidates
            if all((x - a) ** 2 + (y - b) ** 2 >= 30**2 for a, b in label_positions)
        )
        label_positions.append((label_x, label_y))
        diagram.append(
            f'<g opacity="{opacity}"><path d="M {start_x} {start_y} '
            f'Q {control_x} {control_y} {end_x} {end_y}" '
            f'stroke="var(--dk-accent)" stroke-width="2" {dash} fill="none" '
            f'marker-end="url(#{escape(marker)})"/>'
            f"<title>{number}: {escape(label)} ({escape(kind)})</title></g>"
        )
        labels.append(
            f'<g opacity="{opacity}">'
            f'<circle cx="{label_x}" cy="{label_y}" r="12" fill="var(--dk-bg)" '
            'stroke="var(--dk-accent)"/>'
            f'<text x="{label_x}" y="{label_y + 4}" text-anchor="middle" '
            f'fill="var(--dk-fg)" font-size="11">{number}</text>'
            f"<title>{number}: {escape(label)} ({escape(kind)})</title></g>"
        )
    # Draw all number badges above all edges, so later paths cannot obscure digits.
    diagram.extend(labels)
    for node in nodes:
        x, y = positions[node.id]
        stroke = "var(--dk-accent)" if selected == node.id else "var(--dk-line)"
        diagram.append(
            f'<rect x="{x - 105}" y="{y - 50}" width="210" height="100" rx="12" '
            f'fill="var(--dk-soft)" stroke="{stroke}" stroke-width="2"/>'
        )
        for index, line in enumerate(wrap(node.label, width=22)):
            diagram.append(
                f'<text x="{x}" y="{y - 13 + index * 18}" text-anchor="middle" '
                f'fill="var(--dk-fg)" font-size="15" font-weight="600">{escape(line)}</text>'
            )
        diagram.append(
            f'<text x="{x}" y="{y + 37}" text-anchor="middle" fill="var(--dk-muted)" '
            f'font-size="11">{escape(node.kind.replace("_", " ").upper())}</text>'
        )
    diagram.append("</svg></div>")
    if collapse_table:
        diagram.append("<details><summary>Read the numbered connections as a table</summary>")
    diagram.append(
        render_table(
            panel=Panel(
                title="Relationship table — the same view without the diagram",
                columns=("#", "Source", "Connection", "Target", "Role"),
                rows=tuple(
                    (str(number), by_name[source].label, label, by_name[target].label, kind)
                    for number, (source, target, label, kind) in enumerate(connections, start=1)
                    if target is not None
                ),
                note=(
                    "Numbers match diagram connections. Solid: domain relationship. "
                    "Dashed: attribute reference. Evidence is "
                    "shown in citation tables; business mappings do not assert formal "
                    "ontology equivalence."
                ),
            )
        )
    )
    if collapse_table:
        diagram.append("</details>")
    return "".join(diagram)


def render_definition(
    *,
    scene: Scene,
    definition: DefinitionRecord,
    status: str = "Accepted in this simulated snapshot",
) -> str:
    """Inspect meaning, field-level evidence and review history from loaded records."""
    fields = (
        render_table(
            panel=Panel(
                title="Attributes and their modelling basis",
                columns=(
                    "Field",
                    "Shape",
                    "Presence",
                    "Meaning / qualification",
                    "Basis",
                    "Evidence",
                ),
                rows=tuple(
                    (
                        field.name,
                        field.value_type
                        + (f" → {field.target}" if field.target else "")
                        + f" / {field.collection}",
                        "required" if field.required else "optional",
                        field.meaning + " " + field.qualification,
                        field.basis,
                        ", ".join(field.evidence),
                    )
                    for field in definition.attributes
                ),
                note=(
                    "Presence is a shape contract, not a finding of legal compliance. "
                    "Field-level meanings, basis labels and citations are teaching annotations "
                    "over the reviewed definitions, not additional SDK attribute parameters."
                ),
            )
        )
        if definition.attributes
        else ""
    )
    details = (
        definition.details
        + tuple(("Key", ", ".join(key)) for key in definition.keys)
        + definition.members
    )
    detail_table = (
        render_table(
            panel=Panel(title="Definition detail", columns=("Element", "Meaning"), rows=details)
        )
        if details
        else ""
    )
    evidence_ids = (
        set(definition.evidence)
        | {key for field in definition.attributes for key in field.evidence}
        | {key for annotation in definition.annotations for key in annotation.evidence}
    )
    annotations = (
        render_table(
            panel=Panel(
                title="Conditions and modelling choices",
                columns=("Element", "Meaning", "Basis", "Evidence"),
                rows=tuple(
                    (item.element, item.meaning, item.basis, ", ".join(item.evidence))
                    for item in definition.annotations
                ),
                note=(
                    "Inspection annotations on existing descriptive definitions; "
                    "these conditions are not executable rules."
                ),
            )
        )
        if definition.annotations
        else ""
    )
    related = render_table(
        panel=Panel(
            title="Related definitions",
            columns=("Source", "Connection", "Target", "Role"),
            rows=tuple(
                (edge.source, edge.label, edge.target, edge.kind)
                for edge in scene.edges
                if definition.name in (edge.source, edge.target)
            )
            + tuple(
                (item.name, field.name, field.target, "attribute reference")
                for item in scene.definitions
                for field in item.attributes
                if field.target is not None and definition.name in (item.name, field.target)
            ),
        )
    )
    citations = []
    for source in scene.source_records:
        for passage in source.passages:
            if passage.id not in evidence_ids:
                continue
            link = (
                f'<a href="{escape(source.url, quote=True)}" target="_blank" '
                'rel="noopener noreferrer">Open original source</a>'
                if source.url.startswith(("https://", "http://"))
                else ""
            )
            citations.append(
                f"<li><strong>{escape(passage.id)} · {escape(passage.locator)}</strong>"
                f'<p>{escape(passage.text)}</p><p class="dk-note">{escape(source.edition)} · '
                f"{escape(passage.kind)} · {escape(source.verification)}</p>{link}</li>"
            )
    mappings = render_table(
        panel=Panel(
            title="Reviewed reference mappings",
            columns=("Relation", "Original IRI", "Decision", "Reason"),
            rows=tuple(
                (m.relation, m.iri, m.decision, m.explanation)
                for m in scene.mappings
                if m.definition == definition.name
            ),
        )
    )
    reviews = render_table(
        panel=Panel(
            title="Attributed review history",
            columns=("Case", "Action", "Actor", "Reason"),
            rows=tuple(
                (r.id, r.action, r.actor, r.reason)
                for r in scene.reviews
                if definition.name in r.targets
            ),
        )
    )
    return (
        f'<h3>{escape(definition.display_name)}</h3><p class="dk-note">'
        f"{escape(definition.id)} · {escape(definition.name)} · revision "
        f"{definition.revision} · {escape(definition.kind)}</p>"
        f'<span class="dk-badge">{escape(definition.basis)}</span>'
        f'<span class="dk-badge">{escape(status)}</span>'
        f"<p>{escape(definition.meaning)}</p>"
        + fields
        + detail_table
        + annotations
        + related
        + "<h3>Source evidence</h3><ul>"
        + "".join(citations)
        + "</ul>"
        + mappings
        + reviews
    )


def render_inventory(*, scene: Scene) -> str:
    """Present all definitions, including those outside the selected diagram."""
    if not scene.definitions:
        return ""
    table = render_table(
        panel=Panel(
            title="Complete definition inventory",
            columns=("Name", "Kind / revision", "Meaning", "Basis", "Evidence"),
            rows=tuple(
                (d.name, f"{d.kind} / {d.revision}", d.meaning, d.basis, ", ".join(d.evidence))
                for d in scene.definitions
            ),
            note=(
                "All accepted definitions in this snapshot. The catalogue describes types; "
                "individual systems, candidates and logs belong to the host application."
            ),
        )
    )
    return (
        f"<details><summary>Browse all {len(scene.definitions)} definitions</summary>"
        f"{table}</details>"
    )


def render_snapshot(*, scene: Scene, selected: str | None = None) -> str:
    """Render the canonical result with static alternatives for each named view."""
    primary_titles = {
        "C6": "Keep the two document meanings separate",
        "C7": "Inspect the field changes",
        "C10": "Compared definition revisions",
    }
    primary = next(
        (panel for panel in scene.panels if panel.title == primary_titles.get(scene.id)),
        scene.panels[0],
    )
    panels = render_table(panel=primary)
    supporting = "".join(render_table(panel=panel) for panel in scene.panels if panel != primary)
    views = available_views(scene=scene)
    default = "actors" if scene.catalogue_snapshot == "seed" else "documentation"
    graph = render_graph(scene=scene, selected=selected, view_id=default, collapse_table=True)
    if graph and scene.id not in {"C2", "C8"}:
        graph = (
            "<details><summary>Explore the accepted model — diagram and connection matrix</summary>"
            + graph
            + render_connection_matrix(scene=scene, view_id=default)
            + "</details>"
        )
    elif graph and scene.id == "C8":
        graph += (
            "<details><summary>Read this model as a connection matrix</summary>"
            + render_connection_matrix(scene=scene, view_id=default)
            + "</details>"
        )
    alternatives = ""
    if scene.id in {"C8", "C9", "C10"}:
        alternatives = "".join(
            f"<details><summary>{escape(view.title)} — static view</summary>"
            f"{render_graph(scene=scene, view_id=view.id)}</details>"
            for view in views
            if view.id != default
        )
    count = (
        f"{len(scene.definitions)} definitions · {len(scene.edges)} relationship definitions"
        if scene.definitions
        else "Independent sample exercise"
    )
    progress = ""
    if scene.id.startswith("C"):
        chapter = int(scene.id[1:])
        progress = (
            f'<div class="dk-progress" role="img" aria-label="Main journey: step {chapter} of 10">'
            + "".join(
                '<span class="dk-current"></span>' if step <= chapter else "<span></span>"
                for step in range(1, 11)
            )
            + "</div>"
        )
    return (
        STYLE
        + '<section class="dk-preview">'
        + f'<div class="dk-eyebrow">DOMAIN KERNEL / {escape(scene.id)} / DEVELOPER TOUR</div>'
        + f"<h2>{escape(scene.title)}</h2>"
        + '<span class="dk-badge">Simulated SDK result</span>'
        + f'<span class="dk-badge">Snapshot: {escape(scene.snapshot)}</span>'
        + progress
        + f'<p class="dk-note">{count}</p>'
        + '<div class="dk-focus"><div class="dk-eyebrow">THE RESULT TO UNDERSTAND</div>'
        + f"<p>{escape(scene.expected)}</p></div>"
        + panels
        + graph
        + "<details><summary>Inspect supporting detail</summary>"
        + f'<p class="dk-lead">{escape(scene.summary)}</p>'
        + supporting
        + "</details>"
        + alternatives
        + render_inventory(scene=scene)
        + '<p class="dk-note">Canonical walkthrough · Sample actors and outcomes · '
        + f"Implementation owners: {escape(', '.join(scene.owners))}</p></section>"
    )


def render_choice(*, choice: Choice, reason: str, status: str) -> str:
    """Show the explicit before/after impact of a separate experiment."""
    panel = Panel(
        title="Inspected sample impact",
        columns=("Before", "After"),
        rows=((choice.before, choice.after),),
        note=choice.explanation,
    )
    return (
        STYLE
        + '<section class="dk-preview"><div class="dk-eyebrow">SEPARATE EXPERIMENT BRANCH</div>'
        + f"<h3>{escape(status)}</h3>"
        + render_table(panel=panel)
        + f"<p><strong>Your reason:</strong> {escape(reason)}</p>"
        + '<p class="dk-note">Simulated action. Canonical walkthrough snapshots are unchanged.</p>'
        + "</section>"
    )


def render_text(*, scene: Scene) -> str:
    """Keep the complete meaning readable when HTML is unavailable or untrusted."""
    sections = [f"{scene.id}: {scene.title} — Simulated SDK result", scene.summary]
    for panel in scene.panels:
        sections.extend((panel.title, " | ".join(panel.columns)))
        sections.extend(" | ".join(row) for row in panel.rows)
        if panel.note:
            sections.append(panel.note)
    if scene.definitions:
        sections.append("Complete definition inventory")
        sections.extend(
            f"{d.id} | {d.name} | {d.kind} | revision {d.revision} | {d.meaning} | "
            f"{d.basis} | {', '.join(d.evidence)}"
            for d in scene.definitions
        )
        sections.append("Relationships")
        sections.extend(f"{edge.source} --{edge.label}--> {edge.target}" for edge in scene.edges)
    sections.append(scene.expected)
    return "\n\n".join(sections)
