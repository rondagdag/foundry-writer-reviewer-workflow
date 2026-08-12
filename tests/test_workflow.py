import asyncio
from types import SimpleNamespace

import app
from agent_framework import Message


class FakeAgent:
    def __init__(self, *, client, name: str, instructions: str) -> None:
        self.name = name

    async def run(self, prompt):
        text = prompt.text if isinstance(prompt, Message) else str(prompt)
        if self.name == "reviewer":
            return SimpleNamespace(text="Use a clearer opening and a more direct conclusion.")
        if "Reviewer feedback:" in text:
            return SimpleNamespace(text="Refined content with a clear opening and direct conclusion.")
        return SimpleNamespace(text="Initial draft content.")


def test_writer_reviewer_workflow_returns_refined_plain_text(monkeypatch) -> None:
    monkeypatch.setattr(app, "Agent", FakeAgent)
    workflow = app.build_workflow(client=object())

    result = asyncio.run(workflow.run(Message("user", ["Write a short article."])))

    assert result.get_outputs() == [
        "Refined content with a clear opening and direct conclusion."
    ]


def test_workflow_supports_hosted_message_lists(monkeypatch) -> None:
    monkeypatch.setattr(app, "Agent", FakeAgent)
    workflow = app.build_workflow(client=object())

    workflow.as_agent()
    assert {executor.id for executor in workflow.get_output_executors()} == {
        "writer",
        "reviewer",
    }