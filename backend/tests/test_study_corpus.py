import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from corpus_router import create_corpus_router
from study_corpus import (
    add_article_schema_candidate,
    add_conflict,
    add_paper_source,
    add_schema_version,
    ensure_study_corpus,
    get_study_corpus,
    record_expert_decision,
    set_consensus_schema,
    update_paper_source,
)


def test_corpus_lifecycle_and_json_serialization():
    session = {"dataset_id": "ds1"}

    paper = add_paper_source(
        session,
        source_type="doi",
        source_ref="10.1234/example",
        title="Example paper",
        status="loaded",
        metadata={"journal": "Test Journal"},
    )
    assert paper["source_type"] == "doi"
    assert paper["title"] == "Example paper"

    updated = update_paper_source(
        session,
        paper["id"],
        text="Animals were randomised before treatment.",
        status="extracted",
    )
    assert updated["status"] == "extracted"
    assert "randomised" in updated["text"]

    candidate = add_article_schema_candidate(
        session,
        paper_id=paper["id"],
        schema={
            "fields": [
                {"name": "animal_id", "semantic_type": "identifier"},
                {"name": "treatment", "semantic_type": "experimental_condition"},
            ]
        },
        evidence_spans=[
            {
                "start": 0,
                "end": 28,
                "text": "Animals were randomised",
                "field": "treatment",
            }
        ],
        source="unit-test",
        confidence=0.8,
    )
    assert candidate["paper_id"] == paper["id"]
    assert candidate["evidence_spans"][0]["paper_id"] == paper["id"]

    consensus = set_consensus_schema(
        session,
        {"fields": [{"name": "animal_id", "required": True}]},
        based_on_candidate_ids=[candidate["id"]],
    )
    conflict = add_conflict(
        session,
        field="treatment",
        candidate_ids=[candidate["id"]],
        paper_ids=[paper["id"]],
        values=["vehicle", "control"],
        description="Control group naming differs.",
    )
    decision = record_expert_decision(
        session,
        target_type="conflict",
        target_id=conflict["id"],
        decision="accepted",
        payload={"canonical_value": "control"},
    )
    version = add_schema_version(
        session,
        schema=consensus["schema"],
        reason="Initial expert-reviewed schema",
        based_on_candidate_ids=[candidate["id"]],
    )

    corpus = ensure_study_corpus(session)
    assert len(corpus["papers"]) == 1
    assert len(corpus["article_schema_candidates"]) == 1
    assert corpus["consensus_schema"]["schema"]["fields"][0]["name"] == "animal_id"
    assert corpus["conflicts"][0]["id"] == conflict["id"]
    assert corpus["expert_decisions"][0]["id"] == decision["id"]
    assert corpus["schema_versions"][0]["version"] == version["version"] == 1

    encoded = json.dumps(session)
    decoded = json.loads(encoded)
    assert decoded["study_corpus"]["papers"][0]["source_ref"] == "10.1234/example"


def test_get_study_corpus_returns_detached_snapshot():
    session = {}
    add_paper_source(session, source_type="text", source_ref="manual notes", text="abc")

    snapshot = get_study_corpus(session)
    snapshot["papers"][0]["title"] = "mutated"

    assert session["study_corpus"]["papers"][0]["title"] == "manual notes"


def test_validation_rejects_bad_inputs():
    session = {}
    with pytest.raises(ValueError):
        add_paper_source(session, source_type="url", source_ref="https://example.org")

    paper = add_paper_source(session, source_type="pdf", source_ref="paper.pdf")
    with pytest.raises(ValueError):
        add_article_schema_candidate(
            session,
            paper_id=paper["id"],
            schema={"fields": []},
            evidence_spans=[{"start": 10, "end": 1}],
        )

    with pytest.raises(KeyError):
        update_paper_source(session, "missing", status="loaded")


def test_router_factory_persists_corpus_updates():
    sessions = {"ds1": {"dataset_id": "ds1"}}
    saved = []

    app = FastAPI()
    app.include_router(create_corpus_router(sessions, save_fn=lambda did, s: saved.append((did, s))))
    client = TestClient(app)

    paper_response = client.post(
        "/api/ds1/study-corpus/papers",
        json={
            "source_type": "text",
            "source_ref": "paste-1",
            "title": "Pasted article",
            "text": "A short article body.",
            "status": "loaded",
        },
    )
    assert paper_response.status_code == 200
    paper = paper_response.json()

    candidate_response = client.post(
        "/api/ds1/study-corpus/schema-candidates",
        json={
            "paper_id": paper["id"],
            "schema": {"fields": [{"name": "dose"}]},
            "evidence_spans": [{"start": 2, "end": 7, "text": "short"}],
            "confidence": 0.7,
        },
    )
    assert candidate_response.status_code == 200

    corpus_response = client.get("/api/ds1/study-corpus")
    assert corpus_response.status_code == 200
    corpus = corpus_response.json()
    assert corpus["papers"][0]["id"] == paper["id"]
    assert corpus["article_schema_candidates"][0]["paper_id"] == paper["id"]
    assert saved[-1][0] == "ds1"


def test_router_factory_can_load_missing_session():
    sessions = {}
    loaded = {"ds2": {"dataset_id": "ds2"}}

    app = FastAPI()
    app.include_router(create_corpus_router(sessions, load_fn=lambda did: loaded.get(did)))
    client = TestClient(app)

    response = client.get("/api/ds2/study-corpus")

    assert response.status_code == 200
    assert response.json()["papers"] == []
    assert "ds2" in sessions


def test_schema_review_route_queues_vcg_questions():
    sessions = {"ds1": {"dataset_id": "ds1", "columns": [{"name": "group"}]}}

    app = FastAPI()
    app.include_router(create_corpus_router(sessions))
    client = TestClient(app)

    response = client.post("/api/ds1/study-corpus/schema-review")

    assert response.status_code == 200
    body = response.json()
    assert body["created"]
    categories = {item["category"] for item in body["created"]}
    assert "vcg_assumption" in categories
    assert body["loop_state"]["reason"] in {"needs_questions", "iteration_cap"}
