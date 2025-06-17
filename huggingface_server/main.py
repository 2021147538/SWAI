import os, json, logging, urllib.parse, requests, re
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from openai import OpenAI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다!")
client = OpenAI(api_key=api_key)

# ───────────────────────── JSON 보정 유틸─────────────────────────
OBJ_GLUE  = re.compile(r'}\s*{')           # `}{`
ARR_TAIL  = re.compile(r',\s*]')           # `,]`
JSON_RE   = re.compile(r'\{[\s\S]*\}')     # 가장 큰 JSON 블록

# 느슨한 캡처: {... "title":"X", ... "author":"Y", ... "reason":"Z" ...}
LOOSE_RE  = re.compile(
    r'\{[^{}]*?"title"\s*:\s*"([^"]+)"[^{}]*?'
    r'"author"\s*:\s*"([^"]+)"[^{}]*?'
    r'"reason"\s*:\s*"([^"]+)"[^{}]*?\}',
    re.S | re.I
)

def fix_missing_commas(txt: str) -> str:
    txt = OBJ_GLUE.sub('},{', txt)
    txt = ARR_TAIL.sub(']', txt)
    return txt

def parse_loose_books(txt: str) -> List[Dict[str, str]]:
    return [{"title": t, "author": a, "reason": r}
            for t, a, r in LOOSE_RE.findall(txt)]

def safe_parse(content: str) -> List[Dict[str, str]]:
    """
    ① 바로 json.loads → ② 쉼표 보정 후 json.loads
    ③ 가장 큰 JSON 블록 뽑아 보정 후 json.loads
    ④ 마지막으로 정규식으로 title/author/reason 뽑기
    """
    for step in (
        lambda x: json.loads(x),
        lambda x: json.loads(fix_missing_commas(x)),
        lambda x: json.loads(fix_missing_commas(JSON_RE.search(x).group(0)))
        if JSON_RE.search(x) else (_ for _ in ()).throw(
            ValueError("JSON 블록 없음")),
    ):
        try:
            raw = step(content)
            if isinstance(raw, dict) and isinstance(raw.get("books"), list):
                return raw["books"]
        except Exception:
            pass

    # ④ loose regex
    loose = parse_loose_books(content)
    if loose:
        return loose
    raise ValueError("유효한 책 정보를 추출하지 못함")

# ───────────────────── FastAPI & 엔드포인트 ─────────────────────
class Prompt(BaseModel):
    prompt: str
    count:  int = 9

limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])
app = FastAPI(title="ReadingTree-GPT")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

@app.post("/recommend")
@limiter.limit("10/minute")
def recommend(request: Request, p: Prompt) -> Dict[str, List[Dict[str, str]]]:
    user_q = p.prompt.strip()
    if not user_q:
        raise HTTPException(status_code=400, detail="빈 프롬프트입니다.")
    desired, request_n = max(1, min(p.count, 12)), p.count + 4

    sys_prompt = (
        f"너는 서평가다. 최대 {request_n}권까지 책을 추천한다.\n"
        "순수 JSON만 출력, 부족하면 있는 만큼 넣어라.\n"
        "예시: {\"books\":[{\"title\":\"…\",\"author\":\"…\",\"reason\":\"…\"}]}"
    )

    try:
        books: List[Dict[str, str]] = []
        for attempt in range(3):
            rsp = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.3,
                response_format={"type":"json_object"},
                messages=[
                    {"role":"system","content":sys_prompt},
                    {"role":"user",  "content":user_q}
                ],
                max_tokens=600,
            )
            content = rsp.choices[0].message.content
            try:
                books = safe_parse(content)
            except Exception as err:
                logging.warning("파싱 실패 %s회차: %s", attempt+1, err)
                continue
            if books:
                break

        if not books:
            raise ValueError("책을 한 권도 추출하지 못했습니다")

        # 중복 제거 + desired 개수로 제한
        uniq, seen = [], set()
        for b in books:
            key = f"{b.get('title')}|{b.get('author')}"
            if key not in seen:
                seen.add(key)
                uniq.append(b)
            if len(uniq) >= desired:
                break

        return {"books": uniq}

    except Exception as e:
        logging.exception("OpenAI API 오류")
        raise HTTPException(status_code=500, detail=f"OpenAI API 호출 실패: {e}")

@app.get("/healthz")
@limiter.exempt
def health() -> Dict[str, str]:
    return {"status":"ok"}
