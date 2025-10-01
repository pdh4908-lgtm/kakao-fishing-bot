# ===== MERGED APP FILE (app.py + app_final.py) =====

# ===== Original app.py =====

# app.py
import os
import json
import random
from datetime import datetime, time, date
from flask import Flask, request, jsonify

app = Flask(__name__)
DATA_PATH = os.environ.get("DATA_PATH", "data.json")

# -----------------------------
# 상수/정책
# -----------------------------
RESTRICTED_CAP = 1000  # 제한골드 최대 보유치(일반 규칙)
BAG_CAP = 5            # 가방 칸 수 
# -----------------------------
# 상점/아이템 정의
# -----------------------------
PRICES = {
    "지렁이": 10,                  # 제한골드 사용 가능
    "떡밥": 10,                    # 제한골드 사용 가능
    "집어제": 500,                 # 3회 지속
    "케미라이트1등급": 600,        # 1회성(20:00~05:00)
    "케미라이트2등급": 350,        # 1회성(20:00~05:00)
    "케미라이트3등급": 200,        # 1회성(20:00~05:00)
    # 장비(예시)
    "철제 낚싯대": 1000,
    "강화 낚싯대": 5000,
    "프로 낚싯대": 20000,
    "레전드 낚싯대": 100000,
}
CONSUMABLES = {"지렁이", "떡밥", "집어제", "케미라이트1등급", "케미라이트2등급", "케미라이트3등급"}
RESTRICTED_ALLOWED = {"지렁이", "떡밥"}

# 허용 명령(이외엔 무응답)
STRICT_CMDS = {
    "/", "/상점", "/전부판매", "/출석", "/초보자찬스",
    "/릴감기", "/판매확인", "/판매취소", "/기록"
}
PREFIX_CMDS = {
    "/닉네임 ", "/구매 ", "/아이템판매 ", "/낚시 ", "/장소 ",
    "/케미라이트1등급 사용", "/케미라이트2등급 사용", "/케미라이트3등급 사용",
    "/집어제사용",
}

def is_allowed_command(text: str) -> bool:
    if not text or not text.startswith("/"):
        return False
    if text in STRICT_CMDS:
        return True
    for p in PREFIX_CMDS:
        if text == p or text.startswith(p):
            return True
    return False

# -----------------------------
# 물고기 데이터
# -----------------------------
FISH_POOL = {
    "민물": {
        "소형":[("붕어",1,40),("피라미",5,35),("미꾸라지",3,20),("몰개",4,25),("가재",5,15)],
        "중형":[("잉어",41,99),("향어",50,80),("메기",60,90),("동자개",45,70),("붕어왕",70,95)],
        "대형":[("철갑상어",100,300),("쏘가리",100,180),("민물가오리",120,250),("대형메기",200,500),("괴물잉어",300,600)],
    },
    "바다": {
        "소형":[("전어",10,30),("멸치",5,15),("정어리",10,25),("고등어",20,40),("청어",15,35)],
        "중형":[("방어",50,90),("도미",60,95),("삼치",45,80),("참소라",50,70),("오징어",40,85)],
        "대형":[("참치",100,600),("상어",200,800),("고래상어",500,1000),("만새기",150,400),("황새치",200,700)],
    }
}

# -----------------------------
# 저장/로드
# -----------------------------
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
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_PATH)

def today_str():
    return date.today().isoformat()

# -----------------------------
# 칭호/레벨
# -----------------------------
def get_title(level: int) -> str:
    # 확정: 낚린이(1~30), 낚시인(31~70), 전문낚시인(71~99), 프로(100+)
    if level <= 0:
        level = 1
    if level < 31:
        return "낚린이"
    elif level < 71:
        return "낚시인"
    elif level < 100:
        return "전문낚시인"
    else:
        return "프로"

def title_attendance_reward(title: str) -> int:
    # 출석 제한골드 보상(칭호별)
    return {
        "낚린이": 150,
        "낚시인": 300,
        "전문낚시인": 1000,
        "프로": 3000,
    }.get(title, 0)

def level_threshold(lv:int) -> int:
    # 다음 레벨까지 필요 EXP = 100 + 50*(lv-1)
    return 100 + 50 * (lv - 1)

# -----------------------------
# 신규 유저 기본값
# -----------------------------
def get_user(store, uid):
    u = store["users"].get(uid)
    if u is None:
        u = {
            "nickname": None,          # 닉네임 미설정
            "nick_locked": False,      # 닉네임 확정 여부
            "gold": 0,                 # 기본 소지금 0
            "restricted_gold": 0,      # 기본 제한골드 0
            "level": 1,
            "exp": 0,
            "rod": "철제 낚싯대",
            "inventory": {},           # 소모품/수량
            "fish": [],                # 가방 물고기
            "attendance_last": None,   # 마지막 출석 일자
            "newbie": {"date": None, "count": 0},  # 초보자찬스
            "additive_uses": 0,        # 집어제 효과 남은 횟수
            "pending_sale": None,      # 되팔기 대기 {name, qty, refund}
            "location": None,          # "바다"/"민물"
            "records": {"min": None, "max": None}, # 평생 기록
        }
        store["users"][uid] = u
    # 마이그레이션 안전장치
    u.setdefault("location", None)
    u.setdefault("records", {"min": None, "max": None})
    return u

# -----------------------------
# 포맷/시간
# -----------------------------
def kakao_text(text):
    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]}
    })

def fmt_money(g, r):
    return f"Gold: 💰{g:,} | 제한골드: 💰{r:,}"

def is_night(now=None) -> bool:
    now = now or datetime.now()
    t = now.time()
    return (t >= time(20,0)) or (t < time(5,0))

# -----------------------------
# 가방 5칸 규칙
# -----------------------------
def slot_usage(u):
    used = 0
    slots = []
    for f in u["fish"]:        # 물고기: 개체당 1칸
        if used < 5:
            slots.append({"type":"fish","data":f})
            used += 1
    for name, cnt in u["inventory"].items():  # 소모품: 종류당 1칸
        if cnt > 0 and name in CONSUMABLES and used < 5:
            slots.append({"type":"consumable","name":name,"count":cnt})
            used += 1
    while used < 5:
        slots.append({"type":"empty"})
        used += 1
    return slots

def bag_full(u) -> bool:
    return all(s["type"] != "empty" for s in slot_usage(u))

def will_overflow_if_add_consumable(u, name):
    cnt = u["inventory"].get(name, 0)
    if cnt > 0:
        return False
    return all(s["type"] != "empty" for s in slot_usage(u))

# -----------------------------
# 소모품 추가/감소 (지렁이/떡밥 100개 한도)
# -----------------------------
def add_consumable(u, name, qty):
    before = u["inventory"].get(name, 0)
    after = before + qty
    limit = 100 if name in {"지렁이", "떡밥"} else None

    note = None
    if limit is not None:
        if after > limit:
            u["inventory"][name] = limit
            gained = max(0, limit - before)
            if gained < qty:
                note = f"{name} 최대 보유 한도는 {limit}개입니다. {gained}개만 추가되었습니다."
        else:
            u["inventory"][name] = after
    else:
        u["inventory"][name] = after

    if u["inventory"][name] <= 0:
        del u["inventory"][name]

    return note  # 한도 걸릴 때 안내 문구(없으면 None)

# -----------------------------
# 홈 화면('/')
# -----------------------------
def home_text(u):
    lines = []
    lines += [
        "🎣 낚시 RPG 사용법",
        "1) /장소 [바다|민물] ← 먼저 장소를 설정하세요",
        "2) /낚시 [1~60]s ← 해당 초 만큼 캐스팅 (예: /낚시 15s)",
        "3) 시간이 끝나면 /릴감기 로 결과 확인",
        "",
        "🏪 상점 이용 방법",
        "/상점 → 상점 목록 보기",
        "/구매 [이름] [갯수] → 예: /구매 지렁이 10개, /구매 케미라이트1등급 1개",
        "/아이템판매 [이름] [수량] → 되팔기(구매가의 50%)",
        "",
        "(출석/보너스)",
        "/출석 → 출석 보상 받기",
        "/초보자찬스 → 낚린이 전용 보너스(1일 3회, 잔액 0일 때만 수령)",
        "",
    ]
    title = get_title(u["level"])
    lines.append(f"닉네임: [{title}] {u['nickname'] or '(미설정)'}")
    lines += [
        "[상태]",
        f"Lv.{u['level']}  Exp: {u['exp']}/{level_threshold(u['level'])}",
        f"{fmt_money(u['gold'], u['restricted_gold'])}",
        f"착용 낚싯대: {u['rod']}",
    ]
    if u["additive_uses"] > 0:
        lines.append(f"집어제 효과 남은 횟수: {u['additive_uses']}회")
    lines.append("")
    slots = slot_usage(u)
    used = sum(1 for s in slots if s["type"] != "empty")
    lines.append(f"[가방] {used}/5칸 사용")
    for i, s in enumerate(slots, start=1):
        if s["type"] == "empty":
            lines.append(f"{i}. 비어있음")
        elif s["type"] == "fish":
            f = s["data"]
            lines.append(f"{i}. {f['name']} {f['cm']}cm ({f['grade']}) - 판매가 {f['price']}골드")
        else:
            name = s["name"]; cnt = s["count"]
            suffix = ""
            if name == "집어제":
                suffix = " · 사용: /집어제사용 (3회 지속)"
            elif name.startswith("케미라이트"):
                suffix = " · 사용: /" + name + " 사용 (1회성 · 20:00~05:00)"
            lines.append(f"{i}. {name} ({cnt}개) - 소모품{suffix}")
    owned = set(k for k,v in u["inventory"].items() if v>0)
    missing = [x for x in ["지렁이","떡밥","집어제","케미라이트1등급","케미라이트2등급","케미라이트3등급"] if x not in owned]
    if missing:
        lines.append("")
        lines.append("보유하지 않은 물품: " + ", ".join(missing))
    return "\n".join(lines)

# -----------------------------
# 상점 UI
# -----------------------------
def shop_text(u):
    lines = []
    lines.append("🏪 상점\n")
    lines += [
        "[소모품]",
        f"- 지렁이 (1개) | 💰{PRICES['지렁이']:,}  ← 제한골드 사용 가능 (보유 한도 100개)",
        f"- 떡밥   (1개) | 💰{PRICES['떡밥']:,}  ← 제한골드 사용 가능 (보유 한도 100개)",
        f"- 집어제 (1개) | 💰{PRICES['집어제']:,}  ※ 사용 시 3회 지속",
        f"- 케미라이트3등급 (1개) | 💰{PRICES['케미라이트3등급']:,}  ※ 사용 1회성, 20:00~05:00",
        f"- 케미라이트2등급 (1개) | 💰{PRICES['케미라이트2등급']:,}  ※ 사용 1회성, 20:00~05:00",
        f"- 케미라이트1등급 (1개) | 💰{PRICES['케미라이트1등급']:,}  ※ 사용 1회성, 20:00~05:00",
        "",
        "[장비]",
        f"- 철제 낚싯대 | 💰{PRICES['철제 낚싯대']:,}",
        f"- 강화 낚싯대 | 💰{PRICES['강화 낚싯대']:,}",
        f"- 프로 낚싯대 | 💰{PRICES['프로 낚싯대']:,}",
        f"- 레전드 낚싯대 | 💰{PRICES['레전드 낚싯대']:,}",
        "",
        "구매: /구매 [이름] [갯수]",
        "예) /구매 지렁이 10개, /구매 케미라이트1등급 1개",
        "되팔기: /아이템판매 [이름] [수량]  (구매가의 50%)",
        "정책",
        "- 제한골드는 지렁이/떡밥에만 사용 (우선 차감)",
        "- 케미라이트: 밤(20:00~05:00)만 사용 가능",
        "- 집어제: 사용 시 3회 지속 효과",
    ]
    return "\n".join(lines)

# -----------------------------
# 가격/경험치
# -----------------------------
def fish_price(grade):
    return {"소형": 20, "중형": 40, "대형": 80}.get(grade, 20)

def fish_exp(cm, grade):
    if grade == "대형": return cm * 100
    if grade == "중형": return cm * 10
    return cm

def add_exp(u, amount):
    u["exp"] += amount    # 누적 EXP (게이지가 넘쳐도 계속 누적)
    while u["exp"] >= level_threshold(u["level"]):
        u["exp"] -= level_threshold(u["level"])
        u["level"] += 1

# -----------------------------
# 가방 텍스트
# -----------------------------
def bag_text_lines(u):
    slots = slot_usage(u)
    used = sum(1 for s in slots if s["type"] != "empty")
    lines = [f"[가방] {used}/5칸 사용"]
    for i, s in enumerate(slots, start=1):
        if s["type"] == "empty":
            lines.append(f"{i}. 비어있음")
        elif s["type"] == "fish":
            f = s["data"]
            lines.append(f"{i}. {f['name']} {f['cm']}cm ({f['grade']}) - 판매가 {f['price']}골드")
        else:
            name = s["name"]; cnt = s["count"]
            suffix = ""
            if name == "집어제":
                suffix = " · 사용: /집어제사용 (3회 지속)"
            elif name.startswith("케미라이트"):
                suffix = " · 사용: /" + name + " 사용 (1회성 · 20:00~05:00)"
            lines.append(f"{i}. {name} ({cnt}개) - 소모품{suffix}")
    return lines

def bag_full_block_text(u):
    lines = []
    lines.append("⚠️ 가방이 가득 차 낚시를 진행할 수 없습니다. (5/5칸)")
    night = is_night()
    has_chum = u["inventory"].get("집어제", 0) > 0
    has_chem_any = any(u["inventory"].get(k,0) > 0 for k in ["케미라이트1등급","케미라이트2등급","케미라이트3등급"])

    offered = False
    if has_chum or (has_chem_any and night):
        lines.append("가방이 가득 찼습니다. 아래 소모품 중 하나를 사용하시겠어요?")
        if has_chum:
            lines.append("• /집어제사용")
            offered = True
        if has_chem_any and night:
            for k in ["케미라이트1등급","케미라이트2등급","케미라이트3등급"]:
                if u["inventory"].get(k,0)>0:
                    lines.append(f"• /{k} 사용")
                    offered = True
            lines.append("※ 케미라이트 사용시간 제한: 20:00~05:00")
    else:
        if has_chem_any and not night:
            t = datetime.now().strftime("%H:%M")
            lines.append(f"※ 케미라이트는 낮 시간({t})에는 사용할 수 없습니다. 사용 가능 시간: 20:00~05:00")

    if not offered:
        total = sum(f["price"] for f in u["fish"])
        lines.append("가방에 사용 가능한 소모품이 없습니다. 대신 가방 속 물고기를 전부 판매하시겠습니까?")
        lines.append("👉 /전부판매 입력 시 즉시 판매 후 칸이 비워집니다.")
        lines.append(f"예상 판매 금액: 💰{total:,}")
        lines.append(f"판매 후 소지금: 💰{u['gold']+total:,} | 제한골드: 💰{u['restricted_gold']:,}")
    lines.append("")
    lines += bag_text_lines(u)
    return "\n".join(lines)

# -----------------------------
# 기록(평생) 업데이트
# -----------------------------
def update_records(u, fish_obj):
    rec = u["records"]
    if rec["min"] is None or fish_obj["cm"] < rec["min"]["cm"]:
        rec["min"] = {
            "name": fish_obj["name"],
            "cm": fish_obj["cm"],
            "grade": fish_obj["grade"],
            "location": fish_obj.get("location") or "알 수 없음",
            "caught_at": fish_obj.get("caught_at")
        }
    if rec["max"] is None or fish_obj["cm"] > rec["max"]["cm"]:
        rec["max"] = {
            "name": fish_obj["name"],
            "cm": fish_obj["cm"],
            "grade": fish_obj["grade"],
            "location": fish_obj.get("location") or "알 수 없음",
            "caught_at": fish_obj.get("caught_at")
        }

# -----------------------------
# ===== 장소/인벤/미끼 유틸 =====
def _normalize_location(raw):
    """입력된 장소를 '바다' 또는 '민물'로 정규화"""
    if not raw:
        return None
    s = str(raw).strip().lower().replace(" ", "")
    if s in ("바다", "sea", "ocean"):
        return "바다"
    if s in ("민물", "민", "fresh", "freshwater", "river", "lake"):
        return "민물"
    return None

def _bait_key_for(loc):
    """장소에 맞는 미끼 키를 반환 ('지렁이' 또는 '떡밥')"""
    if loc == "바다":
        return "지렁이"
    if loc == "민물":
        return "떡밥"
    return None

# 프로젝트에 따라 인벤 키명이 다를 수 있어 alias 지원
_BAIT_ALIASES = {
    "지렁이": ["지렁이", "미끼_지렁이", "bait_worm"],
    "떡밥": ["떡밥", "미끼_떡밥", "bait_dough"],
}

def _get_inv_qty(inv: dict, canonical_key: str) -> int:
    """여러 alias 중 존재하는 키를 찾아 수량 반환"""
    for k in _BAIT_ALIASES[canonical_key]:
        if k in inv:
            return int(inv.get(k, 0))
    return 0

def _dec_inv(inv: dict, canonical_key: str, n: int = 1) -> int:
    """여러 alias 중 존재하는 키에서 차감, 없으면 canonical 키 생성"""
    # 우선 존재하는 alias를 찾아 차감
    for k in _BAIT_ALIASES[canonical_key]:
        if k in inv:
            inv[k] = max(0, int(inv.get(k, 0)) - n)
            return inv[k]
    # 하나도 없으면 canonical 키를 만들어 차감(음수 방지)
    inv[canonical_key] = max(0, int(inv.get(canonical_key, 0)) - n)
    return inv[canonical_key]

def ensure_bait_and_consume(u: dict):
    """
    장소에 맞는 미끼가 1개 이상 있는지 확인하고, 있으면 즉시 1개 차감.
    - 프로젝트에 add_consumable(u, key, delta)가 있으면 그걸 우선 사용(영속/동기화 보장)
    - 없으면 inventory dict 직접 차감(fallback)
    """
    loc = _normalize_location(u.get("location"))
    if not loc:
        return False, "⚠️ 먼저 /장소 [바다|민물] 을 설정하세요."
    need = _bait_key_for(loc)
    if not need:
        return False, "⚠️ 지원하지 않는 장소입니다. /장소 [바다|민물]"

    inv = u.setdefault("inventory", {})

    # 보유 수량 확인(별칭 포함)
    have = _get_inv_qty(inv, need)
    if have <= 0:
        return False, f"⚠️ {need}가 없어 '{loc}'에서 낚시할 수 없습니다.\n/상점 에서 {need}를 구매해 주세요."

    # 표준 헬퍼(add_consumable)가 있으면 그것을 우선 사용
    try:
        _ = add_consumable(u, need, -1)  # 존재하면 DB/파일에도 반영되는 경로일 가능성 큼
        remain = _get_inv_qty(inv, need) # 실제 남은 수량 재확인
    except Exception:
        # 없거나 실패하면 직접 차감
        remain = _dec_inv(inv, need, 1)

    return True, f"✅ {need} 1개 사용됨 (남은 {need}: {remain}개)"
# --------------------------------------------------------------
# 낚시 흐름(간단)
# -----------------------------
def handle_cast(u, seconds:int):
    if bag_full(u):
        return bag_full_block_text(u)
    u["casting"] = {"seconds": seconds, "start": datetime.now().isoformat()}
    return "캐스팅 시작! 시간이 끝나면 /릴감기 로 결과를 확인하세요."

def handle_reel(u):
    if u.get("additive_uses", 0) > 0:
        u["additive_uses"] -= 1
    if bag_full(u):
        return bag_full_block_text(u)

    import random
    cm = random.randint(20, 35)
    grade = "소형" if cm < 26 else ("중형" if cm < 31 else "대형")
    price = fish_price(grade)
    gain = fish_exp(cm, grade)

    loc = u.get("location") or "알 수 없음"
    fish_obj = {
        "name": "붕어",
        "cm": cm,
        "grade": grade,
        "price": price,
        "location": loc,
        "caught_at": today_str()  # 잡은 날짜 기록
    }
    u["fish"].append(fish_obj)
    update_records(u, fish_obj)
    add_exp(u, gain)

    msg = []
    msg.append(f"🎣 낚시 성공! {fish_obj['name']} {cm}cm ({grade})을(를) 낚았습니다!")
    msg.append(f"가격: 💰{price:,} | 경험치 +{gain} | 장소: {loc}")
    msg.append("")
    msg += bag_text_lines(u)
    return "\n".join(msg)

# -----------------------------
# 판매/전부판매/되팔기
# -----------------------------
def sell_all_fish(u):
    total = sum(f["price"] for f in u["fish"])
    u["gold"] += total
    u["fish"].clear()
    return f"전부판매 완료: 💰{total:,} 획득\n{fmt_money(u['gold'], u['restricted_gold'])}"

def start_resell(u, name, qty):
    if name not in PRICES:
        return "해당 아이템은 되팔 수 없습니다."
    have = u["inventory"].get(name, 0)
    if qty <= 0 or have < qty:
        return "수량이 올바르지 않거나 보유 수량이 부족합니다."
    refund = (PRICES[name] * qty) // 2
    u["pending_sale"] = {"name":name, "qty":qty, "refund":refund}
    return (
        "⚠️ 되팔기 안내\n"
        "상점에서 산 물건을 되팔면 구매가격의 50%만 환불됩니다.\n"
        f"판매 대상: {name} ×{qty}\n"
        f"환불 예정: 💰{refund:,}\n"
        "진행하시겠습니까?\n"
        "/판매확인 | /판매취소"
    )

def confirm_resell(u, ok:bool):
    if not u.get("pending_sale"):
        return "대기 중인 되팔기 내역이 없습니다."
    if not ok:
        u["pending_sale"] = None
        return "판매가 취소되었습니다."
    ps = u["pending_sale"]
    add_consumable(u, ps["name"], -ps["qty"])
    u["gold"] += ps["refund"]
    u["pending_sale"] = None
    return f"판매 완료: 💰{ps['refund']:,} 환불\n{fmt_money(u['gold'], u['restricted_gold'])}"

# -----------------------------
# 물고기 데이터
# -----------------------------
FISH_POOL = {
    "민물": {
        "소형":[("붕어",1,40),("피라미",5,35),("미꾸라지",3,20),("몰개",4,25),("가재",5,15)],
        "중형":[("잉어",41,99),("향어",50,80),("메기",60,90),("동자개",45,70),("붕어왕",70,95)],
        "대형":[("철갑상어",100,300),("쏘가리",100,180),("민물가오리",120,250),("대형메기",200,500),("괴물잉어",300,600)],
    },
    "바다": {
        "소형":[("전어",10,30),("멸치",5,15),("정어리",10,25),("고등어",20,40),("청어",15,35)],
        "중형":[("방어",50,90),("도미",60,95),("삼치",45,80),("참소라",50,70),("오징어",40,85)],
        "대형":[("참치",100,600),("상어",200,800),("고래상어",500,1000),("만새기",150,400),("황새치",200,700)],
    }
}

# -----------------------------
# 유틸
# -----------------------------
def load_store():
    if not os.path.exists(DATA_PATH): return {"users":{}}
    try:
        with open(DATA_PATH,"r",encoding="utf-8") as f: return json.load(f)
    except: return {"users":{}}

def save_store(store):
    tmp=DATA_PATH+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(store,f,ensure_ascii=False,indent=2)
    os.replace(tmp,DATA_PATH)

def today_str(): return date.today().isoformat()

def kakao_text(t): 
    return jsonify({"version":"2.0","template":{"outputs":[{"simpleText":{"text":t}}]}})

def fmt_money(g,r): return f"Gold: 💰{g:,} | 제한골드: 💰{r:,}"

def is_night(now=None): 
    now=now or datetime.now(); t=now.time()
    return (t>=time(20,0)) or (t<time(5,0))

# -----------------------------
# 유저 데이터
# -----------------------------
def get_user(store, uid):
    u = store["users"].get(uid)
    if u is None:
        u={"nickname":None,"nick_locked":False,"gold":0,"restricted_gold":0,
           "level":1,"exp":0,"rod":"철제 낚싯대","inventory":{},"fish":[],
           "attendance_last":None,"newbie":{"date":None,"count":0},
           "additive_uses":0,"location":None,"records":{"min":None,"max":None},
           "casting":None,"active_buff":None}
        store["users"][uid]=u
    return u

# -----------------------------
# 경험치/레벨
# -----------------------------
def level_threshold(lv:int)->int: return 100+50*(lv-1)
def add_exp(u, amount):
    u["exp"]+=amount
    while u["exp"]>=level_threshold(u["level"]):
        u["exp"]-=level_threshold(u["level"]); u["level"]+=1

def update_records(u, fish_obj):
    rec=u["records"]
    if rec["min"] is None or fish_obj["cm"]<rec["min"]["cm"]: rec["min"]=fish_obj
    if rec["max"] is None or fish_obj["cm"]>rec["max"]["cm"]: rec["max"]=fish_obj

# -----------------------------
# 확률 계산
# -----------------------------
def calc_prob(seconds:int,u)->dict:
    sec=min(seconds,60)
    base={"소형":0.30,"중형":0.01,"대형":0.00005}
    base["소형"]+=0.10*(sec/60)
    base["중형"]+=0.01*(sec/60)
    base["대형"]+=0.00005*(sec/60)
    # 집어제
    if u.get("additive_uses",0)>0:
        base["중형"]+=0.02; base["대형"]+=0.00005
    # 케미라이트
    buff=u.get("active_buff")
    if buff=="케미라이트1등급":
        for k in ["소형","중형","대형"]: base[k]*=1.30
    elif buff=="케미라이트2등급":
        for k in ["소형","중형","대형"]: base[k]*=1.20
    elif buff=="케미라이트3등급":
        for k in ["소형","중형","대형"]: base[k]*=1.05
    total=sum(base.values())
    base["실패"]=max(0.0,1.0-total)
    return base

# -----------------------------
# 낚시/릴감기
# -----------------------------
def handle_cast(u, seconds:int):
    if not u.get("location"):
        return "⚠️ 먼저 /장소 [바다|민물] 을 설정하세요."
    if len(u["fish"])>=BAG_CAP:
        return "⚠️ 가방이 가득 찼습니다."
    u["casting"]={"seconds":seconds,"start":datetime.now().isoformat()}
    return f"{seconds}초 캐스팅 시작! 시간이 끝나면 /릴감기 로 결과 확인하세요."

def handle_reel(u):
    if not u.get("location"):
        return "⚠️ 장소가 설정되지 않았습니다. /장소 [바다|민물] 을 먼저 입력하세요."
    if not u.get("casting"):
        return "⚠️ 캐스팅 기록이 없습니다. 먼저 /낚시 [초] 로 시도하세요."
    if u.get("additive_uses",0)>0:
        u["additive_uses"]-=1
    if len(u["fish"])>=BAG_CAP:
        return "⚠️ 가방이 가득 찼습니다."

    seconds=u["casting"]["seconds"]
    prob=calc_prob(seconds,u)
    roll=random.random()
    outcome="실패"; cum=0.0
    for k,v in prob.items():
        cum+=v
        if roll<=cum: outcome=k; break
    u["casting"]=None

    if outcome=="실패":
        return "🎣 낚시 실패... 다시 도전해 보세요!"

    loc=u["location"]; fishlist=FISH_POOL[loc][outcome]
    name,smin,smax=random.choice(fishlist); cm=random.randint(smin,smax)

    # 사이즈별 기본 산식
    if outcome=="소형": base_price,base_exp=cm*1,cm*1
    elif outcome=="중형": base_price,base_exp=cm*100,cm*10
    else: base_price,base_exp=cm*1000,cm*100

    # 지역 보정
    if loc=="민물":
        price=int(base_price*0.5); exp=int(base_exp*1.5)
    else:
        price=int(base_price*1.5); exp=int(base_exp*0.5)

    fish_obj={"name":name,"cm":cm,"grade":outcome,"price":price,
              "location":loc,"caught_at":today_str()}
    u["fish"].append(fish_obj)
    update_records(u,fish_obj)
    add_exp(u,exp)

    return f"🎣 {name} {cm}cm ({outcome}) 낚음!\n가격:💰{price:,} | 경험치 +{exp} | 장소:{loc}"

# -----------------------------
# 구매
# -----------------------------
def try_buy(u, name, qty):
    if name not in PRICES:
        return False, "존재하지 않는 상품입니다."
    if qty <= 0:
        return False, "구매 수량이 올바르지 않습니다."

    # 가방 수용 체크(새 소모품 종류를 0→보유로 바꿀 때 1칸 필요)
    if name in CONSUMABLES and will_overflow_if_add_consumable(u, name):
        return False, "가방이 부족해요. (구매 후 5/5칸)"

    unit = PRICES[name]
    total = unit * qty

    use_restricted = 0
    use_gold = 0
    if name in RESTRICTED_ALLOWED:
        use_restricted = min(u["restricted_gold"], total)
        remain = total - use_restricted
        if remain > u["gold"]:
            return False, f"⚠️ 골드가 부족합니다. 필요: 💰{total:,} / 보유: 💰{u['gold']:,} | 제한골드: 💰{u['restricted_gold']:,}"
        use_gold = remain
    else:
        if total > u["gold"]:
            return False, f"⚠️ 골드가 부족합니다. 필요: 💰{total:,} / 보유: 💰{u['gold']:,}"
        use_gold = total

    u["gold"] -= use_gold
    u["restricted_gold"] -= use_restricted

    limit_note = None
    if name in CONSUMABLES:
        limit_note = add_consumable(u, name, qty)
        base = f"{name}({qty}개)를 구매했어요."
        if limit_note:
            base += f"\n{limit_note}"
        return True, base + f"\n잔액  {fmt_money(u['gold'], u['restricted_gold'])}"
    else:
        u["rod"] = name
        return True, f"{name}를(을) 구매했어요.\n잔액  {fmt_money(u['gold'], u['restricted_gold'])}"

# -----------------------------
# 명령 처리
# -----------------------------
def handle_cmd(u, utt:str):
    t = (utt or "").strip()

    # 닉네임 미설정
    if not u["nick_locked"]:
        if t.startswith("/닉네임 "):
            nickname = t.replace("/닉네임 ","",1).strip()
            if not nickname:
                return "닉네임 설정 형식: /닉네임 원하는이름"
            u["nickname"] = nickname
            u["nick_locked"] = True
            return f"닉네임이 '{nickname}'(으)로 설정되었습니다.\n이제 '/' 로 홈 화면을 확인해 보세요."
        if t == "/":
            return (
                "🎣 낚시 RPG에 오신 것을 환영합니다!\n\n"
                "닉네임을 먼저 설정해 주세요.\n"
                "닉네임은 한 번 설정하면 변경할 수 없습니다.\n\n"
                "설정 방법: /닉네임 [원하는이름]\n"
                "예) /닉네임 홍길동"
            )
        return ""

    # 홈
    if t in ("/","홈","home","메뉴"):
        return home_text(u)

    # 장소 설정
    if t.startswith("/장소"):
        parts = t.split()
        if len(parts) >= 2 and parts[1] in ("바다","민물"):
            u["location"] = parts[1]
            return f"장소를 '{u['location']}'(으)로 설정했습니다. 이제 /낚시 [1~60]s 로 캐스팅해 보세요."
        return "형식: /장소 [바다|민물]"

    # 상점
    if t == "/상점":
        return shop_text(u)

    # 출석 (칭호별 제한골드 지급)
    if t == "/출석":
        today = today_str()
        if u["attendance_last"] == today:
            return "오늘은 이미 출석 체크를 하였습니다."
        u["attendance_last"] = today
        title = get_title(u["level"])
        reward = title_attendance_reward(title)

        # 낚린이는 제한골드 1000 초과 불가(캡 적용)
        if title == "낚린이":
            before = u["restricted_gold"]
            after = min(RESTRICTED_CAP, before + reward)
            gained = max(0, after - before)
            u["restricted_gold"] = after
            if gained == 0:
                return f"낚린이는 제한골드 보유 상한이 {RESTRICTED_CAP}입니다. 잔액을 사용한 뒤 다시 출석해 주세요.\n{fmt_money(u['gold'], u['restricted_gold'])}"
            return f"✅ 출석 보상 {gained}골드 지급! ({title})\n{fmt_money(u['gold'], u['restricted_gold'])}"

        # 낚린이 외 구간: 출석으로는 1000 초과 허용
        u["restricted_gold"] = u["restricted_gold"] + reward
        return f"✅ 출석 보상 {reward}골드 지급! ({title})\n{fmt_money(u['gold'], u['restricted_gold'])}"

    # 초보자찬스 (1일 3회, 제한골드 0일 때만 1000 수령)
    if t == "/초보자찬스":
        today = today_str()
        nb = u["newbie"]
        if nb.get("date") != today:
            nb["date"] = today
            nb["count"] = 0
        if nb["count"] >= 3:
            return "오늘은 이미 3회 모두 사용했습니다."
        # 제한골드가 정확히 0일 때만 수령 가능
        if u["restricted_gold"] != 0:
            return (
                "제한골드 잔액이 0이어야 초보자찬스를 받을 수 있습니다.\n"
                f"현재 {fmt_money(u['gold'], u['restricted_gold'])}\n"
                "지렁이/떡밥 구매 등으로 제한골드를 모두 사용한 뒤 다시 시도해 주세요."
            )
        # 수령 시 1000으로 세팅
        u["restricted_gold"] = RESTRICTED_CAP
        nb["count"] += 1
        return f"초보자찬스 사용 {nb['count']}/3회: 제한골드 1,000 지급\n{fmt_money(u['gold'], u['restricted_gold'])}"

    # 전부판매
    if t == "/전부판매":
        return sell_all_fish(u)

    # 되팔기 확인/취소
    if t == "/판매확인":
        return confirm_resell(u, True)
    if t == "/판매취소":
        return confirm_resell(u, False)

    # 소모품 사용
    if t == "/집어제사용":
        if u["inventory"].get("집어제",0) <= 0:
            return "집어제가 없습니다."
        add_consumable(u, "집어제", -1)
        u["additive_uses"] = 3
        return "✅ 집어제 1개를 사용했습니다. (효과 3회 지속)"

    if t.endswith(" 사용") and t.startswith("/케미라이트"):
        item = t[1:-3].strip()
        if item not in {"케미라이트1등급","케미라이트2등급","케미라이트3등급"}:
            return ""
        if not is_night():
            now = datetime.now().strftime("%H:%M")
            return f"케미라이트는 낮 시간({now})에는 사용할 수 없습니다. 사용 가능 시간: 20:00~05:00"
        if u["inventory"].get(item,0) <= 0:
            return f"{item} 이(가) 없습니다."
        add_consumable(u, item, -1)
        return f"✅ {item} 1개를 사용했습니다. (1회성 · 20:00~05:00)"

    # 되팔기 시작 (/아이템판매 [이름] [수량])
    if t.startswith("/아이템판매"):
        rest = t.replace("/아이템판매","",1).strip()
        if not rest:
            return "형식: /아이템판매 [이름] [수량]"
        parts = rest.split()
        if len(parts) < 2:
            return "형식: /아이템판매 [이름] [수량]"
        name = " ".join(parts[:-1])
        qty_txt = parts[-1]
        qty = 0
        for ch in qty_txt:
            if ch.isdigit():
                qty = qty*10 + int(ch)
        if qty <= 0:
            return "수량을 숫자로 입력해 주세요."
        return start_resell(u, name, qty)

    # 구매 (/구매 [이름] [갯수])
    if t.startswith("/구매 "):
        rest = t.replace("/구매","",1).strip()
        parts = rest.split()
        if len(parts) < 2:
            return "형식: /구매 [이름] [갯수]\n예) /구매 지렁이 10개"
        qty_txt = parts[-1]
        qty = 0
        for ch in qty_txt:
            if ch.isdigit():
                qty = qty*10 + int(ch)
        if qty <= 0:
            return "구매 수량을 숫자로 입력해 주세요. 예) /구매 지렁이 10개"
        name = " ".join(parts[:-1])
        ok, msg = try_buy(u, name, qty)
        return msg

    # 낚시/릴감기
    if t.startswith("/낚시"):
        num = 0
        for ch in t:
            if ch.isdigit():
                num = num*10 + int(ch)
        if num <= 0 or num > 60:
            return "낚시 시간은 1~60초 사이로 입력해 주세요. 예) /낚시 15s"
        if bag_full(u):
            return bag_full_block_text(u)
        return handle_cast(u, num)

    if t == "/릴감기":
        return handle_reel(u)

    # 기록: 1) 최대크기 2) 최소크기 3) 종류별 1마리(장소+날짜)
    if t == "/기록":
        rec = u.get("records") or {}
        mn = rec.get("min")
        mx = rec.get("max")
        lines = []

        # 첫째줄: 최대
        if mx:
            lines.append(f"[최대크기] {mx['name']} {mx['cm']}cm ({mx['grade']}) - {mx.get('location','알 수 없음')}")
        else:
            lines.append("[최대크기] 기록 없음")

        # 둘째줄: 최소
        if mn:
            lines.append(f"[최소크기] {mn['name']} {mn['cm']}cm ({mn['grade']}) - {mn.get('location','알 수 없음')}")
        else:
            lines.append("[최소크기] 기록 없음")

        # 셋째줄 이후: 종류별 1마리(장소+날짜)
        if u["fish"]:
            lines.append("")
            lines.append("📜 잡은 물고기 기록 (종류별 1마리)")
            seen = set()
            for f in u["fish"]:
                key = f["name"]
                if key not in seen:
                    seen.add(key)
                    lines.append(f"- {f['name']} {f['cm']}cm ({f['grade']}) | 장소: {f.get('location','알 수 없음')} | 날짜: {f.get('caught_at','알 수 없음')}")
        else:
            lines.append("")
            lines.append("📜 잡은 물고기 기록 없음")

        return "\n".join(lines)

    return ""

# -----------------------------
# 라우팅
# -----------------------------
@app.get("/")
def health():
    return "OK", 200

@app.route("/skill", methods=["GET","POST"], strict_slashes=False)
@app.route("/skill/", methods=["GET","POST"], strict_slashes=False)
def skill():
    if request.method == "GET":
        return kakao_text(""), 200

    body = request.get_json(silent=True) or {}
    user_req = body.get("userRequest", {})
    utter = (user_req.get("utterance") or "").strip()
    uid = user_req.get("user", {}).get("id") or "anonymous"

    if not is_allowed_command(utter):
        return kakao_text(""), 200

    store = load_store()
    u = get_user(store, uid)
    text = handle_cmd(u, utter)
    save_store(store)
    return kakao_text(text or ""), 200

# -----------------------------
# 로컬 실행
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))


# ===== Integrated from app_final.py =====

import os
import json
import random
from datetime import datetime, time, date
from flask import Flask, request, jsonify
from threading import Timer

app = Flask(__name__)
DATA_PATH = os.environ.get("DATA_PATH", "data.json")

# -----------------------------
# 상수/정책
# -----------------------------
RESTRICTED_CAP = 1000
BAG_CAP = 5

# -----------------------------
# 상점/아이템 정의
# -----------------------------
PRICES = {
    "지렁이": 10,
    "떡밥": 10,
    "집어제": 2000,
    "케미라이트1등급": 1000,
    "케미라이트2등급": 350,
    "케미라이트3등급": 200,
    "철제 낚싯대": 5000,
    "강화 낚싯대": 20000,
    "프로 낚싯대": 100000,
    "레전드 낚싯대": 500000,
}
CONSUMABLES = {"지렁이", "떡밥", "집어제", "케미라이트1등급", "케미라이트2등급", "케미라이트3등급"}
RESTRICTED_ALLOWED = {"지렁이", "떡밥"}

# -----------------------------
# 장소/미끼 관련 유틸
# -----------------------------
def _normalize_location(raw):
    if not raw:
        return None
    s = str(raw).strip().lower().replace(" ", "")
    if s in ("바다","sea","ocean"):
        return "바다"
    if s in ("민물","fresh","freshwater","river","lake"):
        return "민물"
    return None

def _bait_key_for(loc):
    if loc=="바다": return "지렁이"
    if loc=="민물": return "떡밥"
    return None

def ensure_bait_and_consume(u:dict):
    loc = _normalize_location(u.get("location"))
    if not loc:
        return False,"⚠️ 먼저 /장소 [바다|민물] 을 설정하세요."
    need = _bait_key_for(loc)
    inv = u.setdefault("inventory",{})
    have = inv.get(need,0)
    if have<=0:
        return False,f"⚠️ {need}가 없어 '{loc}'에서 낚시할 수 없습니다."
    inv[need]=have-1
    return True,f"✅ {need} 1개 사용됨 (남은 {need}: {inv[need]}개)"

# -----------------------------
# 저장/로드
# -----------------------------
def load_store():
    if not os.path.exists(DATA_PATH): return {"users":{}}
    try:
        with open(DATA_PATH,"r",encoding="utf-8") as f: return json.load(f)
    except: return {"users":{}}

def save_store(store):
    tmp=DATA_PATH+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(store,f,ensure_ascii=False,indent=2)
    os.replace(tmp,DATA_PATH)

def today_str(): return date.today().isoformat()

def kakao_text(t): 
    return jsonify({"version":"2.0","template":{"outputs":[{"simpleText":{"text":t}}]}})

# -----------------------------
# 유저 데이터
# -----------------------------
def get_user(store, uid):
    u = store["users"].get(uid)
    if u is None:
        u={"nickname":None,"nick_locked":False,"gold":0,"restricted_gold":0,
           "level":1,"exp":0,"rod":"철제 낚싯대","inventory":{},"fish":[],
           "attendance_last":None,"newbie":{"date":None,"count":0},
           "additive_uses":0,"location":None,"records":{"min":None,"max":None},
           "casting":None,"active_buff":None}
        store["users"][uid]=u
    return u

# -----------------------------
# 경험치/레벨
# -----------------------------
def level_threshold(lv:int)->int: return 100+50*(lv-1)
def add_exp(u, amount):
    u["exp"]+=amount
    while u["exp"]>=level_threshold(u["level"]):
        u["exp"]-=level_threshold(u["level"]); u["level"]+=1

def update_records(u, fish_obj):
    rec=u["records"]
    if rec["min"] is None or fish_obj["cm"]<rec["min"]["cm"]: rec["min"]=fish_obj
    if rec["max"] is None or fish_obj["cm"]>rec["max"]["cm"]: rec["max"]=fish_obj

# -----------------------------
# 확률 계산 (보정치 절반 적용)
# -----------------------------
def calc_prob(seconds:int,u)->dict:
    sec = min(seconds,60)
    base = {"소형":0.30,"중형":0.005,"대형":0.000025}
    base["소형"] += 0.10 * (sec/60) * 0.5
    base["중형"] += 0.01 * (sec/60) * 0.5
    base["대형"] += 0.00005 * (sec/60) * 0.5
    if u.get("additive_uses",0) > 0:
        base["중형"] += 0.02
        base["대형"] += 0.00005
    total=sum(base.values())
    base["실패"]=max(0.0,1.0-total)
    return base

# -----------------------------
# 낚시/릴감기
# -----------------------------
def handle_cast(u, seconds:int):
    if u.get("casting"):
        return "⚠️ 이미 캐스팅 중입니다. 현재 낚시가 끝날 때까지 기다려주세요."
    ok,bait_msg=ensure_bait_and_consume(u)
    if not ok: return bait_msg
    sec=max(1,min(60,int(seconds)))
    u["casting"]={"seconds":sec,"start":datetime.now().isoformat()}
    def auto_reel():
        if u.get("casting"):
            result=handle_reel(u)
            u["last_result"]="뭔가가 걸렸다 !!\n"+result
    Timer(sec,auto_reel).start()
    return f"{bait_msg}\n⏳ {sec}초 캐스팅 시작! 시간이 끝나면 자동으로 결과가 전송됩니다."

def handle_reel(u):
    if not u.get("casting"):
        return "⚠️ 캐스팅 기록이 없습니다."
    seconds=u["casting"]["seconds"]
    prob=calc_prob(seconds,u)
    roll=random.random()
    outcome="실패"; cum=0.0
    for k,v in prob.items():
        cum+=v
        if roll<=cum: outcome=k; break
    u["casting"]=None
    msg_lines=[]

    if outcome=="실패":
        msg_lines.append("🎣 낚시 실패... 다시 도전해 보세요!")
    else:
        msg_lines.append(f"🎣 {outcome} 어종을 낚았습니다!")

    loc=u.get("location")
    if loc=="바다":
        remain=u["inventory"].get("지렁이",0)
        msg_lines.append(f"남은 지렁이: {remain}개")
    elif loc=="민물":
        remain=u["inventory"].get("떡밥",0)
        msg_lines.append(f"남은 떡밥: {remain}개")

    return "\n".join(msg_lines)

# -----------------------------
# 라우팅
# -----------------------------
@app.get("/")
def health():
    return "OK",200

@app.route("/skill",methods=["GET","POST"],strict_slashes=False)
@app.route("/skill/",methods=["GET","POST"],strict_slashes=False)
def skill():
    body=request.get_json(silent=True) or {}
    utter=(body.get("userRequest",{}).get("utterance") or "").strip()
    uid=body.get("userRequest",{}).get("user",{}).get("id") or "anonymous"
    store=load_store(); u=get_user(store,uid)
    if utter.startswith("/낚시"):
        text=handle_cast(u,utter.replace("/낚시","").replace("s","").strip() or 10)
    elif utter=="/릴감기":
        text=handle_reel(u)
    else:
        text=""
    save_store(store)
    return kakao_text(text or ""),200

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
