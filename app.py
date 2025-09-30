# app.py (request/approve gating)
import os
import time
import threading
from flask import Flask, request
from game import FishingGame, KakaoResp

app = Flask(__name__)

DB_PATH = os.environ.get("FISHING_DB", "fishing.json")
_lock = threading.Lock()

# 유저별 캐스팅 상태
# { user_id: {"casting": bool, "start_ts": int, "ends_at": int, "sec": int, "spot": "바다"/"민물"} }
user_state = {}

# 사용 허가 흐름: 요청 대기 & 허락된 사용자
# pending_request: { user_id: {"name": user_name, "ts": epoch} }
pending_request = {}
allowed_users = set()  # user_id 집합

game = FishingGame(DB_PATH)

def now() -> int:
    return int(time.time())

def load_json():
    try:
        return request.get_json(force=True, silent=False)
    except Exception:
        return {}

@app.route("/", methods=["GET"])
def health():
    return "OK", 200

def _approve_by_name(name: str):
    """이름으로 대기열에서 특정 사용자 승인 (없으면 None 반환)"""
    # 가장 최근 요청부터 검색
    if not pending_request:
        return None
    # 정렬: 최신 요청 우선
    items = sorted(pending_request.items(), key=lambda kv: kv[1]["ts"], reverse=True)
    for uid, info in items:
        if info.get("name") == name:
            allowed_users.add(uid)
            pending_request.pop(uid, None)
            return info
    return None

def _approve_any():
    """대기자 중 가장 최근 요청자 승인 (없으면 None)"""
    if not pending_request:
        return None
    uid = max(pending_request, key=lambda k: pending_request[k]["ts"])
    info = pending_request.pop(uid)
    allowed_users.add(uid)
    return info

@app.route("/skill", methods=["POST"])
def skill():
    data = load_json()
    utter = (data.get("userRequest", {}).get("utterance") or "").strip()
    user = data.get("userRequest", {}).get("user", {}) or {}
    user_id = str(user.get("id") or "unknown")
    user_name = str(user.get("nickname") or "unknown")
    msg = normalize(utter)

    try:
        # ── /입어요청: 사용 요청 등록 ─────────────────────────
        if msg == "/입어요청":
            with _lock:
                pending_request[user_id] = {"name": user_name, "ts": now()}
            return KakaoResp.text(f"✅ {user_name}님이 참여를 요청했습니다.\n"
                                  f"상대방이 '/허락' 또는 '/허락 {user_name}' 를 입력하면 사용 가능합니다.")

        # ── /허락: 특정 닉네임 또는 최근 요청자 승인 ────────────
        if msg.startswith("/허락"):
            _, arg = split_two(msg)  # arg가 있으면 닉네임
            with _lock:
                if arg:
                    info = _approve_by_name(arg)
                    if info is None:
                        return KakaoResp.text(f"대기 중인 '{arg}'의 요청을 찾지 못했습니다.\n"
                                              f"현재 대기자 수: {len(pending_request)}명")
                    return KakaoResp.text(f"✅ {info['name']}님의 요청을 허락했습니다. 이제 사용 가능합니다.")
                else:
                    info = _approve_any()
                    if info is None:
                        return KakaoResp.text("현재 대기 중인 요청이 없습니다.")
                    return KakaoResp.text(f"✅ {info['name']}님의 요청을 허락했습니다. 이제 사용 가능합니다.")

        # ── 허용되지 않은 사용자 차단 ──────────────────────────
        if user_id not in allowed_users:
            # 요청 안내 및 현재 대기자 표시
            with _lock:
                waiting_names = [info["name"] for _, info in sorted(pending_request.items(), key=lambda kv: kv[1]["ts"], reverse=True)]
            extra = f"\n(대기자: {', '.join(waiting_names)})" if waiting_names else ""
            return KakaoResp.text("⚠️ 아직 허락되지 않았습니다.\n"
                                  "먼저 '/입어요청' 을 입력하고, 상대방이 '/허락' 해주어야 사용 가능합니다." + extra)

        # ── 안내: 구 기능 제거 ─────────────────────────────────
        if msg in ("/입어가능", "/입어해제"):
            return KakaoResp.text("본 채널은 요청/허락 방식으로 운영됩니다.\n'/입어요청' → 상대방의 '/허락' 후 이용해 주세요.")

        # ── 홈/도움 ───────────────────────────────────────────
        if msg in ("/", "/help", "/도움", "/명령", "/?"):
            return KakaoResp.text(game.cmd_start(user_id))

        # ── 닉네임 설정 ───────────────────────────────────────
        if msg.startswith("/닉네임"):
            _, arg = split_two(msg)
            return KakaoResp.text(game.cmd_set_nickname(user_id, arg))

        # ── 가방 ─────────────────────────────────────────────
        if msg in ("/가방", "/inventory"):
            return KakaoResp.text(game.cmd_inventory(user_id))

        # ── 장소 설정 ─────────────────────────────────────────
        if msg.startswith("/장소"):
            _, arg = split_two(msg)
            return KakaoResp.text(game.cmd_set_spot(user_id, arg))

        # ── 상점 & 구매/판매 ──────────────────────────────────
        if msg in ("/상점", "/shop"):
            return KakaoResp.text(game.cmd_shop(user_id))

        if msg.startswith("/구매"):
            _, arg = split_two(msg)  # 예) "지렁이 10개"
            return KakaoResp.text(game.cmd_buy_by_name_qty(user_id, arg))

        if msg.startswith("/아이템판매"):
            _, arg = split_two(msg)
            return KakaoResp.text(game.cmd_sell_item_prepare(user_id, arg))

        if msg == "/판매확인":
            return KakaoResp.text(game.cmd_sell_item_confirm(user_id))
        if msg == "/판매취소":
            return KakaoResp.text(game.cmd_sell_item_cancel(user_id))

        # ── 출석/초보자찬스 ───────────────────────────────────
        if msg == "/출석":
            return KakaoResp.text(game.cmd_attendance(user_id))
        if msg == "/초보자찬스":
            if hasattr(game, "cmd_newbie_chance"):
                return KakaoResp.text(game.cmd_newbie_chance(user_id))
            else:
                return KakaoResp.text("현재 버전에서는 /초보자찬스 기능이 비활성화되어 있습니다. (게임 모듈에 구현 필요)")

        # ── 소모품 사용 ───────────────────────────────────────
        if msg in ("/집어제사용", "/집어제_사용", "/use_chum"):
            return KakaoResp.text(game.cmd_use_chum(user_id))
        if msg == "/케미라이트1등급 사용":
            return KakaoResp.text(game.cmd_use_chem_named(user_id, "케미라이트1등급"))
        if msg == "/케미라이트2등급 사용":
            return KakaoResp.text(game.cmd_use_chem_named(user_id, "케미라이트2등급"))
        if msg == "/케미라이트3등급 사용":
            return KakaoResp.text(game.cmd_use_chem_named(user_id, "케미라이트3등급"))

        # ── 낚시/릴감기 ───────────────────────────────────────
        if msg.startswith("/낚시"):
            return KakaoResp.text(handle_cast_seconds(user_id, msg))
        if msg == "/릴감기":
            return KakaoResp.text(handle_reel(user_id))

        # ── 기타 ─────────────────────────────────────────────
        return KakaoResp.text("알 수 없는 명령입니다. '/' 를 입력해 도움말을 확인하세요.")

    except Exception as e:
        return KakaoResp.text(f"에러가 발생했습니다: {e}")

def handle_cast_seconds(user_id: str, msg: str) -> str:
    # /낚시 [초]s  예) /낚시 15s
    parts = msg.split()
    if len(parts) < 2 or not parts[1].endswith("s") or not parts[1][:-1].isdigit():
        return "올바른 형식: /낚시 [시간]s   (예: /낚시 15s)"
    sec = int(parts[1][:-1])
    if sec < 1 or sec > 60:
        return "낚시는 1초 ~ 60초까지만 가능합니다."

    # 장소 확인
    spot = game.get_spot(user_id)
    if spot not in ("바다", "민물"):
        return "먼저 /장소 바다 또는 /장소 민물 로 장소를 설정해 주세요."

    # 가방 가득 차면 낚시 불가
    used, max_slot = game.count_used_slots(game.store.load_user(user_id))
    if used >= max_slot:
        bag_text = game.cmd_inventory(user_id)
        return f"⚠️ 가방이 가득 차 낚시를 진행할 수 없습니다. ({used}/{max_slot}칸)\n\n{bag_text}"

    # 캐스팅 중복 방지 + 소모품 차감
    with _lock:
        st = user_state.get(user_id, {"casting": False})
        if st.get("casting") and st.get("ends_at", 0) > now():
            remain = st["ends_at"] - now()
            return f"이미 캐스팅 중이에요! {remain}초 후에 /릴감기 를 사용해 주세요."

        ok, msg2 = game.prepare_cast(user_id, spot)
        if not ok:
            return msg2

        start = now()
        ends = start + sec
        user_state[user_id] = {"casting": True, "start_ts": start, "ends_at": ends, "sec": sec, "spot": spot}

    return (
        f"[캐스팅 시작] 장소: {spot} | 시간: {sec}초\n"
        f"끝나면 /릴감기 로 결과를 확인하세요.\n"
        f"(조기 릴 시 실패확률 +80%p 패널티, 성공률 상한 95%)"
    )

def handle_reel(user_id: str) -> str:
    with _lock:
        st = user_state.get(user_id)
        if not st or not st.get("casting"):
            return "지금 캐스팅 중이 아니에요. /낚시 [시간]s 으로 시작해 주세요."
        start_ts = st["start_ts"]
        ends_at = st["ends_at"]
        sec = st["sec"]
        spot = st["spot"]
        # 캐스팅 종료(한 번만)
        user_state[user_id] = {"casting": False, "start_ts": 0, "ends_at": 0, "sec": sec, "spot": spot}

    # 시간 계산
    now_ts = now()
    elapsed = max(0, now_ts - start_ts)
    is_early = now_ts < ends_at

    # 결과 계산
    return game.resolve_fishing(user_id, spot, chosen_sec=sec, elapsed_sec=elapsed, early_penalty=is_early)

def normalize(s: str) -> str:
    return " ".join(s.replace("  ", " ").strip().split())

def split_two(msg: str):
    parts = msg.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
