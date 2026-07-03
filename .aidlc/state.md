# AIDLC State

- **Phase**: implementing
- **Branch**: feat/real-adapter-wiring
- **PR**: (TBD)
- **Last action**: 2026-07-03T23:20:00Z
- **Next action**: Run /implement T-103 (Real AI adapter — Anthropic SDK + Gemini fallback)
- **Notes**: T-101 + T-102 done. RealSupabaseAdapter (PostgREST) + RealLineAdapter
  (Reply/Push API w/ bot-info cache + Markdown strip + 5/4500 chunker +
  self-message echo filter) both shipping. 25 new tests, 162 total
  passing, 5 skipped (real_swap opt-in), coverage 92.75%.
  Starting T-103: Anthropic SDK call (Claude 3.5 Sonnet), typed errors
  (AIRateLimitError / AIError), silent Gemini fallback on 429/5xx/timeout
  per OQ-F, versioned prompt templates in app/adapters/ai/prompts.py.

_Updated: 2026-07-03T23:20:00Z_
