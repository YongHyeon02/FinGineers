from __future__ import annotations

import json, re, functools
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, NamedTuple
import numpy as np
import yfinance as yf

from app.universe import KOSPI_MAP, KOSDAQ_MAP, _load_alias_csv, NAME_BY_TICKER
from app.llm_bridge import disambiguate_ticker_hcx
from config import TOP_K_FUZZY, TOP_K_EMBED, HCX_CONF_THRESHOLD, AmbiguousTickerError

from rapidfuzz import process, fuzz             # 나중에 아래 try 코드로 변경해야 함.
# try:
#     from rapidfuzz import process, fuzz        # fuzzy 매칭용
# except ImportError:
#     process = fuzz = None

from sentence_transformers import SentenceTransformer # 나중에 아래 try 코드로 변경해야 함.
import faiss
# try:
#     from sentence_transformers import SentenceTransformer
#     import faiss
# except ImportError:
#     SentenceTransformer = None         # graceful-degrade

class TickerInfo(NamedTuple):
    ticker: str        # ‘005930.KS’
    name:   str        # ‘삼성전자’


# 1️⃣ 메모리 사전 (CSV + 수동 보강)
_STATIC_MAP: Dict[str, str] = {}
_STATIC_MAP.update(KOSPI_MAP)
_STATIC_MAP.update(KOSDAQ_MAP)
_STATIC_MAP.update(_load_alias_csv())
# _STATIC_MAP.update({           # 필요 시 수동 보강
#     "마이크로소프트": "MSFT",
#     "애플": "AAPL",
# })

# --------------- 2) 헬퍼 ---------------
@lru_cache(maxsize=512)
def _fallback_lookup(name: str) -> Optional[str]:
    """yfinance.Lookup / Search 로 티커 추정 (주식만 반환)"""
    try:
        res = yf.Lookup(name)
        for item in res.stock:  # type: ignore[attr-defined]
            return item.symbol
    except Exception:
        pass

    try:
        res = yf.Search(name, max_results=5)
        for q in res.quotes:
            if q.quoteType == "EQUITY":
                return q.symbol
    except Exception:
        pass
    return None

_PARTICLE_REGEX = re.compile(r"[의은는이가를]\s*$")

def _strip_particle(text: str) -> str:
    """문자열 끝의 조사 하나만 제거 (없으면 원본 그대로 반환)"""
    return _PARTICLE_REGEX.sub("", text)


def _lookup_korean(name: str) -> Optional[str]:
    """KOSPI/KOSDAQ 사전 + yfinance Lookup 검색"""
    return (
        KOSPI_MAP.get(name)
        or KOSDAQ_MAP.get(name)
        or _fallback_lookup(name)
    )

 # ───────────────────────────────────────────────────────────────────────
 # ③ Sentence-BERT 임베딩 Fallback
 # -----------------------------------------------------------------------
 # ─────────────────────────── Sentence-BERT 모델 ───────────────────────────
@lru_cache(maxsize=1)
def _get_model():
    """Sentence-BERT 모델 1회 로드 (없으면 None)"""
    if SentenceTransformer is None:
        return None
    return SentenceTransformer("jhgan/ko-sbert-sts")

_EMBED_DIM = 768

@lru_cache(maxsize=1)
def _init_embed_index():
    """한 번만 호출: 이름들 → 임베딩 → Faiss 인덱스 구성"""
    if SentenceTransformer is None or faiss is None:
        return None, None

    names = list(_STATIC_MAP.keys())
    model = _get_model()
    vecs = model.encode(names, normalize_embeddings=True, batch_size=128)

    index = faiss.IndexFlatIP(_EMBED_DIM)      # cosine sim == dot prod (L2-norm=1)
    index.add(np.asarray(vecs, dtype="float32"))
    return (index, names)

# class LowConfidenceTickerError(Exception):
#     """confidence 가 기준치보다 낮을 때 발생"""
#     def __init__(self, identifier: str, best: str, confidence: float):
#         self.identifier = identifier
#         self.best = best
#         self.confidence = confidence
#         super().__init__(identifier, best, confidence)


def to_ticker(identifier: str, *, with_name: bool = False) -> str | TickerInfo:
    """
    1) _STATIC_MAP에서 먼저 찾기
    2) 없으면 yfinance Lookup/Search
    3) 그래도 없으면 identifier를 대문자로 반환

    with_name=True → TickerInfo(ticker, 공식종목명) 반환
    """
    identifier = identifier.strip()

    # ---------- ① 정적/alias 매핑 ----------
    for name_try in (identifier, _strip_particle(identifier)):
        if (ticker := _STATIC_MAP.get(name_try)):
            official = name_try
            return (
                TickerInfo(ticker, official) if with_name else ticker
            )

    # # ---------- ② fuzzy 후보 N 개 ----------
    fuzzy_cands: list[tuple[str, float]] = []
    if process:
        raw_fuzzy = process.extract(
            identifier,
            _STATIC_MAP.keys(),
            scorer=fuzz.QRatio,
            limit=TOP_K_FUZZY,
        )
        # rapidfuzz는 (choice, score, idx)를 반환하므로 앞 두 개만 사용
        fuzzy_cands = [(choice, float(score)) for choice, score, *_ in raw_fuzzy]

    # ---------- ③ 임베딩 fallback (Sentence-BERT) ----------
    embed_cands: list[tuple[str, float]] = []
    idx, names = _init_embed_index()
    model = _get_model()
    if idx is not None and model is not None:
        q_vec = model.encode([identifier], normalize_embeddings=True)
        D, I = idx.search(np.asarray(q_vec, dtype="float32"), TOP_K_EMBED)
        for sim, ix in zip(D[0], I[0]):
            embed_cands.append((names[ix], float(sim)))
    # if (_sem := _semantic_fallback(identifier)):
    #     return _sem
    # ----- ④ 후보 합치기 (중복 제거·유사도 기준 정렬) -----
    cand_all: dict[str, float] = {}
    for item in fuzzy_cands + embed_cands:
        name, score = item[:2]          # 앞 두 값만 사용
        cand_all[name] = max(cand_all.get(name, 0), score)
    candidates = sorted(cand_all.items(), key=lambda x: -x[1])[:TOP_K_FUZZY+TOP_K_EMBED]
    official_names = [n for n, _ in candidates]

    # ----- ⑤ hcx에게 어떤 후보가 alias와 가장 유사한지 판단시키기 -----
    best, conf = disambiguate_ticker_hcx(alias=identifier, candidates=official_names)
    
    if conf >= HCX_CONF_THRESHOLD:
        ticker = _STATIC_MAP[best]
        official = best
        return TickerInfo(ticker, official) if with_name else ticker

    # ----- ⑥ 자신 없으면 사용자 재질문을 위해 예외 발생 -----
    raise AmbiguousTickerError(identifier, official_names)
