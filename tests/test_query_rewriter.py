"""Tests for QueryRewriter -- all LLM calls are mocked."""

import json
from unittest.mock import MagicMock, patch

import pytest

from codelibrarian.models import RewrittenQuery
from codelibrarian.query_rewriter import QueryRewriter


@pytest.fixture
def rewriter():
    return QueryRewriter(
        api_url="http://localhost:11434/v1/chat/completions",
        model="qwen2.5:3b",
        timeout=5.0,
    )


class TestRewrite:
    def test_parses_valid_json_response(self, rewriter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "terms": ["insert_call", "INSERT INTO", "store_parse_result"],
                                "focus": "implementation",
                            }
                        )
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(rewriter._client, "post", return_value=mock_response):
            result = rewriter.rewrite("how are edges inserted into the graph?")

        assert result is not None
        assert result.terms == ["insert_call", "INSERT INTO", "store_parse_result"]
        assert result.focus == "implementation"

    def test_returns_none_on_timeout(self, rewriter):
        import httpx

        with patch.object(
            rewriter._client, "post", side_effect=httpx.TimeoutException("timeout")
        ):
            result = rewriter.rewrite("some query")

        assert result is None

    def test_returns_none_on_connection_error(self, rewriter):
        import httpx

        with patch.object(
            rewriter._client, "post", side_effect=httpx.ConnectError("refused")
        ):
            result = rewriter.rewrite("some query")

        assert result is None

    def test_returns_none_on_invalid_json(self, rewriter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not json at all"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(rewriter._client, "post", return_value=mock_response):
            result = rewriter.rewrite("some query")

        assert result is None

    def test_returns_none_on_missing_terms(self, rewriter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": json.dumps({"focus": "implementation"})}}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(rewriter._client, "post", return_value=mock_response):
            result = rewriter.rewrite("some query")

        assert result is None

    def test_defaults_focus_to_all(self, rewriter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"terms": ["find_oldest", "animal"]}
                        )
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(rewriter._client, "post", return_value=mock_response):
            result = rewriter.rewrite("find oldest animal")

        assert result is not None
        assert result.focus == "all"

    def test_strips_markdown_fences_from_response(self, rewriter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{"terms": ["foo", "bar"], "focus": "all"}\n```'
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(rewriter._client, "post", return_value=mock_response):
            result = rewriter.rewrite("some query")

        assert result is not None
        assert result.terms == ["foo", "bar"]


class TestContextManager:
    def test_enters_and_exits(self):
        rw = QueryRewriter(
            api_url="http://localhost:11434/v1/chat/completions",
            model="qwen2.5:3b",
        )
        with rw as r:
            assert r is rw
