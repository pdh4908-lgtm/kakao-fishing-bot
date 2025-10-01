import pytz
from datetime import datetime
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
            "🎉 낚시 RPG에 오신 것을 환영합니다!\n\n"
            "🎣 게임을 시작하려면 먼저 닉네임을 설정해주세요.\n"
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
    # 기본 보상 = 길이(cm)
    exp = length
    gold = length

    # 장소 보정
    if user.get("place") == "바다":
        exp = int(exp * 0.5)
        gold = int(gold * 1.5)
    elif user.get("place") == "민물":
        exp = int(exp * 1.5)
        gold = int(gold * 0.5)

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
        "- 집어제 (1개) | 💰2,000   ※ 사용 시 3회 지속  ← 희귀어 노리는 강화용\n"
        "- 케미라이트3등급 (1개) | 💰200   ※ 사용 1회성, 20:00~05:00 ← 낚시 실패 방지용\n"
        "- 케미라이트2등급 (1개) | 💰350   ※ 사용 1회성, 20:00~05:00 ← 낚시 실패 방지용\n"
        "- 케미라이트1등급 (1개) | 💰1,000   ※ 사용 1회성, 20:00~05:00 ← 낚시 실패 방지용\n\n"
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
    user["limit_gold"] += 2000  # 최초 2000골드 → 제한골드로 지급
    return (
        f"✅ 닉네임 설정 완료: {user['nickname']}\n"
        f"보너스 2000골드(제한골드)가 지급되었습니다! (현재 제한골드: 💰{user['limit_gold']})\n\n"
        "👉 제한골드는 지렁이·떡밥 구매에만 사용할 수 있으며, 사용 시 일반 골드보다 우선 차감됩니다.
"
        "👉 이제 '/'를 입력해서 게임을 시작해보세요!"
    )"\n"👉 이제 '/'를 입력해서 게임을 시작해보세요!")

def check_in(user):
    tz = pytz.timezone("Asia/Seoul")
    today = datetime.now(tz).strftime("%Y-%m-%d")

    if user.get("last_checkin") == today:
        return "⚠️ 오늘은 이미 출석 보상을 받았습니다. 내일 다시 시도해주세요!"

    user["limit_gold"] += 100   # 출석 보상 → 제한골드
    user["last_checkin"] = today
    return (
        f"✅ 출석 보상으로 제한골드 100 획득! (현재 제한골드: 💰{user['limit_gold']})\n\n"
        "👉 제한골드는 지렁이·떡밥 구매에만 사용할 수 있으며, 사용 시 일반 골드보다 우선 차감됩니다."
    )

    user["gold"] += 100
    user["last_checkin"] = today
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

from flask import Response

HTML_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>카톡 낚시 RPG - 테스트</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Apple SD Gothic Neo,Noto Sans KR,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;line-height:1.5}
h1{font-size:20px}
textarea, input[type=text]{width:100%;padding:8px;font-size:16px}
pre{white-space:pre-wrap;background:#111;color:#eee;padding:12px;border-radius:8px}
.small{color:#666;font-size:13px}
button{padding:10px 14px;font-size:16px;cursor:pointer}
</style>
</head>
<body>
  <h1>카톡 낚시 RPG - 테스트 콘솔</h1>
  <form method="GET" action="/" id="f">
    <label>사용자 ID:</label>
    <input type="text" name="user" placeholder="예: tester1" value="tester1"/>
    <label>명령어 입력:</label>
    <input type="text" name="utter" placeholder='예: /, /닉네임 낚시왕, /장소 바다, /구매 지렁이 10개, /낚시 5초' autofocus/>
    <button type="submit">실행</button>
  </form>
  {RESULT}
  <p class="small">API로 사용하려면 <code>/skill</code> 엔드포인트에
  GET(쿼리) 또는 POST(JSON/form)로 <code>user</code>, <code>utter</code>를 전달하세요.</p>
</body>
</html>"""

@app.route("/", methods=["GET"])
def index():
    user_id = request.args.get("user")
    utter = request.args.get("utter")
    if utter:
        try:
            reply = handle_command(str(user_id or "guest"), utter)
        except Exception as e:
            reply = f"⚠️ 오류: {e}"
        # Render with result
        block = f"<h2>결과</h2><pre>{reply}</pre>"
        return Response(HTML_PAGE.format(RESULT=block), mimetype="text/html; charset=utf-8")
    # initial page
    return Response(HTML_PAGE.format(RESULT=""), mimetype="text/html; charset=utf-8")

@app.route("/skill", methods=["GET", "POST"])
def skill():
    try:
        user_id = None
        utter = None
        if request.method == "GET":
            user_id = request.args.get("user", "guest")
            utter = request.args.get("utter", "/")
        else:
            # Try JSON first
            data = request.get_json(force=True, silent=True) or {}
            user_id = str(data.get("user") or request.form.get("user") or request.args.get("user") or "guest")
            utter = data.get("utter") or request.form.get("utter") or request.args.get("utter") or "/"
        reply = handle_command(str(user_id), utter)
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    # Render/Gunicorn 환경에서는 gunicorn app:app 형태로 구동되므로,
    # 로컬 테스트 시에만 아래 실행.
    app.run(host="0.0.0.0", port=8000, debug=False)

def determine_size_category(length):
    if length <= 30:
        return "소형"
    elif length <= 80:
        return "중형"
    else:
        return "대형"


import asyncio

async def handle_fishing(user, seconds):
    # Step 1: Casting message immediately
    first_msg = f"🎣 캐스팅...! ...... {seconds}초 동안 기다려봅시다..."
    send_message(user, first_msg)

    # Step 2: Wait for given seconds
    await asyncio.sleep(seconds)

    # Deduct bait (example: check place for bait type)
    bait_name = "지렁이" if user.get("place") == "바다" else "떡밥"
    if user.get("bait", {}).get(bait_name, 0) > 0:
        user["bait"][bait_name] -= 1
    remaining = user.get("bait", {}).get(bait_name, 0)

    # Step 3: Hook message + result
    hook_msg = "뭔가 걸린 것 같다....!\n\n\n"

    # Example success/failure check (placeholder logic)
    import random
    if random.random() < 0.7:  # 70% success rate
        # simulate fish success result
        length = random.randint(5, 120)
        size_cat = determine_size_category(length)
        fish = get_fish_by_place_and_size(user.get("place"), size_cat)
        # dummy exp/gold values
        exp = length
        gold = length
        result_msg = f"🎣 낚시 성공! {fish} {length}cm ({size_cat}어종) | {bait_name}({remaining}개 남음)\n획득: 경험치 +{exp} | 골드 +{gold}"
    else:
        result_msg = f"🎣 낚시 실패... 물고기를 놓쳤습니다. | {bait_name}({remaining}개 남음)"

    send_message(user, hook_msg + result_msg)


def get_title(level):
    if level <= 40:
        return "🐟 낚린이"
    elif level <= 69:
        return "🎣 낚시인"
    elif level <= 99:
        return "🐠 프로낚시꾼"
    else:
        return "🐳 강태공"


def handle_attendance(user, current_time):
    title = get_title(user.get("level", 1))
    reward = 0
    if "last_attendance" in user and user["last_attendance"].date() == current_time.date():
        return f"⚠️ 오늘은 이미 출석 보상을 받았습니다. (서울표준시 기준 자정에 초기화됩니다)"
    if title == "🐟 낚린이":
        reward = 500
    elif title == "🎣 낚시인":
        reward = 2000
    elif title == "🐠 프로낚시꾼":
        reward = 5000
    elif title == "🐳 강태공":
        return f"⚠️ {title} 등급은 출석 보상을 받을 수 없습니다."
    if reward > 0:
        user["limit_gold"] = user.get("limit_gold", 0) + reward
        user["last_attendance"] = current_time
        return f"✅ 출석 완료! ({title} {user.get('nickname','')})\n제한골드 {reward}이 지급되었습니다."
    return "⚠️ 출석 보상을 지급할 수 없습니다."

# /초기화 명령어 추가

    
elif text.startswith("/초기화"):
    parts = text.split()
    if len(parts) >= 2:
        target_nick = parts[1]
        target_id = None
        for uid, pdata in list(players.items()):
            if pdata.get("nickname") == target_nick:
                target_id = uid
                break
        if target_id:
            if target_id == user_id:
                return KakaoResp.text("""""⚠️ 본인 닉네임은 직접 초기화할 수 없습니다.""""")
            else:
                del players[target_id]
                return KakaoResp.text(f"""""⚠️ 닉네임 '{}'의 데이터가 초기화되었습니다.\n새로 시작하려면 /닉네임 [이름] 으로 설정해주세요.".format(target_nick))
        else:
            return KakaoResp.text("⚠️ 닉네임 '{}'을(를) 가진 사용자를 찾을 수 없습니다.".format(target_nick))
    else:
        return KakaoResp.text("사용법: /초기화 [닉네임]""""")
