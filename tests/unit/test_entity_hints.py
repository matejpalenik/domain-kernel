from domain_kernel import NamedEntityHints


def test_hints_keep_only_exact_mentions_under_the_selected_profile() -> None:
    def predict(text: str, labels: list[str]) -> list[dict[str, object]]:
        assert labels == ["role"]
        assert text == "the operator"
        return [
            {"label": "role", "text": "operator", "start": 4, "end": 12},
            {"label": "role", "text": "manager", "start": 4, "end": 12},
            {"label": "place", "text": "operator", "start": 4, "end": 12},
        ]

    labels = ["role"]
    hints = NamedEntityHints(predict=predict, profile="roles-v1", labels=labels)
    labels.clear()
    assert [m.text for m in hints("the operator")] == ["operator"]
