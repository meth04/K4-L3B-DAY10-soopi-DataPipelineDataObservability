"""Retrieval & evaluation tests: metric math and index document construction."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.config import load_settings
from evaluation.metrics import _token_f1
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import load_raw_records
from retrieval.index import LocalEmbeddingIndex

RUN_DATE = datetime(2026, 9, 26, tzinfo=timezone.utc)


def test_token_f1_identical_strings():
    assert _token_f1("hello world", "hello world") == 1.0


def test_token_f1_disjoint_strings():
    assert _token_f1("alpha beta", "gamma delta") == 0.0


def test_token_f1_partial_overlap():
    score = _token_f1("the quick brown fox", "the quick red fox")
    assert 0.0 < score < 1.0


def test_token_f1_empty_input():
    assert _token_f1("", "anything") == 0.0
    assert _token_f1("anything", "") == 0.0


def test_index_documents_carry_required_metadata(raw_records_path):
    df = build_clean_dataframe(load_raw_records(raw_records_path), RUN_DATE)
    documents = LocalEmbeddingIndex._build_documents(df)

    assert len(documents) == len(df)
    required = {"paper_id", "title", "published", "authors_joined", "categories_joined", "summary"}
    for document in documents:
        assert required.issubset(document["metadata"].keys())
        assert document["content"] == document["metadata"]["summary"] or document["content"]
        assert document["record_id"].startswith(document["paper_id"])


def test_collection_name_derivation_is_stable():
    settings = load_settings()
    assert (
        LocalEmbeddingIndex._derive_collection_name(settings, settings.paths.embeddings_json)
        == settings.baseline_collection_name
    )
    assert (
        LocalEmbeddingIndex._derive_collection_name(settings, settings.paths.corrupted_embeddings_json)
        == settings.corrupted_collection_name
    )
    assert (
        LocalEmbeddingIndex._derive_collection_name(settings, settings.paths.repaired_embeddings_json)
        == settings.repaired_collection_name
    )
    assert LocalEmbeddingIndex._derive_collection_name(settings, None) == settings.baseline_collection_name


def test_manifest_persist_path_is_portable_and_supports_legacy_paths():
    settings = load_settings()
    expected = settings.paths.chroma_dir.resolve()

    assert LocalEmbeddingIndex._resolve_persist_path(settings, Path("data/chroma")) == expected
    # Manifests created on another machine used an absolute path. When it is absent,
    # loading should fall back to this project's local Chroma directory.
    assert LocalEmbeddingIndex._resolve_persist_path(settings, Path("Z:/old-machine/chroma")) == expected


def test_mock_llm_supports_tool_binding():
    """The mock provider must work with langchain's tool-calling agent loop.

    Regression: the bundled fake chat models do not implement bind_tools, so
    create_agent raised NotImplementedError and the agent demo never ran.
    """
    from langchain.agents import create_agent
    from langchain.tools import tool

    from retrieval.llm import build_llm

    settings = load_settings()
    llm = build_llm(settings=settings, temperature=0.0)
    assert llm.bind_tools([]) is not None

    @tool
    def noop(query: str) -> str:
        """A no-op tool used to exercise agent construction."""
        return "ok"

    agent = create_agent(model=llm, tools=[noop], system_prompt="test", name="test_agent")
    assert agent is not None


def test_judge_falls_back_when_verdict_is_not_parsed():
    """A provider returning None must not crash evaluation with AttributeError."""
    from evaluation.metrics import JudgeVerdict, _heuristic_verdict

    verdict = _heuristic_verdict("exact answer", "exact answer")
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.score == 5
    assert verdict.correct is True
    assert _heuristic_verdict("a b c d", "unrelated text").score == 1
