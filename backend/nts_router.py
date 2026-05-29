import asyncio
import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from nts_analyzer import analyze_nts, _NTS_FIELD_REGISTRY

logger = logging.getLogger(__name__)

_nts_batches: Dict[str, Dict[str, Any]] = {}
# Key: batch_id (UUID str), Value: {"created_at": iso_str, "results": List[Dict]}

nts_router = APIRouter(prefix="/api/nts", tags=["nts"])


@nts_router.post("/analyze")
async def analyze_single(file: UploadFile = File(...)):
    """Analyze a single NTS PDF file."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF (.pdf extension required).")

    content = await file.read()

    result = await asyncio.to_thread(analyze_nts, content, file.filename)

    batch_id = str(uuid.uuid4())
    _nts_batches[batch_id] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results": [result],
    }

    return {"batch_id": batch_id, "results": [result]}


@nts_router.post("/analyze-batch")
async def analyze_batch(files: List[UploadFile] = File(...)):
    """Analyze multiple NTS PDF files (1–50)."""
    if not files or len(files) < 1:
        raise HTTPException(status_code=400, detail="At least one file is required.")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="A maximum of 50 files can be processed per batch.")

    results: List[Dict[str, Any]] = []

    for upload in files:
        filename = upload.filename or "unknown.pdf"

        if not filename.lower().endswith(".pdf"):
            results.append(
                {
                    "filename": filename,
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    "error": "File is not a PDF (.pdf extension required).",
                    "classification": "ERROR",
                    "layer1": None,
                    "layer2": None,
                    "layer2_available": False,
                }
            )
            continue

        try:
            content = await upload.read()
            result = await asyncio.to_thread(analyze_nts, content, filename)
            results.append(result)
        except Exception as exc:
            logger.exception("Failed to analyze file %s", filename)
            results.append(
                {
                    "filename": filename,
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                    "classification": "ERROR",
                    "layer1": None,
                    "layer2": None,
                    "layer2_available": False,
                }
            )

    batch_id = str(uuid.uuid4())
    _nts_batches[batch_id] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }

    return {"batch_id": batch_id, "count": len(results), "results": results}


@nts_router.get("/export/{batch_id}/csv")
async def export_csv(batch_id: str):
    """Export batch results as a flat CSV file."""
    batch = _nts_batches.get(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")

    fixed_columns = [
        "filename",
        "analyzed_at",
        "classification",
        "arrive_cited",
        "prepare_cited",
        "arrive_evidence_count",
        "prepare_evidence_count",
        "arrive_first_match",
        "prepare_first_match",
        "layer1_error",
        "layer2_available",
    ]

    dynamic_columns: List[str] = []
    for field_id in _NTS_FIELD_REGISTRY:
        dynamic_columns.append(field_id)
        dynamic_columns.append(f"{field_id}_status")

    all_columns = fixed_columns + dynamic_columns

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=all_columns, extrasaction="ignore")
    writer.writeheader()

    for result in batch["results"]:
        layer1 = result.get("layer1")
        layer2 = result.get("layer2")

        arrive_cited = ""
        arrive_evidence_count = 0
        arrive_first_match = ""
        prepare_cited = ""
        prepare_evidence_count = 0
        prepare_first_match = ""
        layer1_error = ""

        if layer1 is not None:
            arrive_block = layer1.get("arrive", {})
            arrive_cited = arrive_block.get("cited", "")
            arrive_evidence = arrive_block.get("evidence", [])
            arrive_evidence_count = len(arrive_evidence)
            if arrive_evidence:
                context = arrive_evidence[0].get("context", "")
                arrive_first_match = context[:100]

            prepare_block = layer1.get("prepare", {})
            prepare_cited = prepare_block.get("cited", "")
            prepare_evidence = prepare_block.get("evidence", [])
            prepare_evidence_count = len(prepare_evidence)
            if prepare_evidence:
                context = prepare_evidence[0].get("context", "")
                prepare_first_match = context[:100]

            layer1_error = layer1.get("error", "")

        row: Dict[str, Any] = {
            "filename": result.get("filename", ""),
            "analyzed_at": result.get("analyzed_at", ""),
            "classification": result.get("classification", ""),
            "arrive_cited": arrive_cited,
            "prepare_cited": prepare_cited,
            "arrive_evidence_count": arrive_evidence_count,
            "prepare_evidence_count": prepare_evidence_count,
            "arrive_first_match": arrive_first_match,
            "prepare_first_match": prepare_first_match,
            "layer1_error": layer1_error,
            "layer2_available": result.get("layer2_available", False),
        }

        for field_id in _NTS_FIELD_REGISTRY:
            if layer2 is not None and field_id in layer2:
                row[field_id] = layer2[field_id].get("value", "")
                row[f"{field_id}_status"] = layer2[field_id].get("status", "")
            else:
                row[field_id] = ""
                row[f"{field_id}_status"] = ""

        writer.writerow(row)

    csv_bytes = output.getvalue().encode("utf-8")

    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="nts_analysis_{batch_id[:8]}.csv"'
        },
    )


@nts_router.get("/export/{batch_id}/json")
async def export_json(batch_id: str):
    """Export full batch results as a JSON file."""
    batch = _nts_batches.get(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")

    payload = json.dumps(batch, indent=2, ensure_ascii=False)

    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="nts_analysis_{batch_id[:8]}.json"'
        },
    )


@nts_router.get("/batches")
async def list_batches():
    """List all stored batches, sorted by creation time descending."""
    summary = [
        {
            "batch_id": batch_id,
            "created_at": data["created_at"],
            "count": len(data["results"]),
        }
        for batch_id, data in _nts_batches.items()
    ]
    summary.sort(key=lambda x: x["created_at"], reverse=True)
    return {"batches": summary}
