This directory contains first-class runtime dependencies for Next AI Chat.

`hermes-agent` is vendored from the official `NousResearch/hermes-agent` repository by `git subtree`. It is part of this product repository because Next AI Chat is built on Hermes as its core agent runtime, not merely as an incidental optional integration.

Runtime source in this directory should stay traceable to upstream. Do not copy new runtime files by hand; use the vendor policy in `docs/architecture/HERMES_VENDORING.md`.
