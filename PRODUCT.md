# Product

## Register

product

## Users

Next AI is for people who use AI to finish real work, not to configure agents for its own sake. They may be making decks, researching a topic, analyzing data, writing, planning, or building a repeatable personal workflow. They arrive with a task in mind, often uncertain about the exact structure, and need an AI product that can turn a first sentence into a usable workspace.

The first target user for the MVP is someone using `PPT Designer`: they want to describe a presentation, upload or reference material, discuss the direction with AI, and see a task interface grow into the parts that make PPT work easier: topic, audience, outline, pages, speaker notes, and style decisions.

## Product Purpose

Next AI is an AI product library. Users choose, create, and evolve AI products. An AI product is a long-lived work object with its own role, task history, skills, tools, and task interface. It starts from chat, but when a task needs more structure, it can grow a workspace-like interface for the current task.

Success means users understand the product in the first screen: choose an AI product, say what they want, and keep working. They should not need to understand manifests, sandboxes, version directories, plugin systems, or app builders. The interface should make the AI product feel increasingly useful over time because it can adapt its task flow and workspace UI through preview, apply, and recovery.

## Brand Personality

Calm, capable, adaptive.

The product should feel like a focused work tool with a living AI core. It should be clear before it is clever, sparse before it is expressive, and confident without becoming technical. The AI should feel present through useful task interfaces and good defaults, not through excessive explanation.

## Anti-references

Do not make the product feel like a generic AI assistant list, a plugin marketplace, a developer app builder, or a Lovable-style external app generator.

Avoid first screens dominated by workbench management, connector catalogs, skill stores, project trees, version history, or configuration forms. Avoid explaining the product with terms like default workspace, left chat, right panel, manifest, sandbox, generated space, code diff, or version directory.

Avoid over-designed SaaS chrome: decorative cards, large marketing heroes, gradient text, glass panels, nested cards, ornamental shadows, and feature-heavy sidebars. The UI should not look like it is trying to prove the idea through visual noise.

## Design Principles

1. Chat is the entry, not the whole product.
   Users start with natural language. The AI product decides when a task needs more structure and grows the right workspace UI.

2. The selected AI product is the primary object.
   The first screen should answer: which AI product is selected, what it does, where to start, what it has done before, and how to create another AI product.

3. Progressive disclosure beats explanation.
   Hide advanced concepts until the task creates a reason to show them. Skills, tools, connectors, versions, and evolution history should not compete with the first task.

4. The workspace belongs to the task.
   A workspace UI is not a separate app. It is the current AI product making the current task easier to inspect and edit.

5. Evolution happens through use.
   Users can say what feels wrong or what should happen next time. The AI product proposes an interface or flow improvement, previews it, and applies it only after confirmation.

## MVP UI Model

The default screen is simple: a left AI product library and a central start surface for the selected AI product. Users do not start by choosing a workspace. They choose an AI product, then start a new task.

The selected AI product owns four things:

- Role: what kind of work it is responsible for.
- Memory: previous tasks and learned preferences.
- Capabilities: skills and tools it can use.
- Task interface: the UI it can open or improve when a task needs structure.

For `PPT Designer`, the first task should feel like a normal AI chat until PPT structure becomes useful. Then the task interface can open with topic, audience, outline, pages, notes, and style controls. The chat remains the command surface: users can ask for content changes, workflow changes, or interface changes in the same place.

When a user asks to improve the task interface, the product should not jump into app-builder mode. It should explain that this changes how `PPT Designer` handles PPT tasks, generate a preview, let the user apply or discard it, and allow recovery to the previous interface.

## Accessibility & Inclusion

Default to WCAG AA contrast for text and controls. Use system fonts and familiar product UI patterns. The product should remain usable with reduced motion, keyboard navigation, long Chinese and English labels, and compact desktop screens.

Animations should communicate state changes only. Critical actions like applying a workspace improvement, discarding an improvement, or returning to a previous workspace need clear labels and recoverable outcomes.
