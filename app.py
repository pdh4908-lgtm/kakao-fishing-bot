from zoneinfo import ZoneInfo
from datetime import datetime
import os
import json
import random
import time
from flask import Flask, request, jsonify, Response

def kakao_text_response(text):
    return jsonify({
        "version": "2.0",
        "template": {
            "outputs": [
                {"simpleText": {"text": text}}
            ]
        }
    })

app = Flask(__name__)

# ---------------- 사용자 데이터 ----------------
users = {}

# ---------------- 물고기 및 상점 데이터 ----------------
FISH_POOL = {
    "바다": {
        "소형": [
            ("전어", 15, 30),
            ("멸치", 5, 10),
            ("정어리", 10, 20),
            ("고등어", 20, 35),
            ("청어", 20, 30),
            ("꽁치", 20, 30),
            ("자리돔", 10, 20),
            ("전갱이", 15, 25),
            ("망둥어", 10, 20),
            ("까나리", 10, 15)
        ],
        "중형": [
            ("방어", 40, 100),
            ("도미", 30, 80),
            ("삼치", 50, 100),
            ("부시리", 60, 120),
            ("광어", 40, 80),
            ("농어", 50, 100),
            ("쥐치", 30, 60),
            ("가자미", 35, 70),
            ("우럭", 40, 80),
            ("노래미", 30, 60)
        ],
        "대형": [
            ("참치", 100, 300),
            ("상어", 200, 600),
            ("고래상어", 400, 1200),
            ("만새기", 150, 300),
            ("황새치", 180, 350)
        ]
    },
    "민물": {
        "소형": [
            ("붕어", 10, 25),
            ("피라미", 5, 15),
            ("미꾸라지", 5, 15),
            ("몰개", 10, 20),
            ("가재", 5, 10),
            ("버들치", 10, 20),
            ("각시붕어", 10, 15),
            ("쉬리", 10, 20),
            ("돌고기", 10, 20),
            ("금붕어", 10, 20)
        ],
        "중형": [
            ("잉어", 40, 80),
            ("향어", 40, 90),
            ("메기", 40, 100),
            ("동자개", 20, 50),
            ("강준치", 40, 80),
            ("쏘가리", 35, 70),
            ("블루길", 25, 50),
            ("배스", 30, 60),
            ("누치", 30, 70),
            ("붕어왕", 40, 80)
        ],
        "대형": [
            ("철갑상어", 100, 250),
            ("대형메기", 100, 200),
            ("괴물잉어", 120, 250),
            ("민물가오리", 120, 200),
            ("큰쏘가리", 100, 180)
        ]
    }
}

SHOP_PRICE = {
}

# ---------------- 핵심 헬퍼 함수 ----------------

def get_user(user_id):
    if user_id not in users:
        users[user_id] = {
        }
    return users[user_id]

def get_title(level):
    if level <= 40: return "🐟 낚린이"
    elif level <= 69: return "🎣 낚시인"
    elif level <= 99: return "🐠 프로낚시꾼"
    else: return "🐳 강태공"

def get_exp_and_gold(size):
    if size == "소형": return 5, 80
    elif size == "중형": return 15, 300
    elif size == "대형": return 50, 1000
    return 0, 0

def parse_amount(txt):
    num_str = "".join(filter(str.isdigit, txt))
    return int(num_str) if num_str else 0

# ---------------- UI 텍스트 생성 함수 ----------------

def bag_text(user):
    lines = [f"[가방] {len(user['bag'])}/{user['max_slot']}칸 사용"]
    for i in range(user['max_slot']):
        if i < len(user['bag']):
            fish = user['bag'][i]
            lines.append(f"{i+1}. {fish['name']} ({fish['length']}cm, {fish['size']}어종)")
        else:
            lines.append(f"{i+1}. 비어있음")
    return "\n".join(lines)

def home_text(user):
    if user["nickname"] is None:
        return (
            "🎉 낚시 RPG에 오신 것을 환영합니다!\n\n"
        )
    owned_items = []
    for item, count in user['inventory'].items():
        if count > 0: owned_items.append(f"{item}({count}개)")
    for item, count in user['items'].items():
        if count > 0: owned_items.append(f"{item}({count}개)")

    inventory_status = "보유 아이템: " + ", ".join(owned_items) if owned_items else "보유 아이템이 없습니다."

    return (
    "🎣 낚시 RPG 사용법\n"
)

def shop_text():
    return """🏪 상점

[소모품]
- 지렁이 (1개) | 💰10  ← 제한골드 사용 가능 (바다낚시 전용)
- 떡밥   (1개) | 💰10  ← 제한골드 사용 가능 (민물낚시 전용)
- 집어제 (1개) | 💰2,000  ※ 사용 시 3회 지속
- 케미라이트3등급 (1개) | 💰200  ※ 1회성, 밤(20:00~05:00) 낚시 실패 방지
- 케미라이트2등급 (1개) | 💰350  ※ 1회성, 밤(20:00~05:00) 낚시 실패 방지
- 케미라이트1등급 (1개) | 💰1,000  ※ 1회성, 밤(20:00~05:00) 낚시 실패 방지

[장비] (낚싯대는 물고기 사이즈별 확률 보정이 적용됩니다)
- 철제 낚싯대 | 💰5,000
- 강화 낚싯대 | 💰20,000
- 프로 낚싯대 | 💰100,000
- 레전드 낚싯대 | 💰500,000

구매: /구매 [이름] [갯수]
예) /구매 지렁이 10
...
판매: /판매 [이름] [수량]  (구매가의 50%)
"""
def record_text(user):
    if not user["record"]:
        return "🎣 아직 잡은 물고기가 없습니다."

    fishes = user["record"]
    max_f = max(fishes, key=lambda x: x["length"])
    min_f = min(fishes, key=lambda x: x["length"])

    msg = ["📒 기록"]
    msg.append(f"최대: {max_f['name']} {max_f['length']}cm ({max_f['size']}어종) | 장소:{max_f.get('place','-')} | {max_f.get('time','')}")
    msg.append(f"최소: {min_f['name']} {min_f['length']}cm ({min_f['size']}어종) | 장소:{min_f.get('place','-')} | {min_f.get('time','')}")
    msg.append("")

    species_map = {}
    for f in fishes:
        if f["name"] not in species_map or f["length"] > species_map[f["name"]]["length"]:
            species_map[f["name"]] = f

    msg.append("종류별 최대 기록:")
    for name, f in sorted(species_map.items()):
        msg.append(f"- {name} {f['length']}cm ({f['size']}어종) | 장소:{f.get('place', '-')} | {f.get('time', '')}")
    return "\n".join(msg)

# ---------------- 게임 로직 처리 함수 ----------------


def handle_fishing(user, seconds):
    now = time.time()

    # 이미 낚시 중인지 확인
    if user.get("fishing_until", 0) > now:
        remain = int(user["fishing_until"] - now)


    # 미끼 1개 소모
    if user["inventory"][limit_bait] > 0:
        user["inventory"][limit_bait] -= 1
    else:
        user["inventory"][bait_type] -= 1

    remain_bait = user["inventory"][bait_type] + user["inventory"][limit_bait]

    # 지정된 시간 대기
    import time as _t
    _t.sleep(seconds)

    roll = random.random()
    if roll < 0.8:  # 성공 80%
        if roll < 0.6: size = "소형"
        elif roll < 0.9: size = "중형"
        else: size = "대형"

        fish_name, min_len, max_len = random.choice(FISH_POOL[user["place"]][size])
        length = random.randint(min_len, max_len)
        exp, gold = get_exp_and_gold(size)

        if user["place"] == "바다":
            exp = int(exp * 0.5); gold = int(gold * 1.5)
        elif user["place"] == "민물":
            exp = int(exp * 1.5); gold = int(gold * 0.5)

        user["exp"] += exp
        user["gold"] += gold

        fish_obj = {"name": fish_name, "length": length, "size": size,
        user["bag"].append(fish_obj)
        user["record"].append(fish_obj)

        user["fishing_until"] = 0  # 종료


    else:
        user["fishing_until"] = 0  # 종료



def handle_buy(user, name, amount_txt):
    if name not in SHOP_PRICE:
        return "⚠️ 상점에 없는 품목입니다. '/상점'으로 목록을 확인하세요."

    amount = parse_amount(amount_txt)
    if amount <= 0: return "⚠️ 구매 수량을 올바르게 입력하세요. 예) /구매 지렁이 10"

    price = SHOP_PRICE[name] * amount

    used_limit = 0
    if name in ("지렁이", "떡밥"):
        use = min(user["limit_gold"], price)
        user["limit_gold"] -= use
        price -= use
        used_limit = use

    if user["gold"] < price:
    user["gold"] -= price

    if name in user["inventory"]: user["inventory"][name] += amount
    elif name in user["items"]: user["items"][name] += amount

    txt_limit = f" (제한골드 {used_limit} 사용)" if used_limit else ""

def handle_sell(user, name, amount_txt):
    amount = parse_amount(amount_txt)
    if amount <= 0: return "⚠️ 판매 수량을 올바르게 입력하세요."

    if name in user["inventory"]:
        if user["inventory"][name] < amount: return "⚠️ 보유 수량이 부족합니다."
        user["inventory"][name] -= amount
    elif name in user["items"]:
        if user["items"][name] < amount: return "⚠️ 보유 수량이 부족합니다."
        user["items"][name] -= amount
    else:
        return "⚠️ 판매 불가 품목입니다."

    if name not in SHOP_PRICE: return "⚠️ 가격 정보가 없는 품목입니다."

    earn = SHOP_PRICE[name] * amount // 2
    user["gold"] += earn

def check_in(user):
    today_str = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")

    if user.get("last_checkin") == today_str:
        return "⚠️ 오늘은 이미 출석 보상을 받았습니다."

    title = get_title(user.get("level", 1))
    reward = 0
    if title == "🐟 낚린이": reward = 500
    elif title == "🎣 낚시인": reward = 2000
    elif title == "🐠 프로낚시꾼": reward = 5000
    elif title == "🐳 강태공": return f"⚠️ {title} 등급은 출석 보상을 받을 수 없습니다."

    if reward > 0:
        user["limit_gold"] += reward
        user["last_checkin"] = today_str

    return "⚠️ 출석 보상을 지급할 수 없습니다."

def set_place(user, place_txt):
    place = place_txt.strip()
    if place not in ("바다", "민물"):
        return "⚠️ 장소는 '바다' 또는 '민물'만 가능합니다."
    user["place"] = place

def set_nickname(user, nick):
    if user["nickname"]:
        return "⚠️ 닉네임은 이미 설정되어 있어 변경할 수 없습니다."

    user["nickname"] = nick.strip()
    user["limit_gold"] += 2000
    return (
        f"✅ 닉네임 설정 완료: {user['nickname']}\n"

# ---------------- 메인 명령어 핸들러 ----------------

def handle_command(user_id, utter):
    user = get_user(user_id)
    parts = utter.strip().split()
    command = parts[0]

    if command in ("/", "/도움말", "/홈"):
        return home_text(user)

    if user["nickname"] is None and command != "/닉네임":
        return "⚠️ 먼저 /닉네임 [이름] 명령어로 닉네임을 설정해주세요."

    if command == "/닉네임":
        return set_nickname(user, " ".join(parts[1:])) if len(parts) > 1 else "사용법: /닉네임 [원하는 이름]"
    if command == "/장소":
        return set_place(user, parts[1]) if len(parts) > 1 else "사용법: /장소 [바다|민물]"
    if command == "/상점":
        return shop_text()
    if command == "/구매":
        if len(parts) < 3: return "사용법: /구매 [이름] [갯수]"
        return handle_buy(user, parts[1], parts[2])
    if command == "/판매":
        if len(parts) < 3: return "사용법: /판매 [이름] [수량]"
        return handle_sell(user, parts[1], parts[2])
    if command == "/출석":
        return check_in(user)
    if command == "/가방":
        return bag_text(user)
    if command == "/기록":
        return record_text(user)
    if command == "/상태":
        return (
            f"[{get_title(user['level'])}] {user['nickname']}\n"
            f"Lv.{user['level']}  Exp: {user['exp']}/100\n"
            f"Gold: 💰{user['gold']} | 제한골드: 💰{user['limit_gold']}\n"
            f"착용 낚싯대: 철제 낚싯대\n\n{bag_text(user)}"
        )

    return (
        f"[{get_title(user['level'])}] {user['nickname']}\n"
        f"Lv.{user['level']}  Exp: {user['exp']}/100\n"
        f"Gold: 💰{user['gold']} | 제한골드: 💰{user['limit_gold']}\n"
        f"착용 낚싯대: 철제 낚싯대\n\n{bag_text(user)}"
    )
    if command == "/낚시":
        if len(parts) < 2: return "사용법: /낚시 [1~60]초"
        sec = parse_amount(parts[1])
        if not 1 <= sec <= 60: return "⚠️ 1~60초 사이로 입력해주세요."
        return handle_fishing(user, sec)
    if command == "/초기화":
        if len(parts) < 2:
            return "사용법: /초기화 [닉네임]"

        target_nick = parts[1]
        target_id_to_delete = None

        for uid, udata in users.items():
            if udata.get("nickname") == target_nick:
                target_id_to_delete = uid
                break

        if target_id_to_delete:
            del users[target_id_to_delete]
            return f"✅ '{target_nick}' 님의 데이터가 초기화되었습니다."
        else:
            return f"⚠️ '{target_nick}' 닉네임을 찾을 수 없습니다."
    return "알 수 없는 명령어입니다. '/도움말'을 확인하세요."

# ---------------- Flask 웹서버 부분 ----------------

HTML_PAGE = """
<!doctype html><html lang="ko"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>낚시 RPG 테스트</title><style>body{font-family:sans-serif;max-width:720px;margin:20px auto;padding:0 16px;line-height:1.6}h1{font-size:20px}input[type=text]{width:100%;padding:8px;font-size:16px;box-sizing:border-box;margin-bottom:10px;}pre{white-space:pre-wrap;background:#f0f0f0;padding:12px;border-radius:8px}button{padding:10px 14px;font-size:16px;cursor:pointer}</style></head>
<body><h1>낚시 RPG - 테스트 콘솔</h1><form method="GET" action="/"><label>사용자 ID:</label><input type="text" name="user" placeholder="예: user1" value="user1"/><label>명령어 입력:</label><input type="text" name="utter" placeholder="예: /닉네임 낚시왕" autofocus/><button type="submit">실행</button></form>{RESULT}</body></html>

@app.route("/", methods=["GET", "HEAD"])
def index():
    if request.method == "HEAD":
        return "", 200
    user_id = request.args.get("user")
    utter = request.args.get("utter")
    result_html = ""
    if user_id and utter:
        try:
            reply = handle_command(user_id, utter)
        except Exception as e:
            reply = f"⚠️ 서버 오류 발생: {e}"
        result_html = f"<h2>결과</h2><pre>{reply}</pre>"
    return Response(HTML_PAGE.format(RESULT=result_html), mimetype="text/html; charset=utf-8")

@app.route("/skill", methods=["POST"])
def skill():
    try:
        data = request.get_json()
        user_id = data['userRequest']['user']['id']
        utter = data['userRequest']['utterance']
        reply_text = handle_command(user_id, utter)

        response = {"version": "2.0", "template": {"outputs": [{"simpleText": {"text": reply_text}}]}}
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)