# app.py
import os
import json
import threading
from datetime import datetime, date
from flask import Flask, request, jsonify

###############################################################################
# 기본 설정
###############################################################################
app = Flask(__name__)
DATA_PATH = os.environ.get("DATA_PATH", "data.json")
LOCK = threading.Lock()

# 상점 아이템 정의
#   - restricted_allowed: 출석/초보자찬스 골드(제한 골드)로 구매 가능한지 여부
SHOP_ITEMS = {
    1: {"name": "지렁이", "price": 100, "restricted_allowed": True},
    2: {"name": "떡밥", "price": 200, "restricted_allowed": True},
    3: {"name": "집어제", "price": 800, "restricted_allowed": False},
    4: {"name": "케미라이트", "price": 300, "restricted_allowed": False},
}

QUICK = [
    {"action": "message", "label": "도움말", "messageText": "/도움말"},
    {"action": "message", "label": "가방", "messageText": "/가방"},
    {"action": "message", "label": "상점", "messageText": "/상점"},
]

###############################################################################
# 저장/로드 (간단 파일 저장; Render에서는 일시적 저장소)
###############################################################################
def _now_datestr() -> str:
    return date.today().isoformat()

def load_store():
    if not os.path.exists(DATA_PATH):
        return {"users": {}}
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}}

def save_store(store):
    tmp = DATA_PATH + ".tmp"
    with LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_PATH)

###############################################################################
# 유저 상태
###############################################################################
def get_user(store, user_id: str):
    u = store["users"].get(user_id)
    if u is None:
        u = {
            "nickname": None,
            "nickname_locked": False,  # True면 더 이상 변경 불가
            "gold": 0,                 # 일반 골드
            "restricted_gold": 0,      # 제한 골드(출석/초보자찬스) - 지렁이/떡밥만 구매 가능
            "inventory": {},           # {"지렁이": 10, ...}
            "is_beginner": True,       # 낚린이(초보) 여부
            "attendance_last": None,   # 마지막 출석 날짜(YYYY-MM-DD)
            "newbie_bonus": {          # 초보자찬스 사용 기록
                "date": None,
                "count": 0             # 하루 최대 3회
            },
            "stats": {
                "level": 1,
                "played_days": 0
            }
        }
        store["users"][user_id] = u
    return u

###############################################################################
# 공통: 카카오 응답
###############################################################################
def kakao_text(text: str, quick=None):
    payload = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}],
        },
    }
    if quick:
        payload["template"]["quickReplies"] = quick
    return jsonify(payload)

###############################################################################
# 유틸
###############################################################################
def inv_add(user, item_name: str, cnt: int):
    inv = user["inventory"]
    inv[item_name] = inv.get(item_name, 0) + cnt
    if inv[item_name] <= 0:
        del inv[item_name]

def find_item_by_no_or_name(token: str):
    # 번호가 들어오면 번호 우선
    if token.isdigit():
        no = int(token)
        if no in SHOP_ITEMS:
            return SHOP_ITEMS[no]
        return None
    # 이름으로 검색(정확히 일치 우선, 없으면 부분일치)
    for no, it in SHOP_ITEMS.items():
        if it["name"] == token:
            return it
    for no, it in SHOP_ITEMS.items():
        if token in it["name"]:
            return it
    return None

def can_buy_with_restricted(item) -> bool:
    return bool(item.get("restricted_allowed"))

###############################################################################
# 명령어 처리
###############################################################################
HELP_TEXT = (
    "[명령어 안내]\n"
    "1줄: /상태, /가방\n"
    "2줄: /상점, 구매 [번호], 판매 [번호], 전부판매\n"
    "3줄: /출석\n"
    "초보 전용: /초보자찬스 (하루 3회, 1000골드) — 지급 골드는 지렁이/떡밥만 구매 가능\n"
    "닉네임: /닉네임 설정 [원하는닉네임] (1회만 가능)\n"
    "소비: /케미라이트 사용, /집어제 사용"
)

def fmt_money(user):
    return f"일반골드: {user['gold']:,} / 제한골드: {user['restricted_gold']:,}"

def cmd_help():
    return HELP_TEXT

def cmd_status(user):
    lv = user["stats"]["level"]
    nick = user["nickname"] or "(미설정)"
    beginner = "예" if user["is_beginner"] else "아니오"
    return (
        f"[상태]\n닉네임: {nick}\n레벨: {lv}\n낚린이: {beginner}\n"
        f"{fmt_money(user)}"
    )

def cmd_bag(user):
    if not user["inventory"]:
        return "[가방]\n비어 있습니다."
    lines = ["[가방]"]
    for name, cnt in sorted(user["inventory"].items()):
        # 소비아이템 안내 추가
        extra = ""
        if name == "케미라이트":
            extra = " (사용: /케미라이트 사용)"
        if name == "집어제":
            extra = " (사용: /집어제 사용)"
        lines.append(f"- {name} x{cnt}{extra}")
    return "\n".join(lines)

def cmd_shop():
    lines = ["[상점] (번호 / 이름 / 가격)"]
    for no in sorted(SHOP_ITEMS.keys()):
        it = SHOP_ITEMS[no]
        tag = "제한골드 가능" if it["restricted_allowed"] else "일반골드만"
        lines.append(f"{no}) {it['name']} / {it['price']}G / {tag}")
    lines.append("구매 예시: '구매 1' 또는 '구매 지렁이 3'")
    return "\n".join(lines)

def cmd_buy(user, tokens):
    # 형식: 구매 [번호] (개수1)  또는  구매 [이름] [개수]
    if len(tokens) == 2:
        target = find_item_by_no_or_name(tokens[1])
        qty = 1
    elif len(tokens) == 3:
        target = find_item_by_no_or_name(tokens[1])
        if tokens[2].isdigit():
            qty = int(tokens[2])
        else:
            return "구매 형식: '구매 [번호]' 또는 '구매 [아이템이름] [개수]'"
    else:
        return "구매 형식: '구매 [번호]' 또는 '구매 [아이템이름] [개수]'"

    if not target:
        return "해당 아이템을 찾을 수 없습니다."

    price = target["price"] * qty
    # 우선 제한골드로 결제 가능하면 제한골드부터 사용
    used_restricted = 0
    used_normal = 0
    if can_buy_with_restricted(target):
        use = min(user["restricted_gold"], price)
        used_restricted = use
        price -= use
    # 남는 금액은 일반골드로
    if price > 0:
        if user["gold"] < price:
            return (
                "골드가 부족합니다.\n"
                f"필요: {target['price'] * qty:,}G / {fmt_money(user)}"
            )
        used_normal = price

    # 차감 및 지급
    user["restricted_gold"] -= used_restricted
    user["gold"] -= used_normal
    inv_add(user, target["name"], qty)

    paid = []
    if used_restricted:
        paid.append(f"제한골드 {used_restricted:,}G")
    if used_normal:
        paid.append(f"일반골드 {used_normal:,}G")
    paid_str = " + ".join(paid) if paid else "0G"

    return (
        f"구매 완료: {target['name']} x{qty}\n"
        f"결제: {paid_str}\n{fmt_money(user)}"
    )

def cmd_sell(user, tokens):
    # 형식: 판매 [번호]
    if len(tokens) != 2 or not tokens[1].isdigit():
        return "판매 형식: '판매 [번호]' (상점 번호 기준)"
    no = int(tokens[1])
    it = SHOP_ITEMS.get(no)
    if not it:
        return "해당 번호의 아이템이 없습니다."
    name = it["name"]
    if user["inventory"].get(name, 0) <= 0:
        return f"가방에 {name}이(가) 없습니다."

    # 단순 환불가: 구매가의 50%
    user["inventory"][name] -= 1
    if user["inventory"][name] <= 0:
        del user["inventory"][name]
    refund = it["price"] // 2
    user["gold"] += refund
    return f"판매 완료: {name} x1 → {refund}G 획득\n{fmt_money(user)}"

def cmd_sell_all(user):
    if not user["inventory"]:
        return "판매할 아이템이 없습니다."
    gained = 0
    # 상점에 있는 아이템만 판매 대상으로 가정
    sellables = {it["name"]: it for it in SHOP_ITEMS.values()}
    to_del = []
    for name, cnt in user["inventory"].items():
        if name in sellables and cnt > 0:
            refund = (sellables[name]["price"] // 2) * cnt
            gained += refund
            to_del.append(name)
    for name in to_del:
        del user["inventory"][name]
    user["gold"] += gained
    return f"전부판매 완료: {gained}G 획득\n{fmt_money(user)}"

def cmd_attendance(user):
    today = _now_datestr()
    if user["attendance_last"] == today:
        return "오늘은 이미 출석 체크를 하였습니다."
    user["attendance_last"] = today
    user["restricted_gold"] += 1000
    return (
        "출석 체크 완료: 제한골드 1,000G 지급\n"
        "지급된 제한골드는 지렁이/떡밥 구매에만 사용할 수 있습니다.\n"
        f"{fmt_money(user)}"
    )

def cmd_newbie_bonus(user):
    if not user["is_beginner"]:
        return "초보자 전용 보상은 더 이상 받을 수 없습니다."
    today = _now_datestr()
    nb = user["newbie_bonus"]
    if nb["date"] != today:
        nb["date"] = today
        nb["count"] = 0
    if nb["count"] >= 3:
        return "오늘은 이미 3회 모두 사용했습니다."

    nb["count"] += 1
    user["restricted_gold"] += 1000
    return (
        f"초보자찬스 사용 {nb['count']}/3회: 제한골드 1,000G 지급\n"
        "지급된 제한골드는 지렁이/떡밥 구매에만 사용할 수 있습니다.\n"
        f"{fmt_money(user)}"
    )

def cmd_nickname(user, tokens):
    # /닉네임 설정 [닉네임]
    if user["nickname_locked"]:
        return "닉네임은 한 번만 설정할 수 있습니다."
    if len(tokens) < 3 or tokens[1] != "설정":
        return "닉네임 설정 형식: '/닉네임 설정 원하는닉네임'"
    nickname = " ".join(tokens[2:]).strip()
    if not nickname:
        return "닉네임을 입력해 주세요."
    user["nickname"] = nickname
    user["nickname_locked"] = True
    return f"닉네임이 '{nickname}'(으)로 설정되었습니다. 이후 변경은 불가합니다."

def cmd_use_item(user, item_name: str):
    if user["inventory"].get(item_name, 0) <= 0:
        return f"가방에 {item_name}이(가) 없습니다."
    inv_add(user, item_name, -1)
    return f"{item_name} 1개 사용 완료."

###############################################################################
# 메인 핸들러
###############################################################################
def handle_command(utterance: str, user_id: str) -> str:
    store = load_store()
    user = get_user(store, user_id)
    tokens = utterance.strip().split()

    if not tokens:
        return "등록된 명령어만 사용할 수 있습니다. '/도움말'을 입력해 주세요."

    head = tokens[0]

    # 표준 명령어
    if head in ("/도움말", "도움말"):
        return cmd_help()
    if head in ("/상태", "상태"):
        return cmd_status(user)
    if head in ("/가방", "가방"):
        return cmd_bag(user)
    if head in ("/상점", "상점"):
        return cmd_shop()

    # 거래
    if head == "구매":
        msg = cmd_buy(user, tokens)
        save_store(store)
        return msg
    if head == "판매":
        msg = cmd_sell(user, tokens)
        save_store(store)
        return msg
    if head in ("전부판매", "/전부판매"):
        msg = cmd_sell_all(user)
        save_store(store)
        return msg

    # 보상/출석
    if head in ("/출석", "출석"):
        msg = cmd_attendance(user)
        save_store(store)
        return msg
    if head in ("/초보자찬스", "초보자찬스"):
        msg = cmd_newbie_bonus(user)
        save_store(store)
        return msg

    # 닉네임
    if head in ("/닉네임", "닉네임"):
        msg = cmd_nickname(user, tokens)
        save_store(store)
        return msg

    # 소비 아이템 사용
    if utterance.strip() in ("/케미라이트 사용", "케미라이트 사용"):
        msg = cmd_use_item(user, "케미라이트")
        save_store(store)
        return msg
    if utterance.strip() in ("/집어제 사용", "집어제 사용"):
        msg = cmd_use_item(user, "집어제")
        save_store(store)
        return msg

    # 기타 → 안내
    return "등록된 명령어만 사용할 수 있습니다. '/도움말'을 입력해 주세요."

###############################################################################
# 라우팅
###############################################################################
@app.get("/")
def health():
    return "OK", 200

# /skill, /skill/ 모두 허용. GET(핑)도 200으로 응답.
@app.route("/skill", methods=["GET", "POST"], strict_slashes=False)
@app.route("/skill/", methods=["GET", "POST"], strict_slashes=False)
def skill():
    if request.method == "GET":
        return kakao_text("PING OK"), 200

    body = request.get_json(silent=True) or {}
    user_req = body.get("userRequest", {})
    utterance = (user_req.get("utterance") or "").strip()
    user_id = user_req.get("user", {}).get("id") or "anonymous"

    text = handle_command(utterance, user_id)
    return kakao_text(text, quick=QUICK), 200

# 혹시 /skill1로 호출 중이면 임시로 매핑
@app.route("/skill1", methods=["GET", "POST"], strict_slashes=False)
def skill1_alias():
    if request.method == "GET":
        return kakao_text("PING OK (/skill1)"), 200
    return skill()

###############################################################################
# 로컬 실행
###############################################################################
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
