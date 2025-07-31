from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.router import route
from app.session import new_id, clear

app = FastAPI()

@app.get("/agent")
async def handle_agent(request: Request):
    question = request.query_params.get("question", "").strip()
    session_id = request.headers.get("X-NCP-CLOVASTUDIO-REQUEST-ID")
    cid = session_id.strip() if session_id else new_id()

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(content={"answer": "API 키가 필요합니다."}, status_code=401)

    api_key = auth_header.removeprefix("Bearer ").strip()

    if not question:
        return JSONResponse(content={"answer": "질문이 비어 있습니다."}, status_code=400)

    answer = route(question, cid, api_key)

    if not (answer.startswith("종목명 인식에 실패하였습니다.") or answer.endswith("?")):
        clear(cid)

    return JSONResponse(content={"answer": answer, "session_id": cid})
