# Next AI UIUX

## Core Shape

Next AI is an AI product library. The user does not manage workspaces first. They choose an AI product, start a task with one message, and keep working as the task grows structure.

## First Screen

The first screen should be quiet and direct:

- Left: `Next AI`, new task, AI product list, recent tasks for the selected product.
- Center: selected AI product name, one-line description, input, a few starter tasks.
- Hidden by default: skills, tools, connectors, workbench management, versions, file trees, and product configuration.

The first screen should answer only:

- Which AI product am I using?
- What can I ask it to do?
- Where do I start?
- What has it worked on before?

## Task Screen

After the user sends the first message, the product enters a task screen:

- The conversation becomes the command surface.
- The task title replaces the generic product title.
- If the task benefits from structure, the task interface opens beside the conversation.
- The task interface belongs to this AI product and this task. It is not a separate app builder.

For `PPT Designer`, the first structured interface should expose topic, audience, outline, pages, notes, and style decisions. The user should still be able to type normally at any time.

## Interface Evolution

Users can ask the AI product to improve its task interface in the same conversation:

- "以后开头先让我选模板和受众。"
- "讲稿区固定在右边。"
- "这个界面不好用，先给我大纲再给页面。"

The AI product should respond as itself:

1. Explain that this changes how the AI product handles this kind of task.
2. Generate an interface preview.
3. Let the user use or discard the improvement.
4. Let the user return to the previous interface.

Avoid exposing version numbers, generated paths, manifests, code diffs, or app-builder language. The user should feel that the AI product became easier to use, not that they configured software internals.

## MVP Acceptance

The MVP is acceptable when a new user can understand the path without explanation:

1. Select `PPT Designer`.
2. Start a PPT task from the center input.
3. See the PPT task interface appear only after the task needs it.
4. Ask the AI product to change that interface.
5. Preview the change, use it, discard it, or return to the previous interface.
