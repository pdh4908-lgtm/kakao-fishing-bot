import os
import json
import random
import time
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# ---------------- 사용자 데이터 ----------------
users = {}

def get_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "nickname": None,
            "gold": 0,
            "limit_gold": 0,
            "exp": 0,
            "level": 1,
            "bag": [],
            "max_slot": 5,
            "inventory": {
                "지렁이": 0,
                "떡밥": 0
            },
            "items": {
                "집어제": 0,
                "케미라이트1등급": 0,
                "케미라이트2등급": 0,
                "케미라이트3등급": 0
            },
            "record": [],
            "place": None
        }
    return users[user_id]

# ---------------- 물고기 데이터 ----------------
FISH_POOL = {
    "바다": {
        "소형": [("전어", 15, 30), ("멸치", 5, 10), ("정어리", 10, 25), ("고등어", 20, 40), ("청어", 20, 35)],
        "중형": [("방어", 40, 100), ("도미", 30, 60), ("삼치", 50, 100), ("참소라", 10, 20), ("오징어", 20, 40)],
        "대형": [("참치", 100, 300), ("상어", 200, 600), ("고래상어", 400, 1200), ("만새기", 100, 200), ("황새치", 150, 300)]
    },
    "민물": {
        "소형": [("붕어", 10, 30), ("피라미", 5, 15), ("미꾸라지", 5, 20), ("몰개", 5, 15), ("가재", 5, 10)],
        "중형": [("잉어", 40, 80), ("향어", 50, 90), ("메기", 40, 100), ("동자개", 20, 40), ("붕어왕", 30, 50)],
        "대형": [("철갑상어", 100, 300), ("쏘가리", 60, 100), ("민물가오리", 70, 150), ("대형메기", 100, 200), ("괴물잉어", 120, 250)]
    }
}
# ---------------- 경험치 및 보상 계산 ----------------
def get_exp_and_gold(size, length):
    if size == "소형":
        return 5, 80
    elif size == "중형":
        return 15, 300
    elif size == "대형":
        return 50, 1000
    return 0, 0

# ---------------- 가방 UI ----------------
def bag_text(user):
    lines = [f"[가방] {len(user['bag'])}/{user['max_slot']}칸 사용"]
    for i in range(user['max_slot']):
        if i < len(user['bag']):
            fish = user['bag'][i]
            lines.append(f"{i+1}. {fish['name']} ({fish['length']}cm, {fish['size']}어종)")
        else:
            lines.append(f"{i+1}. 비어있음")
    return "\n".join(lines)

# ---------------- 홈 UI ----------------
def home_text(user):
    if user["nickname"] is None:
        return (
            "🎣 닉네임을 설정해주세요.\n"
            "예시) /닉네임 홍길동\n\n"
            "닉네임은 한 번만 설정 가능하며 이후 변경할 수 없습니다."
        )
    msg = []
    msg.append("🎣 낚시 RPG 사용법")
    msg.append("1) /장소 [바다|민물] ← 먼저 장소를 설정하세요")
    msg.append("2) /낚시 [1~60]s 또는 /낚시 [1~60]초 ← 해당 초 만큼 캐스팅 (예: /낚시 15s, /낚시 10초)")
    msg.append("3) /기록 → 물고기 기록 보기!\n")
    msg.append("🏪 상점 이용 방법")
    msg.append("/상점 → 상점 목록 보기")
    msg.append("/구매 [이름] [갯수] → 예: /구매 지렁이 10개, /구매 케미라이트1등급 1개")
    msg.append("/아이템판매 [이름] [수량] → 되팔기 (구매가의 50%)\n")
    msg.append("(출석/보너스)")
    msg.append("/출석 → 출석 보상 받기\n")
    msg.append(f"닉네임: [낚린이] {user['nickname']}")
    msg.append("[상태]")
    msg.append(f"Lv.{user['level']}  Exp: {user['exp']}/100")
    msg.append(f"Gold: 💰{user['gold']} | 제한골드: 💰{user['limit_gold']}")
    msg.append("착용 낚싯대: 철제 낚싯대\n")
    msg.append(bag_text(user))
    msg.append("\n보유하지 않은 물품: 지렁이, 떡밥, 집어제, 케미라이트1등급, 케미라이트2등급, 케미라이트3등급")
    return "\n".join(msg)
# ---------------- 낚시 처리 ----------------
def handle_fishing(user, seconds):
    if user["place"] is None:
        return "⚠️ 먼저 장소를 설정해주세요. (/장소 바다 or /장소 민물)"

    bait_type = "지렁이" if user["place"] == "바다" else "떡밥"
    if user["inventory"][bait_type] <= 0:
        return f"⚠️ {bait_type}가 부족합니다. 상점에서 구매해주세요."

    if len(user["bag"]) >= user["max_slot"]:
        return f"⚠️ 가방이 가득 차 낚시를 진행할 수 없습니다. ({len(user['bag'])}/{user['max_slot']}칸)\n\n" + bag_text(user)

    # 미끼 차감
    user["inventory"][bait_type] -= 1

    # 캐스팅 알림
    msg = ["…뭔가 걸린 것 같다!!!"]
    time.sleep(seconds)

    # 확률 보정 (아이템, 시간 등 적용 가능하도록 구조만 남겨둠)
    roll = random.random()
    if roll < 0.6:
        size = "소형"
    elif roll < 0.9:
        size = "중형"
    else:
        size = "대형"

    fish = random.choice(FISH_POOL[user["place"]][size])
    length = random.randint(fish[1], fish[2])
    exp, gold = get_exp_and_gold(size, length)

    user["exp"] += exp
    user["gold"] += gold
    user["bag"].append({"name": fish[0], "length": length, "size": size})

    msg.append(f"\n🎣 낚시 성공! {fish[0]} {length}cm ({size}어종) | {bait_type}({user['inventory'][bait_type]}개 남음)")
    msg.append(f"가격: 💰{gold} | 경험치 +{exp} | 장소: {user['place']}")
    msg.append("\n" + bag_text(user))
    return "\n".join(msg)
# ---------------- 상점 UI ----------------
def shop_text():
    return (
        "🏪 상점\n\n"
        "[소모품]\n"
        "- 지렁이 (1개) | 💰10   ← 제한골드 사용 가능 (보유 한도 100개) (바다낚시 전용)\n"
        "- 떡밥   (1개) | 💰10   ← 제한골드 사용 가능 (보유 한도 100개) (민물낚시 전용)\n"
        "- 집어제 (1개) | 💰2,000   ※ 사용 시 3회 지속\n"
        "- 케미라이트3등급 (1개) | 💰200   ※ 사용 1회성, 20:00~05:00\n"
        "- 케미라이트2등급 (1개) | 💰350   ※ 사용 1회성, 20:00~05:00\n"
        "- 케미라이트1등급 (1개) | 💰1,000   ※ 사용 1회성, 20:00~05:00\n\n"
        "[장비] (낚싯대는 물고기 사이즈별 확률 보정이 적용됩니다)\n"
        "- 철제 낚싯대 | 💰5,000\n"
        "- 강화 낚싯대 | 💰20,000\n"
        "- 프로 낚싯대 | 💰100,000\n"
        "- 레전드 낚싯대 | 💰500,000\n\n"
        "구매: /구매 [이름] [갯수]\n"
        "예) /구매 지렁이 10개, /구매 케미라이트1등급 1개\n"
        "되팔기: /아이템판매 [이름] [수량]  (구매가의 50%)\n\n"
        "정책\n"
        "- 제한골드는 지렁이/떡밥에만 사용 (우선 차감)\n"
        "- 케미라이트: 밤(20:00~05:00)만 사용 가능\n"
        "- 집어제: 사용 시 3회 지속 효과"
    )

SHOP_PRICE = {
    "지렁이": 10,
    "떡밥": 10,
    "집어제": 2000,
    "케미라이트3등급": 200,
    "케미라이트2등급": 350,
    "케미라이트1등급": 1000,
    "철제 낚싯대": 5000,
    "강화 낚싯대": 20000,
    "프로 낚싯대": 100000,
    "레전드 낚싯대": 500000,
}

# ---------------- 파서/유틸 ----------------
def parse_amount(txt):
    # "10개", "3마리", "5" 등에서 숫자만 추출
    num = ""
    for ch in txt:
        if ch.isdigit():
            num += ch
    return int(num) if num else 0

def now_is_night():
    # 20:00~05:00 사이 여부
    hh = datetime.now().hour
    return hh >= 20 or hh <= 5

def add_record(user, fish_obj):
    user["record"].append(fish_obj)

def record_text(user):
    if not user["record"]:
        return "🎣 아직 잡은 물고기가 없습니다."
    # 최대/최소
    fishes = user["record"]
    max_f = max(fishes, key=lambda x: x["length"])
    min_f = min(fishes, key=lambda x: x["length"])

    msg = []
    msg.append("📒 기록")
    msg.append(f"최대: {max_f['name']} {max_f['length']}cm ({max_f['size']}어종) | 장소:{max_f.get('place','-')} | {max_f.get('time','')}")
    msg.append(f"최소: {min_f['name']} {min_f['length']}cm ({min_f['size']}어종) | 장소:{min_f.get('place','-')} | {min_f.get('time','')}")
    msg.append("")

    # 종류별 1마리(최대 길이 기준)
    species_map = {}
    for f in fishes:
        key = f["name"]
        if key not in species_map or f["length"] > species_map[key]["length"]:
            species_map[key] = f
    msg.append("종류별 기록 (각 1마리):")
    for name, f in sorted(species_map.items(), key=lambda x: x[0]):
        when = f.get("time", "")
        place = f.get("place", "-")
        msg.append(f"- {name} {f['length']}cm ({f['size']}어종) | 장소:{place} | {when}")
    return "\n".join(msg)
# ---------------- 구매/판매 ----------------
def handle_buy(user, name, amount_txt):
    if name not in SHOP_PRICE:
        return "⚠️ 상점에 없는 품목입니다. /상점 으로 목록을 확인하세요."
    amount = parse_amount(amount_txt)
    if amount <= 0:
        return "⚠️ 구매 수량을 올바르게 입력하세요. 예) /구매 지렁이 10개"

    price = SHOP_PRICE[name] * amount

    # 제한골드: 지렁이/떡밥만 우선 차감
    used_limit = 0
    if name in ("지렁이", "떡밥"):
        use = min(user["limit_gold"], price)
        user["limit_gold"] -= use
        price -= use
        used_limit = use

    if user["gold"] < price:
        return f"⚠️ 골드가 부족합니다. 필요: {price}골드"

    user["gold"] -= price

    # 인벤/아이템 반영
    if name in ("지렁이", "떡밥"):
        # 보유 한도 100개
        have = user["inventory"].get(name, 0)
        user["inventory"][name] = min(100, have + amount)
    elif name in ("집어제", "케미라이트1등급", "케미라이트2등급", "케미라이트3등급"):
        user["items"][name] = user["items"].get(name, 0) + amount
    else:
        # 장비는 여기선 단순 표기만(착용/능력치 생략)
        pass

    txt_limit = f" (제한골드 {used_limit} 사용)" if used_limit else ""
    return f"✅ 구매 완료: {name} x{amount}{txt_limit}\nGold: 💰{user['gold']} | 제한골드: 💰{user['limit_gold']}"

def handle_sell(user, name, amount_txt):
    amount = parse_amount(amount_txt)
    if amount <= 0:
        return "⚠️ 판매 수량을 올바르게 입력하세요. 예) /아이템판매 지렁이 10개"

    # 소모품/아이템만 되팔기 허용
    qty = 0
    if name in user["inventory"]:
        qty = user["inventory"][name]
        if qty < amount:
            return "⚠️ 보유 수량이 부족합니다."
        user["inventory"][name] -= amount
    elif name in user["items"]:
        qty = user["items"][name]
        if qty < amount:
            return "⚠️ 보유 수량이 부족합니다."
        user["items"][name] -= amount
    else:
        return "⚠️ 되팔기 불가 품목입니다."

    if name not in SHOP_PRICE:
        return "⚠️ 가격 정보가 없는 품목입니다."

    earn = SHOP_PRICE[name] * amount // 2
    user["gold"] += earn
    return f"✅ 판매 완료: {name} x{amount} → 💰{earn}\n현재 Gold: 💰{user['gold']}"

# ---------------- 장소/닉네임/출석 ----------------
def set_place(user, place_txt):
    place = place_txt.strip()
    if place not in ("바다", "민물"):
        return "⚠️ 장소는 '바다' 또는 '민물'만 가능합니다. 예) /장소 바다"
    user["place"] = place
    return f"🌊 낚시 장소가 [{place}]로 설정되었습니다."

def set_nickname(user, nick):
    if user["nickname"]:
        return "⚠️ 닉네임은 이미 설정되어 있어 변경할 수 없습니다."
    user["nickname"] = nick.strip()
    user["gold"] += 2000  # 최초 2000골드 지급
    return f"✅ 닉네임 설정 완료: {user['nickname']}\n보너스 2000골드가 지급되었습니다! (현재 Gold: 💰{user['gold']})"

def check_in(user):
    # 간단 출석 보상(예: 100골드)
    user["gold"] += 100
    return f"✅ 출석 보상으로 100골드 획득! (현재 Gold: 💰{user['gold']})"
# ---------------- 명령 처리 ----------------
def handle_command(user_id, utter):
    user = get_user(user_id)
    text = utter.strip()

    # 홈
    if text == "/" or text == "/도움말":
        return home_text(user)

    # 닉네임
    if text.startswith("/닉네임"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return "사용법: /닉네임 [이름]"
        return set_nickname(user, parts[1])

    # 장소
    if text.startswith("/장소"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return "사용법: /장소 [바다|민물]"
        return set_place(user, parts[1])

    # 상점
    if text == "/상점":
        return shop_text()

    # 구매
    if text.startswith("/구매"):
        parts = text.split()
        if len(parts) < 3:
            return "사용법: /구매 [이름] [갯수]\n예) /구매 지렁이 10개"
        name = parts[1]
        amount = parts[2]
        return handle_buy(user, name, amount)

    # 아이템 판매
    if text.startswith("/아이템판매"):
        parts = text.split()
        if len(parts) < 3:
            return "사용법: /아이템판매 [이름] [수량]"
        name = parts[1]
        amount = parts[2]
        return handle_sell(user, name, amount)

    # 출석
    if text == "/출석":
        return check_in(user)

    # 가방
    if text == "/가방":
        return bag_text(user)

    # 상태(간단)
    if text == "/상태":
        return (
            f"[상태]\n"
            f"Lv.{user['level']}  Exp: {user['exp']}/100\n"
            f"Gold: 💰{user['gold']} | 제한골드: 💰{user['limit_gold']}\n"
            f"착용 낚싯대: 철제 낚싯대\n\n" + bag_text(user)
        )

    # 기록
    if text == "/기록":
        return record_text(user)

    # 낚시 (/낚시 Ns 또는 /낚시 N초)
    if text.startswith("/낚시"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return "사용법: /낚시 [1~60]s 또는 /낚시 [1~60]초 (예: /낚시 10초)"
        sec_txt = parts[1].strip().lower()
        sec = 0
        if sec_txt.endswith("초") or sec_txt.endswith("s"):
            sec = parse_amount(sec_txt)
        else:
            # 순수 숫자만 준 경우
            try:
                sec = int(sec_txt)
            except:
                sec = 0
        if sec < 1 or sec > 60:
            return "⚠️ 1~60초 사이로 입력해주세요."
        return handle_fishing(user, sec)

    return "알 수 없는 명령어입니다. / 로 도움말을 확인하세요."
# ---------------- Flask 라우트 ----------------
@app.route("/", methods=["GET"])
def index():
    return "OK"

@app.route("/skill", methods=["POST"])
def skill():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_id = str(data.get("user", "guest"))
        utter = data.get("utter", "/")

        # 실제 게임 명령 처리
        reply = handle_command(user_id, utter)

        return jsonify({
            "ok": True,
            "reply": reply
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    # Render/Gunicorn 환경에서는 gunicorn app:app 형태로 구동되므로,
    # 로컬 테스트 시에만 아래 실행.
    app.run(host="0.0.0.0", port=8000, debug=False)
