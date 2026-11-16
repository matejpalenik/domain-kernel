"""Standard widgets for local teaching feedback, separate from review controls."""

from __future__ import annotations

from html import escape

import ipywidgets as widgets

from examples.notebooks._preview.practice import Practice, render_feedback, render_solution


class PracticeView:
    """Retain a learner's answers across cell reruns without changing any SDK fixture."""

    def __init__(self, *, exercise: Practice) -> None:
        self.exercise = exercise
        self.inputs: dict[str, widgets.Dropdown | widgets.Text] = {}
        rows: list[widgets.Widget] = []
        for field in exercise.fields:
            control = (
                widgets.Dropdown(
                    options=[
                        ("Choose an answer", ""),
                        *[(o.label, o.value) for o in field.options],
                    ],
                    value="",
                )
                if field.options
                else widgets.Text(value="", placeholder="Enter the lookup name")
            )
            control.description = field.label
            control.style = {"description_width": "initial"}
            control.layout = widgets.Layout(width="min(100%, 950px)")
            control.observe(self._changed, names="value")
            self.inputs[field.key] = control
            rows.append(control)
        self.check_button = widgets.Button(description="Check your answer", icon="check")
        self.hint_button = widgets.Button(description="Hint", icon="lightbulb-o")
        self.solution_button = widgets.Button(description="Show worked answer", icon="book")
        self.reset_button = widgets.Button(description="Reset practice", icon="undo")
        buttons = [self.check_button, self.hint_button, self.solution_button, self.reset_button]
        for button in buttons:
            button.layout = widgets.Layout(width="195px", min_height="36px", margin="4px")
        self.feedback = widgets.HTML(value="<p>Choose your answers, then Check your answer.</p>")
        self.help = widgets.HTML(value="")
        self.check_button.on_click(self._check)
        self.hint_button.on_click(self._hint)
        self.solution_button.on_click(self._solution)
        self.reset_button.on_click(self._reset)
        self.widget = widgets.VBox(
            children=[
                *rows,
                widgets.HBox(children=buttons, layout=widgets.Layout(flex_flow="row wrap")),
                self.feedback,
                self.help,
            ]
        )
        self.widget.add_class("dk-preview")
        self.widget.add_class("dk-controls")

    def _changed(self, _change: dict[str, object]) -> None:
        self.feedback.value = "<p>Answer changed. Check your answer for updated feedback.</p>"

    @property
    def answers(self) -> dict[str, str]:
        """Read normalized text from standard controls without grading it."""
        return {key: str(control.value) for key, control in self.inputs.items()}

    def _check(self, _button: widgets.Button) -> None:
        result = self.exercise.check(answers=self.answers)
        self.feedback.value = render_feedback(exercise=self.exercise, result=result)

    def _hint(self, _button: widgets.Button) -> None:
        hints = "".join(f"<li>{escape(field.hint)}</li>" for field in self.exercise.fields)
        self.help.value = f"<h4>Hint</h4><ul>{hints}</ul>"

    def _solution(self, _button: widgets.Button) -> None:
        self.help.value = render_solution(exercise=self.exercise)

    def _reset(self, _button: widgets.Button) -> None:
        for control in self.inputs.values():
            control.value = ""
        self.help.value = ""
        self.feedback.value = "<p>Practice reset. Choose your answers, then Check your answer.</p>"
