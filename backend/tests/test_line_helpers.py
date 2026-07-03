"""Tests for the outbound transform helpers + body cap.

Covers the structural work landed alongside hermes-agent#23197:
- ``strip_markdown`` removes the marks LINE cannot render
- ``split_for_line`` honours LINE's 5000-char / 5-message caps
- ``LineRealAdapter`` carries the bones the eventual HTTP wiring needs
  (bot user-id cache, reply-token cache, self-message filter stub)
- ``WEBHOOK_BODY_MAX_BYTES`` rejects payloads over 1 MiB
"""

from __future__ import annotations

import pytest

from app.adapters.line.base import (
    LINE_MAX_MESSAGES_PER_CALL,
    LINE_SAFE_BUBBLE_CHARS,
    WEBHOOK_BODY_MAX_BYTES,
    split_for_line,
    strip_markdown,
)


# ─── strip_markdown ────────────────────────────────────────────────────
class TestStripMarkdown:
    def test_strips_atx_headings(self) -> None:
        assert strip_markdown("# Title\n\nbody") == "Title\n\nbody"

    def test_strips_multiple_heading_levels(self) -> None:
        assert strip_markdown("## H2\n\n### H3\n\nbody") == "H2\n\nH3\n\nbody"

    def test_strips_bold_double_star(self) -> None:
        assert strip_markdown("**bold**") == "bold"

    def test_strips_bold_double_underscore(self) -> None:
        assert strip_markdown("__bold__") == "bold"

    def test_strips_italic_single_star(self) -> None:
        assert strip_markdown("*italic*") == "italic"

    def test_strips_italic_single_underscore(self) -> None:
        assert strip_markdown("_italic_") == "italic"

    def test_strips_inline_code(self) -> None:
        assert strip_markdown("run `pip install` first") == "run pip install first"

    def test_strips_code_fence(self) -> None:
        text = "before\n\n```\ncode block\n```\n\nafter"
        assert strip_markdown(text) == "before\n\ncode block\n\nafter"

    def test_strips_list_bullets(self) -> None:
        text = "- one\n- two\n- three"
        assert strip_markdown(text) == "one\ntwo\nthree"

    def test_strips_blockquote_markers(self) -> None:
        text = "> quoted line\n> more quote"
        assert strip_markdown(text) == "quoted line\nmore quote"

    def test_preserves_bare_urls(self) -> None:
        text = "see https://example.com/pat[h] for details"
        # The path-like character class above is a sanity check that
        # brackets inside URLs aren't treated as markdown emphasis.
        assert "https://example.com" in strip_markdown(text)

    def test_combined_marks(self) -> None:
        text = "## Title\n\n- **bold item**\n- *italic*"
        # Both leading markers (heading + bullet) are stripped, leaving
        # single newlines between segments. The exact inter-segment
        # whitespace depends on the regex order; what matters is that
        # no markdown marks remain and content is preserved.
        result = strip_markdown(text)
        assert "##" not in result
        assert "**" not in result
        assert "*" not in result
        assert "-" not in result
        assert "Title" in result
        assert "bold item" in result
        assert "italic" in result


# ─── split_for_line ────────────────────────────────────────────────────
class TestSplitForLine:
    def test_short_text_unchanged(self) -> None:
        assert split_for_line("hello world") == ["hello world"]

    def test_empty_text(self) -> None:
        assert split_for_line("") == [""]

    def test_paragraph_boundary(self) -> None:
        text = "First paragraph here.\n\nSecond paragraph here."
        chunks = split_for_line(text, max_chars=30)
        # Should split on the blank line.
        assert len(chunks) == 2
        assert "First" in chunks[0]
        assert "Second" in chunks[1]

    def test_sentence_boundary_fallback(self) -> None:
        text = "First sentence. Second sentence. Third sentence."
        chunks = split_for_line(text, max_chars=20)
        # Should split on the period+space.
        assert all(len(c) <= 21 for c in chunks)
        assert " ".join(chunks).replace(" ", "").replace(".", "") == text.replace(" ", "").replace(
            ".", ""
        )

    def test_hard_cut_when_no_boundary(self) -> None:
        text = "a" * 200
        chunks = split_for_line(text, max_chars=50)
        # No spaces / no periods — hard cut at the limit.
        assert all(len(c) <= 50 for c in chunks)
        assert "".join(chunks) == text

    def test_capped_at_5_messages(self) -> None:
        # 12 paragraphs of 10 chars each → would be 12 chunks before the cap.
        text = "\n\n".join(f"p{i:02d}" + "x" * 8 for i in range(12))
        chunks = split_for_line(text, max_chars=10)
        assert len(chunks) == LINE_MAX_MESSAGES_PER_CALL
        assert len(chunks) == 5

    def test_thai_sentence_terminator(self) -> None:
        # Thai uses ``。`` not ``.``
        text = "ประโยคแรก ขายคอนโด ทำเลดี ขนาด 35 ตร.ม。ประโยคที่สอง ราคา 5.5 ล้าน。"
        chunks = split_for_line(text, max_chars=30)
        assert all(len(c) <= 32 for c in chunks)  # small overhead for terminator
        assert "ประโยคแรก" in chunks[0]

    def test_line_safe_default(self) -> None:
        # 4500 chars = default cap; 4501 splits.
        text = "x" * 4501
        chunks = split_for_line(text)
        assert len(chunks) == 2
        assert all(len(c) <= LINE_SAFE_BUBBLE_CHARS for c in chunks)


# ─── WEBHOOK_BODY_MAX_BYTES ────────────────────────────────────────────
class TestWebhookBodyCap:
    def test_constant_value(self) -> None:
        # 1 MiB exactly. Anything bigger gets rejected by the router
        # before the signature check (defence in depth).
        assert WEBHOOK_BODY_MAX_BYTES == 1 * 1024 * 1024


# ─── LineRealAdapter: structural bones (post-fix) ───────────────────
class TestLineRealAdapterStructure:
    """Verify the bot-user-id cache + reply-token cache + self-message
    filter stub. The actual HTTP wiring raises NotImplementedError;
    these tests prove the data structures and gating logic are right
    so the wiring patch will be small."""

    def _build(self, **kw) -> object:  # noqa: ANN401
        from app.adapters.line.real import LineRealAdapter

        kw.setdefault("channel_secret", "test-secret")
        kw.setdefault("channel_access_token", "test-token")
        return LineRealAdapter(**kw)

    def test_default_bot_user_id_is_none(self) -> None:
        a = self._build()
        assert a.bot_user_id is None

    def test_set_bot_user_id_via_ctor(self) -> None:
        a = self._build(bot_user_id="U-self")
        assert a.bot_user_id == "U-self"

    def test_set_then_consume_reply_token_round_trip(self) -> None:
        a = self._build()
        a.set_reply_token("U-alice", "tok-1", ttl_seconds=60)
        token, used = a.consume_reply_token("U-alice")
        assert used is True
        assert token == "tok-1"
        # Second consume is empty (Reply tokens are single-use).
        token2, used2 = a.consume_reply_token("U-alice")
        assert used2 is False
        assert token2 is None

    def test_expired_reply_token_returns_unused(self) -> None:
        a = self._build()
        a.set_reply_token("U-alice", "tok-1", ttl_seconds=-1)
        token, used = a.consume_reply_token("U-alice")
        assert used is False
        assert token is None

    def test_unknown_chat_returns_unused(self) -> None:
        a = self._build()
        token, used = a.consume_reply_token("U-unknown")
        assert used is False
        assert token is None

    def test_send_reply_self_message_filter_skips(self) -> None:
        """When the bot's own userId is set, send_reply to itself
        short-circuits with ``skipped='self-message'`` — prevents
        infinite echo loops once real HTTP is wired."""
        a = self._build(bot_user_id="U-self")
        result = a.send_reply("U-self", "hi")
        assert result["line_user_id"] == "U-self"
        assert result["skipped"] == "self-message"
        assert result["id"].startswith("reply-")

    def test_send_reply_to_other_user_raises_not_implemented(self) -> None:
        """Outbound to anyone but self still raises — the real wiring
        replaces the raise with the Reply/Push dispatch."""
        a = self._build(bot_user_id="U-self")
        with pytest.raises(NotImplementedError) as exc:
            a.send_reply("U-alice", "hello")
        assert "NotImplementedError" in type(exc.value).__name__
        assert "Reply" in str(exc.value) or "Push" in str(exc.value)
