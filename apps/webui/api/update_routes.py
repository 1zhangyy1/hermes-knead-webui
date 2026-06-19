"""Self-update route helpers."""

from __future__ import annotations

import uuid


def _update_target(body) -> str:
    return body.get("target", "") if isinstance(body, dict) else ""


def handle_update_apply(handler, body, *, json_response_fn, bad_response_fn):
    target = _update_target(body)
    if target not in ("webui", "agent"):
        return bad_response_fn(handler, 'target must be "webui" or "agent"')
    from api.updates import apply_update

    return json_response_fn(handler, apply_update(target))


def handle_update_force(handler, body, *, json_response_fn, bad_response_fn):
    target = _update_target(body)
    if target not in ("webui", "agent"):
        return bad_response_fn(handler, 'target must be "webui" or "agent"')
    from api.updates import apply_force_update

    return json_response_fn(handler, apply_force_update(target))


def build_update_summary_llm_callback(*, logger):
    def _llm_update_summary(system_prompt: str, user_prompt: str) -> str:
        from api import profiles as profiles_api

        active_profile = profiles_api.get_active_profile_name() or "default"

        with profiles_api.profile_env_for_background_worker(
            active_profile,
            "update summary",
            logger_override=logger,
        ):
            from api.config import (
                get_effective_default_model,
                resolve_custom_provider_connection,
                resolve_model_provider,
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            main_model, main_provider, main_base_url = resolve_model_provider(
                get_effective_default_model()
            )
            main_api_key = None
            try:
                from api.oauth import resolve_runtime_provider_with_anthropic_env_lock
                from hermes_cli.runtime_provider import resolve_runtime_provider

                runtime = resolve_runtime_provider_with_anthropic_env_lock(
                    resolve_runtime_provider,
                    requested=main_provider,
                )
                main_api_key = runtime.get("api_key")
                if not main_provider:
                    main_provider = runtime.get("provider")
                if not main_base_url:
                    main_base_url = runtime.get("base_url")
            except Exception as exc:
                logger.debug("update summary runtime provider resolution failed: %s", exc)
            if isinstance(main_provider, str) and main_provider.startswith("custom:"):
                custom_key, custom_base = resolve_custom_provider_connection(main_provider)
                if not main_api_key and custom_key:
                    main_api_key = custom_key
                if not main_base_url and custom_base:
                    main_base_url = custom_base

            main_runtime = {
                "provider": main_provider,
                "model": main_model,
                "base_url": main_base_url,
                "api_key": main_api_key,
            }

            try:
                from agent.auxiliary_client import get_text_auxiliary_client

                aux_client, aux_model = get_text_auxiliary_client(
                    "compression",
                    main_runtime=main_runtime,
                )
                if aux_client is not None and aux_model:
                    response = aux_client.chat.completions.create(
                        model=aux_model,
                        messages=messages,
                    )
                    return str(response.choices[0].message.content or "").strip()
            except Exception as exc:
                logger.debug(
                    "update summary auxiliary model failed; falling back to main model: %s",
                    exc,
                )

            from run_agent import AIAgent

            agent = AIAgent(
                model=main_model,
                provider=main_provider,
                base_url=main_base_url,
                api_key=main_api_key,
                platform="webui",
                quiet_mode=True,
                enabled_toolsets=[],
                session_id=f"updates-summary-{uuid.uuid4().hex[:8]}",
            )
            result = agent.run_conversation(
                user_message=user_prompt,
                system_message=system_prompt,
                conversation_history=[],
                task_id=f"updates-summary-{uuid.uuid4().hex[:8]}",
            )
            return str(result.get("final_response") or "").strip()

    return _llm_update_summary


def handle_update_summary(handler, body, *, json_response_fn, logger):
    from api.updates import summarize_update_payload

    updates = body.get("updates") if isinstance(body, dict) else {}
    target = body.get("target") if isinstance(body, dict) else None
    llm_callback = build_update_summary_llm_callback(logger=logger)
    return json_response_fn(
        handler,
        summarize_update_payload(updates, llm_callback=llm_callback, target=target),
    )
