# DETERMINISTIC wrapper / AI dispatcher
"""
LLM Factory — utils/llm_factory.py
Model-agnostic factory pro AI uzly ICM GenAI Platform.

Podporované providery:
  anthropic  (výchozí) — claude-opus-4-6
  openai               — gpt-4o

Konfigurace přes env proměnné:
  LLM_PROVIDER   = "anthropic" | "openai"   (default: anthropic)
  LLM_MODEL      = override modelu           (default: per-provider výchozí)
  ANTHROPIC_API_KEY                          (povinné pro anthropic)
  OPENAI_API_KEY                             (povinné pro openai)

Použití v AI uzlech:
    from utils.llm_factory import get_llm
    llm = get_llm()
    resp = llm.complete(system=skill["prompt"], user_message=ctx, max_tokens=256)
    text   = resp.text
    tokens = resp.tokens_used

Výchozí modely:
  anthropic → claude-opus-4-6
  openai    → gpt-4o
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# ── Výchozí modely ────────────────────────────────────────────────────────────

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-opus-4-6",
    "openai":    "gpt-4o",
}


# ── Response dataclass ────────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    """Jednotný výstup z LLM — nezávislý na provideru."""
    text:        str
    tokens_used: int
    model:       str
    provider:    str


# ── LLMClient ─────────────────────────────────────────────────────────────────

class LLMClient:
    """
    Model-agnostic LLM klient.
    Instanci získej přes `get_llm()` — neinstanciuj přímo.
    """

    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model    = model
        self._client  = self._build_client(provider)
        log.info(f"[LLMFactory] LLMClient init | provider={provider} model={model}")

    # ── Veřejné API ──────────────────────────────────────────────────────────

    def complete(
        self,
        system:       str,
        user_message: str,
        max_tokens:   int = 1024,
    ) -> LLMResponse:
        """
        Odešle completion request na LLM a vrátí `LLMResponse`.

        Args:
            system:       System prompt (instrukce pro model)
            user_message: Uživatelský dotaz / kontext
            max_tokens:   Max výstupních tokenů

        Returns:
            LLMResponse(text, tokens_used, model, provider)

        Raises:
            Exception: při selhání API (caller implementuje retry/freeze)
        """
        if self.provider == "anthropic":
            return self._complete_anthropic(system, user_message, max_tokens)
        if self.provider == "openai":
            return self._complete_openai(system, user_message, max_tokens)
        raise ValueError(f"Nepodporovaný LLM provider: {self.provider!r}")

    # ── Interní implementace ─────────────────────────────────────────────────

    def _build_client(self, provider: str):
        """Inicializuje SDK klienta pro daného providera."""
        if provider == "anthropic":
            import anthropic  # type: ignore
            return anthropic.Anthropic()

        if provider == "openai":
            try:
                import openai  # type: ignore
            except ImportError:
                raise ImportError(
                    "openai balíček není nainstalován. "
                    "Přidej 'langchain-openai' nebo 'openai' do requirements.txt "
                    "a spusť 'pip install openai'."
                )
            return openai.OpenAI()

        raise ValueError(
            f"Nepodporovaný LLM_PROVIDER={provider!r}. "
            f"Povolené hodnoty: {list(_DEFAULT_MODELS)}"
        )

    def _complete_anthropic(
        self,
        system:       str,
        user_message: str,
        max_tokens:   int,
    ) -> LLMResponse:
        """Volání Anthropic Messages API."""
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        text        = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        return LLMResponse(
            text=text,
            tokens_used=tokens_used,
            model=self.model,
            provider=self.provider,
        )

    def _complete_openai(
        self,
        system:       str,
        user_message: str,
        max_tokens:   int,
    ) -> LLMResponse:
        """Volání OpenAI Chat Completions API."""
        response = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system",  "content": system},
                {"role": "user",    "content": user_message},
            ],
        )
        text        = response.choices[0].message.content or ""
        tokens_used = response.usage.total_tokens if response.usage else 0
        return LLMResponse(
            text=text,
            tokens_used=tokens_used,
            model=self.model,
            provider=self.provider,
        )


# ── Factory funkce ────────────────────────────────────────────────────────────

def get_llm(
    provider: Optional[str] = None,
    model:    Optional[str] = None,
) -> LLMClient:
    """
    Vrátí LLMClient nakonfigurovaný dle env proměnných.

    Pořadí priority:
      1. Explicitní argumenty (provider, model)
      2. Env proměnné LLM_PROVIDER, LLM_MODEL
      3. Výchozí hodnoty (anthropic / claude-opus-4-6)

    Args:
        provider: "anthropic" | "openai" (override env)
        model:    název modelu (override env)
    """
    resolved_provider = (
        provider
        or os.getenv("LLM_PROVIDER", "anthropic").lower().strip()
    )
    resolved_model = (
        model
        or os.getenv("LLM_MODEL", "")
        or _DEFAULT_MODELS.get(resolved_provider, "claude-opus-4-6")
    )
    return LLMClient(provider=resolved_provider, model=resolved_model)


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    os.environ.setdefault("ICM_ENV", "demo")

    provider = os.getenv("LLM_PROVIDER", "anthropic")
    model    = os.getenv("LLM_MODEL", _DEFAULT_MODELS.get(provider, "claude-opus-4-6"))

    print(f"LLM_PROVIDER : {provider}")
    print(f"LLM_MODEL    : {model}")

    if not os.getenv("ANTHROPIC_API_KEY") and provider == "anthropic":
        print("ANTHROPIC_API_KEY není nastavena — přeskakuji live test.")
        print("Factory init test:")
        llm = get_llm()
        assert llm.provider == provider
        assert llm.model == model
        print(f"  get_llm() → provider={llm.provider} model={llm.model}  ✓")
    elif not os.getenv("OPENAI_API_KEY") and provider == "openai":
        print("OPENAI_API_KEY není nastavena — přeskakuji live test.")
    else:
        llm = get_llm()
        resp = llm.complete(
            system="Odpověz JSON: {\"status\": \"ok\"}",
            user_message="ping",
            max_tokens=32,
        )
        print(f"  Response: {resp.text[:80]}")
        print(f"  Tokens:   {resp.tokens_used}")

    print("OK — llm_factory.py smoke test passed")
