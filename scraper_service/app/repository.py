import json
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.config import Settings
from app.mongodb import MongoState


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_jsonable(value: Any) -> Any:
    from bson import ObjectId

    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [as_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): as_jsonable(item) for key, item in value.items()}
    return value


def as_preview_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(as_jsonable(value), ensure_ascii=False)
    except TypeError:
        return str(value)


class ScraperRepository:
    def __init__(self, mongo: MongoState, settings: Settings):
        if mongo.db is None:
            raise RuntimeError("MongoDB is not connected")
        self.db = mongo.db
        self.settings = settings

    async def claim_event(self, event_id: str, payload: dict) -> bool:
        current_time = now_utc()
        try:
            await self.db.processed_events.insert_one({"event_id": event_id, "status": "processing", "payload": payload, "created_at": current_time, "updated_at": current_time})
            return True
        except DuplicateKeyError:
            existing = await self.db.processed_events.find_one({"event_id": event_id})
            if existing and existing.get("status") in {"completed", "processing"}:
                return False
            await self.db.processed_events.update_one(
                {"event_id": event_id},
                {"$set": {"status": "processing", "payload": payload, "updated_at": current_time}},
            )
            return True

    async def complete_event(self, event_id: str, document_id: str) -> None:
        current_time = now_utc()
        await self.db.processed_events.update_one(
            {"event_id": event_id},
            {"$set": {"status": "completed", "document_id": document_id, "completed_at": current_time, "updated_at": current_time}},
        )

    async def retry_event(self, event_id: str, reason: str, retry_count: int) -> None:
        await self.db.processed_events.update_one(
            {"event_id": event_id},
            {"$set": {"status": "retrying", "error_reason": reason, "retry_count": retry_count, "updated_at": now_utc()}},
        )

    async def fail_event(self, event_id: str, reason: str) -> None:
        current_time = now_utc()
        await self.db.processed_events.update_one(
            {"event_id": event_id},
            {"$set": {"status": "failed", "error_reason": reason, "failed_at": current_time, "updated_at": current_time}},
            upsert=True,
        )

    async def store_document(self, document: dict[str, Any]) -> str:
        result = await self.db[self.settings.mongodb_collection].insert_one(document)
        return str(result.inserted_id)

    async def get_document(self, document_id: str) -> dict | None:
        from bson import ObjectId
        doc = await self.db[self.settings.mongodb_collection].find_one({"_id": ObjectId(document_id)})
        if doc:
            doc["id"] = str(doc.pop("_id"))
            return as_jsonable(doc)
        return None

    async def delete_document(self, document_id: str, account_id: str | None = None) -> bool:
        from bson import ObjectId
        query: dict[str, Any] = {"_id": ObjectId(document_id)}
        if account_id:
            query["account_id"] = account_id
        result = await self.db[self.settings.mongodb_collection].delete_one(query)
        return result.deleted_count > 0

    async def list_documents(self, account_id: str | None = None, limit: int = 25) -> list[dict]:
        query: dict[str, Any] = {}
        if account_id:
            query["account_id"] = account_id
        cursor = self.db[self.settings.mongodb_collection].find(query).sort("created_at", -1).limit(limit)
        documents: list[dict] = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            raw = doc.get("raw") or {}
            metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            title = raw.get("title") or metadata.get("title") or doc.get("domain") or doc.get("target_url")
            summary = as_preview_text(raw.get("markdown") or raw.get("extracted_content") or raw.get("cleaned_html"))
            documents.append(
                {
                    "id": doc["id"],
                    "event_id": doc.get("event_id"),
                    "account_id": doc.get("account_id"),
                    "target_url": doc.get("target_url"),
                    "domain": doc.get("domain"),
                    "job_type": doc.get("job_type"),
                    "status": doc.get("status"),
                    "created_at": as_jsonable(doc.get("created_at")),
                    "title": as_preview_text(title)[:180],
                    "summary": summary[:320],
                }
            )
        return documents

    async def wait_for_domain_rate_limit(self, domain: str, delay_seconds: float) -> float:
        current = await self.db.domain_rate_limits.find_one({"domain": domain})
        now = now_utc()
        wait_seconds = 0.0
        if current and current.get("last_access_at"):
            elapsed = (now - current["last_access_at"].replace(tzinfo=timezone.utc)).total_seconds()
            wait_seconds = max(0.0, delay_seconds - elapsed)
        await self.db.domain_rate_limits.update_one({"domain": domain}, {"$set": {"last_access_at": now}}, upsert=True)
        return wait_seconds

    async def create_recurring(self, payload: dict) -> str:
        interval = int(payload["interval_seconds"])
        doc = {**payload, "enabled": True, "created_at": now_utc(), "next_run_at": now_utc() + timedelta(seconds=interval)}
        result = await self.db.recurring_scrapes.insert_one(doc)
        return str(result.inserted_id)

    async def due_recurring(self, limit: int = 25) -> list[dict]:
        cursor = self.db.recurring_scrapes.find({"enabled": True, "next_run_at": {"$lte": now_utc()}}).sort("next_run_at", 1).limit(limit)
        return [doc async for doc in cursor]

    async def mark_recurring_dispatched(self, recurring_id, interval_seconds: int) -> None:
        await self.db.recurring_scrapes.update_one({"_id": recurring_id}, {"$set": {"last_run_at": now_utc(), "next_run_at": now_utc() + timedelta(seconds=interval_seconds)}})

    async def create_research_job(self, payload: dict) -> str:
        cadence = str(payload.get("cadence") or "once")
        next_run_at = now_utc() if cadence == "once" else now_utc() + timedelta(seconds=cadence_to_seconds(cadence))
        doc = {**payload, "enabled": True, "created_at": now_utc(), "updated_at": now_utc(), "next_run_at": next_run_at}
        result = await self.db.research_jobs.insert_one(as_jsonable(doc))
        return str(result.inserted_id)

    async def list_research_jobs(self, account_id: str | None, limit: int = 50) -> list[dict]:
        query: dict[str, Any] = {}
        if account_id:
            query["account_id"] = account_id
        cursor = self.db.research_jobs.find(query).sort("created_at", -1).limit(limit)
        jobs: list[dict] = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            jobs.append(as_jsonable(doc))
        return jobs

    async def due_research_jobs(self, limit: int = 25) -> list[dict]:
        cursor = self.db.research_jobs.find({"enabled": True, "next_run_at": {"$lte": now_utc()}}).sort("next_run_at", 1).limit(limit)
        return [doc async for doc in cursor]

    async def mark_research_job_dispatched(self, research_job_id, cadence: str) -> None:
        if cadence == "once":
            await self.db.research_jobs.update_one(
                {"_id": research_job_id},
                {"$set": {"enabled": False, "last_run_at": now_utc(), "next_run_at": None, "updated_at": now_utc()}},
            )
            return
        interval = cadence_to_seconds(cadence)
        await self.db.research_jobs.update_one(
            {"_id": research_job_id},
            {"$set": {"last_run_at": now_utc(), "next_run_at": now_utc() + timedelta(seconds=interval), "updated_at": now_utc()}},
        )

    async def store_research_pack(self, pack: dict[str, Any]) -> str:
        result = await self.db.research_packs.insert_one(as_jsonable(pack))
        return str(result.inserted_id)

    async def get_research_pack(self, pack_id: str) -> dict | None:
        from bson import ObjectId
        doc = await self.db.research_packs.find_one({"_id": ObjectId(pack_id)})
        if not doc:
            return None
        doc["id"] = str(doc.pop("_id"))
        return as_jsonable(doc)

    async def delete_research_pack(self, pack_id: str, account_id: str | None = None) -> bool:
        from bson import ObjectId
        query: dict[str, Any] = {"_id": ObjectId(pack_id)}
        if account_id:
            query["account_id"] = account_id
        result = await self.db.research_packs.delete_one(query)
        return result.deleted_count > 0

    async def list_research_packs(self, account_id: str | None = None, limit: int = 25) -> list[dict]:
        query: dict[str, Any] = {}
        if account_id:
            query["account_id"] = account_id
        cursor = self.db.research_packs.find(query).sort("created_at", -1).limit(limit)
        packs: list[dict] = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            packs.append(as_jsonable({
                "id": doc["id"],
                "topic": doc.get("topic"),
                "job_type": doc.get("job_type"),
                "output_type": doc.get("output_type"),
                "status": doc.get("status"),
                "created_at": doc.get("created_at"),
                "source_count": len(doc.get("sources") or []),
                "successful_source_count": len([item for item in (doc.get("sources") or []) if item.get("status") == "completed"]),
                "summary": "\n".join(doc.get("key_points") or [])[:420],
                "content_draft_id": doc.get("content_draft_id"),
            }))
        return packs

    async def attach_generated_post(self, pack_id: str, post_text: str, content_draft: dict | None = None) -> None:
        from bson import ObjectId
        await self.db.research_packs.update_one(
            {"_id": ObjectId(pack_id)},
            {"$set": {"generated_post": post_text, "content_draft": content_draft, "content_draft_id": (content_draft or {}).get("id"), "updated_at": now_utc()}},
        )


def cadence_to_seconds(cadence: str) -> int:
    if cadence == "weekly":
        return 604800
    if cadence == "monthly":
        return 2592000
    return 86400
