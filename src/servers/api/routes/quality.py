# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Response Quality Evaluation Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Response quality evaluation endpoints

Related Requirements: FR1.30, UC1.28
Related Tasks: T117
Related Architecture: MO1.4
Related Tests: AT1.27

Recent Changes:
- Initial implementation
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel

from src.database.connection import get_db
from src.core.quality.evaluator import QualityEvaluator
from src.core.job.manager import JobManager
from src.servers.api.auth import require_permission, verify_api_key

router = APIRouter(prefix="/quality", tags=["quality"], dependencies=[Depends(require_permission("expert:execute"))])


class EvaluateResponseRequest(BaseModel):
    job_id: int
    prompt: Optional[str] = None
    response: Optional[str] = None


class UserFeedbackRequest(BaseModel):
    job_id: int
    rating: int  # 1-5
    feedback_text: Optional[str] = None


@router.post("/evaluate")
async def evaluate_response(
    request: EvaluateResponseRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Evaluate response quality for a job."""
    job_manager = JobManager(db)
    job = job_manager.get_job(request.job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    prompt = request.prompt or job.prompt_sent
    response = request.response or job.response_received

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    if not response:
        # Some async/error paths may not persist response_received.
        # Use job context so quality endpoints stay contract-compatible.
        import json

        metadata = json.loads(job.metadata_json) if job.metadata_json else {}
        error_info = json.loads(job.error_info_json) if job.error_info_json else {}
        fallback_detail = error_info.get("error") or metadata.get("error") or "No response captured"
        response = f"[{job.status}] {fallback_detail}"

    evaluator = QualityEvaluator()
    metrics = evaluator.evaluate_response(
        prompt=prompt, response=response, context={"job_id": request.job_id}
    )

    # Store quality metrics in job metadata
    import json

    metadata = json.loads(job.metadata_json) if job.metadata_json else {}
    metadata["quality_metrics"] = metrics

    job_manager.update_job(request.job_id, metadata=metadata)

    return {"success": True, "job_id": request.job_id, "metrics": metrics}


@router.post("/feedback")
async def submit_feedback(
    request: UserFeedbackRequest,
    db: Session = Depends(get_db),
    user=Depends(verify_api_key),
) -> Dict[str, Any]:
    """Submit user feedback on response quality.

    # req: FR-023  (FR-1.30 Response Quality Evaluation — authenticated user feedback)

    Feedback is attributed to the authenticated caller resolved from the API key /
    JWT. Unauthenticated requests are rejected by ``verify_api_key`` (401) before
    any feedback row is written, so feedback is never attributed to a default user.
    """
    user_id = user.id

    if request.rating < 1 or request.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    job_manager = JobManager(db)
    job = job_manager.get_job(request.job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    evaluator = QualityEvaluator()
    feedback = evaluator.collect_user_feedback(
        job_id=request.job_id,
        user_id=user_id,
        rating=request.rating,
        feedback_text=request.feedback_text,
    )

    # Store feedback in job metadata
    import json

    metadata = json.loads(job.metadata_json) if job.metadata_json else {}
    if "user_feedback" not in metadata:
        metadata["user_feedback"] = []
    metadata["user_feedback"].append(feedback)

    job_manager.update_job(request.job_id, metadata=metadata)

    return {"success": True, "job_id": request.job_id, "feedback": feedback}


@router.get("/job/{job_id}")
async def get_quality_metrics(
    job_id: int, db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """Get quality metrics for a job."""
    job_manager = JobManager(db)
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    import json

    metadata = json.loads(job.metadata_json) if job.metadata_json else {}

    return {
        "job_id": job_id,
        "quality_metrics": metadata.get("quality_metrics"),
        "user_feedback": metadata.get("user_feedback", []),
    }
