# Writer-Reviewer Workflow

A Microsoft Agent Framework workflow in which a Writer drafts content, a Reviewer supplies concise feedback, and the Writer returns refined plain text.

## Setup

The workspace uses `.venv` and is configured for the `gpt-5.4-mini` deployment in the selected Microsoft Foundry project.

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install debugpy pytest==8.3.3
.venv/bin/python -m pip install --no-deps "agent-dev-cli>=0.0.1b260427"
az login
```

The separate `agent-dev-cli` command avoids its outdated `agent-framework-core<1.3.0` dependency cap while retaining the current Agent Framework SDK.

`DefaultAzureCredential` uses your local Azure sign-in. To target another project or deployment, update `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` in `.env`.

## Run

```bash
.venv/bin/python app.py "Write a 150-word launch announcement for a productivity app."
```

The command prints only the refined content.

## Debug

Press `F5` and choose **Debug Local Agent/Workflow HTTP Server** to start the Responses-compatible server and open Foundry Toolkit Agent Inspector. Choose **Debug Local Agent/Workflow in Terminal** for a direct CLI run.

## Test

```bash
.venv/bin/python -m pytest
```