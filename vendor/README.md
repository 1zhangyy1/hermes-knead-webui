# Vendor Repositories

These repositories are local research copies for the AI Space Platform exploration.

They are intentionally kept under `vendor/` so our own product notes and future app code stay separate from upstream projects.

## Hermes-related repos

| Directory | Upstream | Why it matters |
| --- | --- | --- |
| `hermes-agent` | https://github.com/NousResearch/hermes-agent.git | Core Hermes agent runtime: learning loop, skills, memory, tools, gateway, providers, approvals, cron, MCP, and API server. Decision: fully reuse this as our Agent Runtime / Agent OS. |
| `hermes-agent-self-evolution` | https://github.com/NousResearch/hermes-agent-self-evolution.git | Nous companion project for skill/prompt/code self-improvement. Important reference for our Evolution Engine. |
| `hermes-workspace` | https://github.com/outsourc-e/hermes-workspace.git | Native web workspace for Hermes Agent: chat, terminal, memory, skills, inspector. Important reference for a Hermes-facing Host Shell. |
| `hermes-ui` | https://github.com/pyrate-llama/hermes-ui.git | Lightweight Hermes UI. Current reuse path: embed it as the `Meta Chat` / raw mother-console system space first, then gradually native-port the pieces we want. |
| `Hermes-Desktop` | https://github.com/RedWoodOG/Hermes-Desktop.git | Native Windows desktop shell around Hermes. Useful for desktop/app packaging ideas, not likely to be our first base. |

## Local clone notes

All clones were made with `--depth 1` for lightweight research. If we need full history later, run:

```sh
git -C vendor/<repo> fetch --unshallow
```
