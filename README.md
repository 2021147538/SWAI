Reading Tree - GPT 기반 도서 추천 웹 애플리케이션

본 프로젝트의 주요 기능은 사용자의 프롬프트 입력을 바탕으로 OpenAI GPT 모델을 활용하여 도서를 추천하는 웹 애플리케이션이다.  
프론트엔드와 백엔드는 `public/`, `huggingface_server/` 두 개의 디렉토리로 분리되어 구성된다.

시스템 구성 요약
- 프론트엔드: HTML + JavaScript (jQuery, Bootstrap 기반)
- 백엔드: FastAPI + OpenAI GPT API
- 모델 사용: `gpt-4o-mini` (OpenAI API)
- 책 정보 연동: 알라딘 Open API (`TTB_KEY`)  #현재 사용하지 않음(큰 기능을 하지 않는데 속도가 느려지기 때문)
- 실행 환경: 로컬 실행 또는 Docker

 프롬프트 처리 구조
사용자가 웹에서 입력한 프롬프트가 AI 추천으로 이어지는 전체 흐름은 다음과 같다.

 1. 프론트엔드 입력 및 API 호출
사용자는 `index.html` 내 검색창에서 추천 문장을 입력하고 버튼을 누른다.
fetch(API, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ prompt, count: 9 }),
});

prompt: 사용자가 입력한 문장

count: 추천받을 책의 수 (최대 12)

요청은 /recommend API로 전달된다.

2. 백엔드 처리 흐름 (main.py)
POST /recommend 라우트는 다음 순서로 작동한다:
(1) 시스템 프롬프트 생성
너는 전문 서평가다. 사용자 요청에 맞춰 정확히 N권의 책을 추천한다.
반드시 JSON만 출력해야 하며, 부가 설명은 절대 포함하지 않는다.
{"books":[{"title":"…","author":"…","reason":"…"},…]} 형태여야 한다.
이 프롬프트는 모델이 일관된 JSON을 반환하도록 강제한다.

(2) GPT 응답 요청
rsp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": q}
    ],
    max_tokens=600
)
응답은 문자열 형태의 JSON 텍스트이다.
때로는 포맷 오류가 발생하므로 정규식으로 JSON 블록만 추출하여 파싱을 시도한다.

(3) JSON 파싱 및 유효성 검증
safe_json_parse() 함수에서 중괄호 블록을 찾아 JSON으로 파싱
books 리스트가 없거나 부족하면 재시도
title-author 조합이 중복되지 않도록 필터링

(4) 결과 반환
{
  "books": [
    {
      "title": "과학의 품격",
      "author": "강양구",
      "reason": "과학 지식을 교양 수준으로 풀어낸 현대 교양서입니다."
    },
    ...
  ]
}

3. 프론트엔드 출력
응답을 받은 후 다음과 같이 카드 형태로 추천 도서를 렌더링한다

<div class="card">
  <h5>도서명</h5>
  <h6>저자</h6>
  <p>추천 이유</p>
</div>
로딩 상태 표시
추천 요청 중 spinner를 보여주고 버튼을 비활성화

응답 완료 시 다시 원상복구, 오류 발생 시 alert 메시지로 출력


프로젝트 구조

ReadingTree/
├── public/                  # index.html, style.css, JS 등 프론트 리소스
├── huggingface_server/      # FastAPI 서버, OpenAI 연동 코드
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
└── README.md

*중요!!
현재 github 코드에서는 openai api key가 없기 때문에 로컬에서 백엔드를 구동할 수 없다. main.py 에서 openai api key를 설정하거나
https://readingtree.netlify.app/
에서 실행해 볼 수 있다. 백엔드는 huggingface에 구동되고 있어 기능이 구현되어 있다.
