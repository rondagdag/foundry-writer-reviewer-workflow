import argparse
import asyncio
import os
from dataclasses import dataclass

from agent_framework import Agent, Executor, Message, WorkflowBuilder, WorkflowContext, handler
from agent_framework.foundry import FoundryChatClient, ResponsesHostServer
from agent_framework.observability import configure_otel_providers
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


def configure_tracing() -> None:
    configure_otel_providers(vs_code_extension_port=4317, enable_sensitive_data=True)


@dataclass(frozen=True)
class Draft:
    prompt: str
    content: str


@dataclass(frozen=True)
class Review:
    prompt: str
    content: str
    feedback: str


class Writer(Executor):
    def __init__(self, client: FoundryChatClient) -> None:
        self.agent = Agent(
            client=client,
            name="writer",
            instructions=(
                "You are a skilled content writer. Follow the user's request precisely. "
                "Create clear, engaging, accurate content and return only the requested content."
            ),
        )
        super().__init__(id="writer")

    @handler
    async def draft(self, request: Message, ctx: WorkflowContext[Draft]) -> None:
        await self._create_draft(request.text, request, ctx)

    @handler
    async def draft_messages(
        self, request: list[Message], ctx: WorkflowContext[Draft]
    ) -> None:
        if not request:
            raise ValueError("At least one input message is required.")
        await self._create_draft(request[-1].text, request, ctx)

    async def _create_draft(
        self,
        prompt: str,
        request: Message | list[Message],
        ctx: WorkflowContext[Draft],
    ) -> None:
        response = await self.agent.run(request)
        await ctx.send_message(Draft(prompt=prompt, content=response.text.strip()))

    @handler
    async def revise(self, review: Review, ctx: WorkflowContext[Draft, str]) -> None:
        response = await self.agent.run(
            "Original request:\n"
            f"{review.prompt}\n\n"
            "Draft:\n"
            f"{review.content}\n\n"
            "Reviewer feedback:\n"
            f"{review.feedback}\n\n"
            "Rewrite the draft to address the feedback. Return only the refined content."
        )
        await ctx.yield_output(response.text.strip())


class Reviewer(Executor):
    def __init__(self, client: FoundryChatClient) -> None:
        self.agent = Agent(
            client=client,
            name="reviewer",
            instructions=(
                "You are a rigorous content reviewer. Identify the highest-impact improvements "
                "for clarity, completeness, accuracy, tone, and adherence to the request. "
                "Return concise, actionable feedback only."
            ),
        )
        super().__init__(id="reviewer")

    @handler
    async def review(self, draft: Draft, ctx: WorkflowContext[Review, str]) -> None:
        response = await self.agent.run(
            "Original request:\n"
            f"{draft.prompt}\n\n"
            "Draft to review:\n"
            f"{draft.content}\n\n"
            "Provide concise, actionable feedback for the writer."
        )
        await ctx.send_message(
            Review(
                prompt=draft.prompt,
                content=draft.content,
                feedback=response.text.strip(),
            )
        )


def build_workflow(client: FoundryChatClient):
    writer = Writer(client)
    reviewer = Reviewer(client)
    return (
        WorkflowBuilder(
            name="writer-reviewer-content-workflow",
            description="Draft, review, and refine content in one collaboration pass.",
            start_executor=writer,
            output_from=[writer, reviewer],
        )
        .add_edge(writer, reviewer)
        .add_edge(reviewer, writer)
        .build()
    )


def create_workflow():
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    client = FoundryChatClient(
        project_endpoint=endpoint,
        model=model,
        credential=DefaultAzureCredential(),
    )
    return build_workflow(client)


async def run_cli(prompt: str) -> None:
    result = await create_workflow().run(Message("user", [prompt]))
    outputs = result.get_outputs()
    if not outputs:
        raise RuntimeError("The workflow completed without producing refined content.")
    print(str(outputs[-1]))


def main() -> None:
    configure_tracing()
    parser = argparse.ArgumentParser(description="Run the Writer-Reviewer workflow.")
    parser.add_argument("prompt", nargs="?", help="Content request for the writer")
    parser.add_argument("--server", action="store_true", help="Run an OpenAI Responses-compatible server")
    args = parser.parse_args()

    if args.server or not args.prompt:
        ResponsesHostServer(create_workflow().as_agent()).run()
        return
    asyncio.run(run_cli(args.prompt))


if __name__ == "__main__":
    main()