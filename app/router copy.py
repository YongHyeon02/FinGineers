# app/router.py
from __future__ import annotations
import logging
import datetime as dt
from typing import Callable, Optional, Dict, Any
from app import session                  # ↩︎ 간단한 in-mem 세션 캐시 (앞서 제안)
from app.utils import _holiday_msg, _prev_bday
from app.llm_bridge import extract_params, fill_missing, fill_missing_multi
from app.task_handlers import (
    task_search,
    task1_simple,
)
from config import AmbiguousTickerError

logger = logging.getLogger(__name__)
_FAIL = "질문을 이해하지 못했습니다."

# ─────────────────────────────────────────────────────
# 0. 보조 유틸  ← ★ 새로 추가
# ─────────────────────────────────────────────────────
def _most_recent_bday() -> str:
    """
    오늘이 영업일이면 오늘(YYYY-MM-DD),
    아니면 직전 영업일을 반환
    """
    today = dt.date.today().isoformat()
    return today if _holiday_msg(today) is None else _prev_bday(today)

_recent_kw = ("최근", "요즘", "근래", "요새", "이즈음")
_today_kw  = ("오늘", "금일", "당일", "오늘자")

def _auto_fill_relative_dates(question: str, params: dict) -> None:
    """
    • date 와 date_to 가 모두 None 인 상태에서
      - “최근*”류 키워드 → date = 최근 영업일
      - “오늘*”류 키워드 → date = 최근 영업일
    • date_from 값이 이미 있으면 date_to 에도 최근 영업일 세팅
    """
    if params.get("date") or params.get("date_to"):
        return  # 이미 값이 있으면 건너뜀

    q = question
    if any(k in q for k in _recent_kw + _today_kw):
        recent = _most_recent_bday()
        params["date"] = recent
        if params.get("date_from"):
            params["date_to"] = recent

def _walk_set(d: dict, path: list[str], value):
    """d['a']['b']['c'] … 경로에 value 저장"""
    for k in path[:-1]:
        d = d.setdefault(k, {})
    d[path[-1]] = value

def _walk_get(d: dict, path: list[str]):
    """경로 값 조회(없으면 None)"""
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d

def _has_value(p: dict, dotted: str) -> bool:
    """pending 안에 dotted path 값이 채워져 있는지"""
    if "." not in dotted:
        return p.get(dotted) not in (None, [], "", {})
    head, *rest = dotted.split(".")
    root = p.get("conditions", {})
    return _walk_get(root, [head] + rest) not in (None, [], "", {})

def _collect_missing_cond(cond: dict) -> list[str]:
    """
    conditions 트리에서 비어 있는 leaf (slots) 경로를 모두 반환
    예: ["volume_spike.window", "volume_spike.volume_ratio.min", "volume_pct.min"]
    """
    slots: list[str] = []

    # ① 거래량 급증
    if (vs := cond.get("volume_spike")) is not None:
        if vs.get("window") is None:
            slots.append("volume_spike.window")
        if (vs.get("volume_ratio") or {}).get("min") is None:
            slots.append("volume_spike.volume_ratio.min")

    # ② 거래량·가격·등락률·갭 %
    simple = {
        "volume"      : ("min",),
        "price_close" : ("min", "max"),
        "pct_change"  : ("min", "max"),
        "gap_pct"     : ("min", "max"),
        "volume_pct"  : ("min",),
        "RSI"         : ("min", "max"),
    }
    for k, leaves in simple.items():
        if k not in cond:
            continue
        if not isinstance(cond[k], dict):
            slots.append(f"{k}.{leaves[0]}")
            continue
        for leaf in leaves:
            if cond[k].get(leaf) is None:
                slots.append(f"{k}.{leaf}")

    # ③ 이동평균 돌파
    if (ma := cond.get("moving_avg")) is not None:
        if ma.get("window") is None:
            slots.append("moving_avg.window")
        diff = ma.get("diff_pct", {})
        if (diff.get("min") is None) and (diff.get("max") is None):
            slots.append("moving_avg.diff_pct.min")   # 한 가지만 물어봄

    # ④ 볼린저 터치
    if (bt := cond.get("bollinger_touch")) not in {"upper", "lower"}:
        if "bollinger_touch" in cond:
            slots.append("bollinger_touch")          # upper/lower 자체를 값으로 받음

    # ⑤ 신고가/신저가/낙폭
    if (pb := cond.get("peak_break")) and pb.get("period_days") is None:
        slots.append("peak_break.period_days")
    if (pl := cond.get("peak_low")) and pl.get("period_days") is None:
        slots.append("peak_low.period_days")
    if (op := cond.get("off_peak")):
        if op.get("period_days") is None:
            slots.append("off_peak.period_days")
        if op.get("min") is None:
            slots.append("off_peak.min")

    return slots
# ─────────────────────────────────────────────────────

# ──────────────────────────────────────────────
# 1.  task 메타 정의  (추가 시 여기만 수정)
# ──────────────────────────────────────────────
HandlerFn = Callable[[str, dict], str]      # (question, params) -> answer

TASK_REGISTRY: Dict[str, Dict[str, HandlerFn]] = {
    "단순조회":   {"fn": task1_simple.handle},
    "상승종목수": {"fn": task1_simple.handle},
    "하락종목수": {"fn": task1_simple.handle},
    "거래종목수": {"fn": task1_simple.handle},
    "시장순위":   {"fn": task1_simple.handle},
    "종목검색":   {"fn": task_search.handle},
    "횟수검색":   {"fn": task_search.handle},
    "날짜검색":   {"fn": task_search.handle},
}

# ──────────────────────────────────────────────
def _safe_handle(fn: HandlerFn, question: str, params: dict, api_key: str) -> Optional[str]:
    try:
        out = fn(question, params, api_key)
        # print(out)
        return out if out else None
    except AmbiguousTickerError:
        raise
    except Exception as e:
        logger.exception("%s 실행 오류: %s", fn.__name__, e)
        return None

def _join(xs, last="·"):
    _METRIC_KO = {"pct_change": "등락률"}
    xs2 = [_METRIC_KO.get(x, x) for x in xs]
    return f" {last} ".join(xs2) if xs2 else ""



def _fmt_min_max(label: str, val: dict) -> str:
    lo = val.get("min")
    hi = val.get("max")
    if lo is not None and hi is not None:
        return f"{label}이 {lo} 이상 {hi} 이하인"
    if lo is not None:
        return f"{label}이 {lo} 이상인"
    return f"{label}이 {hi} 이하인"

def _check_and_prompt(task: str, p: dict) -> tuple[bool, str | None, list[str]]:

    """
    • 모든 task별 슬롯검사 & 재질문을 하나의 if-문 체계로 수행
    • 반환값: (ready, prompt)
        ready  : 모든 필드가 채워졌으면 True
        prompt : 누락 시 사용자에게 보낼 재질문(없으면 None)
    """
    # ────────────────────────────────────── 단순조회
    if task == "단순조회":
        date    = p.get("date")
        tickers = p.get("tickers", [])
        metrics = p.get("metrics", [])
        market  = p.get("market")

        only_index_metrics = metrics and set(metrics).issubset({"지수", "거래대금"})
        ticker_needed      = not only_index_metrics

        missing: set[str] = set()
        if not date: 
            missing.add("date")
        if not metrics: 
            missing.add("metrics")
        if ticker_needed and not tickers:
            missing.add("tickers")
        if ("지수" in metrics) and not market:
            missing.add("market")
        
        if not missing:
            return True, None, []
        
        if missing == {"date"}:
            return False, f"어떤 날짜의 {_join(tickers)} {_join(metrics)}를 알려 드릴까요?", list(missing)
        if missing == {"tickers"}:
            return False, f"{date or '해당 날짜'}에 어떤 종목의 {_join(metrics)}를 알려 드릴까요?", list(missing)
        if missing == {"metrics"}:
            return False, f"{date or '해당 날짜'}에 {_join(tickers)}의 어떤 지표(예: 종가·시가·거래량)를 원하시나요?", list(missing)
        if missing == {"market"}:
            return False, f"{date or '해당 날짜'}에 어느 시장(KOSPI·KOSDAQ)의 지수를 알려 드릴까요?", list(missing)
        
        if missing == {"date", "tickers"}:
            return False, f"어떤 날짜에 어떤 종목의 {_join(metrics)}를 알려 드릴까요?", list(missing)
        if missing == {"date", "metrics"}:
            return False, f"어떤 날짜에 {_join(tickers)}의 어떤 지표(예: 종가·시가·거래량)를 알려 드릴까요?", list(missing)
        if missing == {"tickers", "metrics"}:
            return False, f"{date or '해당 날짜'}의 어떤 종목의 어떤 지표(예: 종가·시가·거래량)를 알려 드릴까요?", list(missing)
        if missing == {"date", "market"}:
            return False, "어떤 날짜에 어떤 시장(KOSPI·KOSDAQ)의 지수를 알려 드릴까요?", list(missing)
        
        return False, f"어떤 날짜에 어떤 종목의 어떤 지표를 알려 드릴까요?", list(missing)
    # ────────────────────────────────────── 시장순위
    if task == "시장순위":
        missing = {k for k in ("date", "metrics") if not p.get(k)}
        if not missing:
            return True, None, []
        date   = p.get("date")
        metric = (p.get("metrics") or [None])[0]
        conds   = p.get("conditions") or {}
        order   = conds.get("order")
        order_txt = "높은" if order == "high" else "낮은"
        n = p.get("rank_n") or 1

        if n == 1:
            if metric in ("거래량", "상승률", "하락률", "가격"):
                if missing == {"date"}:
                    return False, f"어떤 날짜 기준으로 {metric}이 가장 높은 종목을 알려 드릴까요?", list(missing)
            if metric in ("변동성", "베타"):
                if missing == {"date"}:
                    return False, f"어떤 날짜 기준으로 {metric}이 가장 {order_txt} 종목을 알려 드릴까요?", list(missing)
            if missing == {"metrics"}:
                if order == None:
                    return False, f"{date}에 어떤 지표가 가장 높은 종목을 알려 드릴까요?", list(missing)
                else:
                    return False, f"{date}에 어떤 지표가 가장 {order_txt} 종목을 알려 드릴까요?", list(missing)

                
        else:
            if metric in ("거래량", "상승률", "하락률", "가격"):
                if missing == {"date"}:
                    return False, f"어떤 날짜 기준으로 {metric}이 높은 {n}개의 종목을 알려 드릴까요?", list(missing)
            if metric in ("변동성", "베타"):
                if missing == {"date"}:
                    return False, f"어떤 날짜 기준으로 {metric}이 {order_txt} {n}개의 종목을 알려 드릴까요?", list(missing)
            if missing == {"metrics"}:
                if order == None:
                    return False, f"{date or '해당 날짜'}에 어떤 지표가 높은 {n}개의 종목을 알려 드릴까요?", list(missing)
                else:
                    return False, f"{date or '해당 날짜'}에 어떤 지표가 {order_txt} {n}개의 종목을 알려 드릴까요?", list(missing)

        return True, None, []
    # ────────────────────────────────────── 상승·하락·거래 종목 수
    if task in ("상승종목수", "하락종목수", "거래종목수"):
        if p.get("date"):
            return True, None, []
        task_txt = (
            "상승한 종목 수" if task == "상승종목수"
            else "하락한 종목 수" if task == "하락종목수"
            else "거래된 종목 수"
        )        
        return False, f"어느 날짜 기준으로 {task_txt}를 알려 드릴까요?", ["date"]
    # ────────────────────────────────────── 종목검색 / 기간검색 / 횟수검색
    
    if task == "종목검색":
        miss: set[str]     = set()
        not_miss: set[str] = set()
        date   = p.get("date")
        date_from = p.get("date_from")
        date_to = p.get("date_to")
        cond = p.get("conditions") or {}

        for key, val in cond.items():
            if key in {"volume", "price_close", "pct_change", "volume_pct", "RSI", "volume_spike", "moving_avg", "bollinger_touch", "peak_break", "peak_low", "off_peak", "gap_pct"}:
                # ── 1. 거래량·가격·등락률·갭 % ─────────────────────
                if key in {"volume_pct", "volume", "price_close", "pct_change", "gap_pct"}:
                    _KOR_NAME = {
                        "volume"      : "거래량",
                        "price_close" : "종가",
                        "pct_change"  : "등락률",
                        "gap_pct"     : "갭",
                    }
                    if not isinstance(val, dict):
                        miss.add(_KOR_NAME[key] + "이 몇 이상/이하인")
                        continue
                    if key == "volume_pct": # (1) 거래량 %, 반드시 min
                        if "min" in val:
                            not_miss.add(f"거래량이 {val['min']}% 이상 증가한")
                        else:
                            miss.add("거래량이 몇 % 이상 증가한")
                        continue
                    if not (("min" in val) or ("max" in val)): # (2) 나머지: min·max 중 하나 필수
                        miss.add(_KOR_NAME[key] + "이 몇 이상/이하인")
                        continue
                    not_miss.add(_fmt_min_max(_KOR_NAME[key], val))
                # ── 2. 거래량 급증 (volume_spike) ─────────────────
                if key == "volume_spike": 
                    if not isinstance(val, dict):
                        miss.add("거래량이 며칠 평균 대비 몇 % 이상 급증한")
                        continue
                    win  = val.get("window")
                    vrat = (val.get("volume_ratio") or {}).get("min")
                    if win is not None and vrat is not None:
                        not_miss.add(f"거래량이 {win}일 평균 대비 {vrat}% 이상 급증한")
                    else:
                        miss.add(
                            f"거래량이 {str(win) + '일' if win is not None else '며칠'} 평균 대비 "
                            f"{vrat if vrat is not None else '몇 '}% 이상 급증한"
                        )
                # ── 3. RSI -----------------------------------------------------------------
                if key == "RSI":
                    if not isinstance(val, dict) or not ("min" in val or "max" in val):
                        miss.add("RSI가 몇 이상/이하인")
                    else:
                        if "min" in val:
                            not_miss.add(f"RSI가 {val['min']} 이상인")
                        if "max" in val:
                            not_miss.add(f"RSI가 {val['max']} 이하인")
                # ── 4. 이동평균 돌파 (moving_avg) -------------------------------------------
                if key == "moving_avg":
                    if not isinstance(val, dict):
                        miss.add("종가가 며칠 이동평균보다 몇 % 이상/이하 높은·낮은")
                        continue
                    win   = val.get("window")
                    diff  = val.get("diff_pct", {})
                    have_win  = win is not None
                    have_diff = isinstance(diff, dict) and ("min" in diff or "max" in diff)

                    if have_win and have_diff:
                        if "min" in diff:
                            updn = "높은" if diff["min"] >= 0 else "낮은"
                            not_miss.add(f"종가가 {win}일 이동평균보다 {abs(diff['min'])}% 이상 {updn}")
                        elif "max" in diff:
                            updn = "높은" if diff["max"] >= 0 else "낮은"
                            not_miss.add(f"종가가 {win}일 이동평균보다 {abs(diff['max'])}% 이하 {updn}")
                    else:
                        if have_win and not have_diff:
                            miss.add(f"종가가 {win}일 이동평균보다 몇 % 이상/이하 높은·낮은")
                        elif not have_win and have_diff:
                            if "min" in diff:
                                v   = diff["min"]
                                updn = "높은" if v >= 0 else "낮은"
                                miss.add(f"종가가 며칠 이동평균보다 {abs(v)}% 이상 {updn}")
                            elif "max" in diff:
                                v   = diff["max"]
                                updn = "높은" if v >= 0 else "낮은"
                                miss.add(f"종가가 며칠 이동평균보다 {abs(v)}% 이하 {updn}")
                            else:
                                miss.add("종가가 며칠 이동평균보다 몇 % 이상/이하 높은·낮은")
                # ── 5. 볼린저 터치 ----------------------------------------------------------
                if key == "bollinger_touch":
                    if val in {"upper", "lower"}:
                        not_miss.add(f"볼린저 밴드 {'상단' if val=='upper' else '하단'}에 터치한")
                    else:
                        miss.add("볼린저 밴드 상단·하단 중 어디에 터치한")
                # ── 6. 신고가 돌파 (peak_break) --------------------------------------------
                if key == "peak_break":
                    if isinstance(val, dict) and "period_days" in val:
                        not_miss.add(f"{val['period_days']}일 신고가를 돌파한")
                    else:
                        miss.add("며칠 신고가를 돌파한")
                # ── 7. 신저가 갱신 (peak_low) ----------------------------------------------
                if key == "peak_low":
                    if isinstance(val, dict) and "period_days" in val:
                        not_miss.add(f"{val['period_days']}일 신저가를 갱신한")
                    else:
                        miss.add("며칠 신저가를 갱신한")
                # ── 8. 고점 대비 낙폭 (off_peak) -------------------------------------------
                if key == "off_peak":
                    if isinstance(val, dict) and "period_days" in val and "min" in val:
                        not_miss.add(f"{val['period_days']}일 대비 {val['min']}% 이상 하락한")
                    else:
                        pdays = (val or {}).get("period_days")
                        mval  = (val or {}).get("min")
                        miss.add(f"{pdays if pdays else '며칠'} 대비 {mval if mval else '몇'}% 이상 하락한")
  
                merged_text = " · ".join(sorted(not_miss | miss))
                if not date and miss:
                    return False, f"어떤 날짜에 {merged_text} 종목을 알려 드릴까요?", ["date", "condition"]
                if not date and not miss:
                    return False, f"어떤 날짜에 {merged_text} 종목을 알려 드릴까요?", ["date"]
                if miss:
                    return False, f"{date}에 {merged_text} 종목을 알려 드릴까요?", ["condition"]
                return True, None, []
            
            if key in {"pct_change_range", "consecutive_change", "cross", "three_pattern"}:
                # ── 1. 기간 등락률 (pct_change_range) -------------------------------------------
                if key == "pct_change_range":
                    if not isinstance(val, dict) or not ("min" in val or "max" in val):
                        miss.add("기간 등락률이 몇 % 이상/이하인")
                    else:
                        not_miss.add(_fmt_min_max("기간 등락률", val))
                # ── 2. 연속 상승, 하락 (consecutive_change) -------------------------------------------
                if key == "consecutive_change":
                    if val == "up":
                        not_miss.add("연속 상승한")
                    elif val == "down":
                        not_miss.add("연속 하락한")
                    else:
                        miss.add("연속 상승·하락 중 어떤")
                # ── 3. 골든크로스, 데드크로스 (cross) -------------------------------------------
                if key == "cross":
                    cross_map = {
                        "both"  : "골든크로스 또는 데드크로스가 발생한",
                        "golden": "골든크로스가 발생한",
                        "dead"  : "데드크로스가 발생한",
                    }
                    if val in cross_map:
                        not_miss.add(cross_map[val])
                    else:
                        miss.add("골든/데드/양쪽 중 어떤 크로스가 발생한")
                # ── 4. 적삼병, 흑삼병 (three_pattern) -------------------------------------------
                if key == "three_pattern":                    
                    if val in {"적삼병", "흑삼병"}:
                        not_miss.add(f"{val}이 발생한")
                    else:
                        miss.add("적삼병·흑삼병 중 어떤 패턴이 발생한")

                merged_text = " · ".join(sorted(not_miss | miss))
                if not date_from and not date_to:
                    if miss:
                        return False, f"언제부터 언제까지의 {merged_text} 종목을 알려 드릴까요?", ["date_from", "date_to", "condition"]
                    else:
                        return False, f"언제부터 언제까지의 {merged_text} 종목을 알려 드릴까요?", ["date_from", "date_to"]
                if not date_from:
                    if miss:
                        return False, f"언제부터 {date_to}까지의 {merged_text} 종목을 알려 드릴까요?", ["date_from", "condition"]
                    else:
                        return False, f"언제부터 {date_to}까지의 {merged_text} 종목을 알려 드릴까요?", ["date_from"]
                if not date_to:
                    if miss:
                        return False, f"{date_from}부터 언제까지의 {merged_text} 종목을 알려 드릴까요?", ["date_to", "condition"]
                    else:
                        return False, f"{date_from}부터 언제까지의 {merged_text} 종목을 알려 드릴까요?", ["date_to"]
                if miss:
                    return False, f"{date_from}~{date_to} 기간에 {merged_text} 종목을 알려 드릴까요?", ["condition"]
                return True, None, []

    if task == "횟수검색":
        tickers   = p.get("tickers", [])
        date_from = p.get("date_from")
        date_to   = p.get("date_to")
        cross     = (p.get("conditions") or {}).get("cross")
        cross_map = {
            "both":   "골든크로스 또는 데드크로스가 발생한",
            "golden": "골든크로스가 발생한",
            "dead":   "데드크로스가 발생한",
        }

        if not date_from and not date_to:
            if tickers:
                return False, f"언제부터 언제까지의 {_join(tickers) or '어떤 종목의'} {cross_map[cross]} 횟수를 알려 드릴까요?", ["date_from", "date_to", "tickers"]
            else:
                return False, f"언제부터 언제까지의 {_join(tickers) or '어떤 종목의'} {cross_map[cross]} 횟수를 알려 드릴까요?", ["date_from", "date_to"]
        if not date_from:
            if tickers:
                return False, f"언제부터 {date_to}까지의 {_join(tickers) or '어떤 종목의'} {cross_map[cross]} 횟수를 알려 드릴까요?", ["date_from", "tickers"]
            else:
                return False, f"언제부터 {date_to}까지의 {_join(tickers) or '어떤 종목의'} {cross_map[cross]} 횟수를 알려 드릴까요?", ["date_from"]
        if not date_to:
            if tickers:
                return False, f"{date_from}부터 언제까지의 {_join(tickers) or '어떤 종목의'} {cross_map[cross]} 횟수를 알려 드릴까요?", ["date_to", "tickers"]
            else:
                return False, f"{date_from}부터 언제까지의 {_join(tickers) or '어떤 종목의'} {cross_map[cross]} 횟수를 알려 드릴까요?", ["date_to"]
        if not tickers:
            return False, f"{date_from}~{date_to} 기간에 어떤 종목의 {cross_map[cross]} 횟수를 알려 드릴까요?", ["tickers"]
        return True, None, []
    
    if task == "날짜검색":
        cond_set = set()
        tickers   = p.get("tickers", [])
        date_from = p.get("date_from")
        date_to   = p.get("date_to")
        cross     = (p.get("conditions") or {}).get("cross")
        cross_map = {
            "both":   "골든크로스 또는 데드크로스가 발생한",
            "golden": "골든크로스가 발생한",
            "dead":   "데드크로스가 발생한",
        }
        pattern   = (p.get("conditions") or {}).get("three_pattern")
        pattern_map = {
            "적삼병": "적삼병이 발생한",
            "흑삼병": "흑삼병이 발생한",
        }
        if cross:
            cond_set.add(cross_map[cross])
        if pattern:
            cond_set.add(pattern_map[pattern])
        merged_text = " · ".join(sorted(cond_set))
        
        if not date_from and not date_to:
            if tickers:
                return False, f"언제부터 언제까지의 {_join(tickers) or '어떤 종목의'} {merged_text} 날짜를 알려 드릴까요?", ["date_from", "date_to", "tickers"]
            else:
                return False, f"언제부터 언제까지의 {_join(tickers) or '어떤 종목의'} {merged_text} 날짜를 알려 드릴까요?", ["date_from", "date_to"]
        if not date_from:
            if tickers:
                return False, f"언제부터 {date_to}까지의 {_join(tickers) or '어떤 종목의'} {merged_text} 날짜를 알려 드릴까요?", ["date_from", "tickers"]
            else:
                return False, f"언제부터 {date_to}까지의 {_join(tickers) or '어떤 종목의'} {merged_text} 날짜를 알려 드릴까요?", ["date_from"]
        if not date_to:
            if tickers:
                return False, f"{date_from}부터 언제까지의 {_join(tickers) or '어떤 종목의'} {merged_text} 날짜를 알려 드릴까요?", ["date_to", "tickers"]
            else:
                return False, f"{date_from}부터 언제까지의 {_join(tickers) or '어떤 종목의'} {merged_text} 날짜를 알려 드릴까요?", ["date_to"]
        if not tickers:
            return False, f"{date_from}~{date_to} 기간에 어떤 종목의 {merged_text} 날짜를 알려 드릴까요?", ["tickers"]
        return True, None, []


# ────────────────────────────── 메인 ──────────────────────────────
def route(question: str, conv_id: str, api_key: str) -> str:
    """
    conv_id : 세션 ID (웹소켓 UUID, 슬랙 thread_ts 등)
    """
    try:
        question = question.strip()
        if not question:
            return _FAIL

        # ── 1) 이전 세션 이어받기 ──────────────────────
        pending = session.get(conv_id)
        if pending:
            filled = None
            if pending.get("_missing"):
                filled = fill_missing_multi(question, pending["_missing"], api_key)
            if filled:
                pending.update(filled)
                pending["_missing"] = [s for s in pending["_missing"] if pending.get(s) in (None, [], "", {})]
            
            # ── 1-b. 새로 추가로 들어온 정보는 기존 파서로 병합
            follow = extract_params(question, api_key)

            # ── 1-a. 새 파싱 결과로 슬롯 병합 ──────────
            for k, v in follow.items():
                if not v:
                    continue
                if k == "task":
                    continue
                if k == "tickers":
                    orig = pending.get("tickers", [])
                    pending["tickers"] = list(dict.fromkeys(orig + v))
                else:
                    if pending.get(k) in (None, [], "", {}):
                        pending[k] = v

            _auto_fill_relative_dates(question, pending)
            ready, follow_up, miss = _check_and_prompt(pending["task"], pending)
            if not ready:
                pending["_missing"] = miss
                session.set(conv_id, pending)
                return follow_up
            
            # ── 1-b. 실행 가능 → 핸들러 호출 ───────────
            hinfo = TASK_REGISTRY[pending["task"]]
            ans = _safe_handle(hinfo["fn"], question, pending, api_key) or _FAIL
            session.clear(conv_id)
            return ans
        
        # ── 2) 첫 질문 파싱 ────────────────────────────
        params = extract_params(question, api_key)
        _auto_fill_relative_dates(question, params)
        print(params)
        ready, follow_up, miss = _check_and_prompt(params["task"], params)

        if not ready:
            params["_missing"] = miss
            session.set(conv_id, params)
            return follow_up
        
        hinfo = TASK_REGISTRY[params["task"]]
        return _safe_handle(hinfo["fn"], question, params, api_key) or _FAIL
    
    except AmbiguousTickerError as e:
        cur = session.get(conv_id)
        if cur:
            cur["tickers"] = [t for t in cur.get("tickers", []) if t != e.alias]
            session.set(conv_id, cur)
        elif 'params' in locals() and params:           # 첫 질문의 params
            pending = params.copy()
            keep = [t for t in pending.get("tickers", []) if t != e.alias]
            pending['tickers'] = keep                  # ← 후속 답변 채울 자리
            session.set(conv_id, pending)

        sugg = " · ".join(e.candidates)
        return f"종목명 인식에 실패하였습니다. 조회할 종목명을 정확하게 입력해 주세요 (제안: {sugg})"

    except Exception as ex:
        logger.exception("route() 처리 중 예외 발생: %s", ex)
        return _FAIL

