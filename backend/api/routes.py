from fastapi import APIRouter, HTTPException
from backend.core.schemas import SolveRequest, FinalResponse
from backend.core.coordinator import Coordinator

router = APIRouter()
coordinator = Coordinator()

@router.post("/solve", response_model=FinalResponse)
async def solve_problem(request: SolveRequest):
    try:
        response = await coordinator.process_request(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

