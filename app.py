from zoneinfo import ZoneInfo
from datetime import datetime
import os
import json
import random
import time
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ---------------- 사용자 데이터 ----------------
users = {}

# ---------------- 물고기 및 상점 데이터 ----------------
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
SHOP_PRICE = {
    "지렁이": 10, "떡밥": 10, "집어제": 2000,
    "케미라이트3등급": 200, "케미라이트2등급": 350, "케미라이트1등급": 1000,
    "철제 낚싯대": 5000, "강화 낚싯대": 20000, "프로 낚싯대": 100000, "레전드 낚싯대": 500000,
}

# ---------------- 핵심 헬퍼 함수 ----------------

def get_user(user_id):
    """사용자 ID로 유저 데이터를 가져오거나 새로 생성합니다."""
    if user_id not in users:
        users[user_id] = {
            "nickname": None, "gold": 0, "limit_gold": 0,
            "exp": 0, "level": 1, "bag": [], "max_slot": 5,
            # 미끼는 골드(거래불가)/일반골드 재고를 분리하여 관리
            "inventory": {
                "지렁이_normal": 0, "지렁이_limit": 0,
                "떡밥_normal": 0, "떡밥_limit": 0
            },
            "items": {"집어제": 0, "케미라이트1등급": 0, "케미라이트2등급": 0, "케미라이트3등급": 0},
            "record": [], "place": None, "last_checkin": None,
            # 캐스팅 상태: {"start": epoch, "wait": sec, "bait": "지렁이|떡밥", "place": "바다|민물"}
            "casting": None,
            "bulk_sell_pending": False,
            "pending_sell_index": None,
            "net": []
        }
    return users[user_id]

def get_title(level):
    """레벨에 맞는 칭호를 반환합니다."""
    if level <= 40: return "🐟 낚린이"
    elif level <= 69: return "🎣 낚시인"
    elif level <= 99: return "🐠 프로낚시꾼"
    else: return "🐳 강태공"

def get_exp_and_gold(size):
    """물고기 크기에 따른 기본 경험치와 골드를 반환합니다."""
    if size == "소형": return 5, 80
    elif size == "중형": return 15, 300
    elif size == "대형": return 50, 1000
    return 0, 0


def calc_sell_price(fish):
    length = fish["length"]
    size = fish["size"]
    place = fish["place"]

    # 크기 보정
    if size == "소형":
        base_price = length
    elif size == "중형":
        base_price = length * 100
    elif size == "대형":
        base_price = length * 1000
    else:
        base_price = length

    # 장소 보정
    if place == "바다":
        base_price = int(base_price * 1.5)
    elif place == "민물":
        base_price = int(base_price * 0.5)

    return base_price



def add_bait_with_limit(user, key, amount):
    """Add bait with a max cap of 50 per type. Returns actual added quantity."""
    current = user["inventory"].get(key, 0)
    max_limit = 50
    if current >= max_limit:
        return 0
    can_add = min(amount, max_limit - current)
    user["inventory"][key] = current + can_add
    return can_add


def parse_amount(txt):
    """'10개', '5' 등 텍스트에서 숫자만 추출합니다."""
    num_str = "".join(filter(str.isdigit, txt))
    return int(num_str) if num_str else 0

# ---------------- UI 텍스트 생성 함수 ----------------



def bag_text(user):
    used = len(user["bag"])
    max_slot = user["max_slot"]
    lines = [f"[가방] {used}/{max_slot}칸 사용"]

    for i in range(max_slot):
        if i < len(user["bag"]):
            item = user["bag"][i]
            if item.get("name") == "어망":
                lines.append(f"{i+1}. 🪣 어망 (현재 {len(user['net'])}/20)")
            elif item.get("length") is not None:
                lines.append(f"{i+1}. {item['name']} {item['length']}cm ({item.get('size','-')}, {item.get('place','-')})")
            else:
                lines.append(f"{i+1}. {item.get('name','아이템')}")
        else:
            lines.append(f"{i+1}. 비어있음")

    return "
".join(lines)    


def owned_items_summary(user):
    """보유 아이템 요약 문자열을 생성합니다. 미끼는 일반/제한을 묶어서 표시."""
    parts = []
    # 미끼
    z_n = user['inventory'].get('지렁이_normal', 0)
    z_l = user['inventory'].get('지렁이_limit', 0)
    t_n = user['inventory'].get('떡밥_normal', 0)
    t_l = user['inventory'].get('떡밥_limit', 0)
    if z_n + z_l > 0:
        parts.append(f"지렁이(일반 {z_n} / 거래불가 {z_l})")
    if t_n + t_l > 0:
        parts.append(f"떡밥(일반 {t_n} / 거래불가 {t_l})")
    # 기타 아이템
    for item, count in user['items'].items():
        if count > 0:
            parts.append(f"{item}({count}개)")
    return "보유 아이템: " + ", ".join(parts) if parts else "보유 아이템이 없습니다."


def home_text(user):
    """초기 화면(홈) 텍스트"""
    if user["nickname"] is None:
        return (
            "🎉 낚시 RPG에 오신 것을 환영합니다!

"
            "🎣 게임을 시작하려면 먼저 닉네임을 설정해주세요.
"
            "예시) /닉네임 홍길동

"
            "닉네임은 한 번만 설정 가능하며 이후 변경할 수 없습니다."
        )

    inventory_status = owned_items_summary(user)
    casting_line = ""
    if user.get("casting"):
        elapsed = int(time.time() - user["casting"]["start"])
        remain = max(0, user["casting"]["wait"] - elapsed)
        casting_line = f"
🎯 진행 중: 캐스팅 {user['casting']['wait']}초 (남은 {remain}초) → /챔질"

    return (
        "🎣 낚시 RPG 사용법
"
        "1) /장소 [바다|민물] ← 먼저 장소를 설정하세요
"
        "2) /낚시 [1~60]초 ← 해당 초 만큼 캐스팅
"
        "3) (시간이 지나면) /챔질 ← 결과 확인

"
        "4) /도움말 → 전체 명령어 안내

"
        f"닉네임: [{get_title(user['level'])}] {user['nickname']}
"
        "[상태]
"
        f"Lv.{user['level']}  Exp: {user['exp']}/100
"
        f"Gold: 💰{user['gold']} | 골드(거래불가): 💰{user['limit_gold']}
"
        "착용 낚싯대: 철제 낚싯대

"
        f"{bag_text(user)}

"
        f"{inventory_status}"
        f"{casting_line}"
    )

    inventory_status = owned_items_summary(user)

    casting_line = ""
    if user.get("casting"):
        elapsed = int(time.time() - user["casting"]["start"])
        remain = max(0, user["casting"]["wait"] - elapsed)
        casting_line = f"
🎯 진행 중: 캐스팅 {user['casting']['wait']}초 (남은 {remain}초) → /챔질"

    return (
        "🎣 낚시 RPG 사용법                                              /도움말
"
        "1) /장소 [바다|민물] ← 먼저 장소를 설정하세요
"
        "2) /낚시 [1~60]초 ← 해당 초 만큼 캐스팅
"
        "3) (시간이 지나면) /챔질 ← 결과 확인
"
        "4) /기록 → 물고기 기록 보기!
"
        "5) /칭호 → Lv. 칭호구간

"
        "🏪 상점 이용 방법
"
        "/상점 → 상점 목록 보기
"
        "/구매 [이름] [갯수] → 예: /구매 지렁이 10
"
        "/판매 [이름] [수량] → 되팔기 (구매가의 50%)

"
        "(기타)
"
        "/출석 → 출석 보상 받기
"
        "/가방, /상태

"
        f"닉네임: [{get_title(user['level'])}] {user['nickname']}
"
        "[상태]
"
        f"Lv.{user['level']}  Exp: {user['exp']}/100
"
        f"Gold: 💰{user['gold']} | 골드(거래불가): 💰{user['limit_gold']}
"
        "착용 낚싯대: 철제 낚싯대

"
        f"{bag_text(user)}

"
        f"{inventory_status}"
        f"{casting_line}"
    )

            "🎉 낚시 RPG에 오신 것을 환영합니다!\n\n"
            "🎣 게임을 시작하려면 먼저 닉네임을 설정해주세요.\n"
            "예시) /닉네임 홍길동\n\n"
            "닉네임은 한 번만 설정 가능하며 이후 변경할 수 없습니다."
        )
    
    inventory_status = owned_items_summary(user)

    casting_line = ""
    if user.get("casting"):
        elapsed = int(time.time() - user["casting"]["start"])
        remain = max(0, user["casting"]["wait"] - elapsed)
        casting_line = f"\n🎯 진행 중: 캐스팅 {user['casting']['wait']}초 (남은 {remain}초) → /챔질"

    return (
        "🎣 낚시 RPG 사용법\n"
        "1) /장소 [바다|민물] ← 먼저 장소를 설정하세요\n"
        "2) /낚시 [1~60]초 ← 해당 초 만큼 캐스팅\n"
        "3) (시간이 지나면) /챔질 ← 결과 확인\n"
        "4) /기록 → 물고기 기록 보기!\n"\
    "5) /칭호 → Lv. 칭호구간\n\n"
        "🏪 상점 이용 방법\n"
        "/상점 → 상점 목록 보기\n"
        "/구매 [이름] [갯수] → 예: /구매 지렁이 10\n"
        "/판매 [이름] [수량] → 되팔기 (구매가의 50%)\n\n"
        "(기타)\n"
        "/출석 → 출석 보상 받기\n"
        "/가방, /상태\n\n"
        f"닉네임: [{get_title(user['level'])}] {user['nickname']}\n"
        "[상태]\n"
        f"Lv.{user['level']}  Exp: {user['exp']}/100\n"
        f"Gold: 💰{user['gold']} | 골드(거래불가): 💰{user['limit_gold']}\n"
        "착용 낚싯대: 철제 낚싯대\n\n"
        f"{bag_text(user)}\n\n"
        f"{inventory_status}"
        f"{casting_line}"
    )



def help_text():
    return (
        "📖 [도움말 - 모든 명령어 안내]

"
        "🎣 낚시 RPG 사용법
"
        "1) /장소 [바다|민물] → 낚시 장소 설정
"
        "2) /낚시 [1~60]초 → 캐스팅
"
        "3) /챔질 → 결과 확인
"
        "4) /도움말 → 전체 명령어 안내

"
        "🏁 시작/프로필
"
        "/닉네임 [이름] → 최초 1회 닉네임 설정 (보너스 2000골드(거래불가))
"
        "/상태 → 현재 칭호/레벨/골드/장비/가방 보기
"
        "/칭호 → 레벨별 칭호 구간 안내
"
        "/기록 → 잡은 물고기 기록 확인

"
        "🎣 낚시 진행
"
        "/어망 → 어망 속 물고기 목록 보기

"
        "🏪 상점/거래
"
        "/상점 → 상점 열기
"
        "/구매 [아이템] [수량] → 아이템 구매 (지렁이/떡밥은 골드(거래불가) 우선 결제)
"
        "/판매 [이름] [수량] → 재화 판매
"
        "/판매 가방 [번호] → 해당 슬롯 물고기 판매 (예/아니오 확인)
"
        "/일괄판매 → 가방·어망 모든 물고기 판매 (네/아니오 확인, 어망 보유 시 주의 문구 표시)

"
        "🎁 기타
"
        "/출석 → 등급별 골드(거래불가) 보상 수령
"
        "/초기화 [닉네임] → 해당 닉네임 데이터 삭제 (관리용)
"
        "/홈 또는 / → 홈 화면 보기
"
    )


def shop_text():
    """상점 UI 텍스트를 반환합니다."""
    return """🏪 상점

[소모품]
- 지렁이 (1개) | 💰10  ← 골드(거래불가) 사용 가능 (바다낚시 전용)
- 떡밥   (1개) | 💰10  ← 골드(거래불가) 사용 가능 (민물낚시 전용)
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

판매: /판매 [이름] [수량]  (구매가의 50%)
일괄판매: /일괄판매   (모든 물고기 일괄판매)
"""

def record_text(user):
    """잡은 물고기 기록을 텍스트로 만듭니다."""
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

def bait_keys(bait_type):
    """미끼 이름으로 normal/limit 키를 반환"""
    return f"{bait_type}_normal", f"{bait_type}_limit"

def bait_total(user, bait_type):
    """총 미끼 수량(일반+제한)"""
    k_n, k_l = bait_keys(bait_type)
    return user["inventory"].get(k_n, 0) + user["inventory"].get(k_l, 0)

def consume_bait(user, bait_type, prefer="limit_first"):
    """캐스팅 시 미끼 1개 차감. 기본은 골드(거래불가) 물량을 우선 사용."""
    k_n, k_l = bait_keys(bait_type)
    if prefer == "limit_first":
        if user["inventory"][k_l] > 0:
            user["inventory"][k_l] -= 1
            return "limit"
        elif user["inventory"][k_n] > 0:
            user["inventory"][k_n] -= 1
            return "normal"
    else:
        if user["inventory"][k_n] > 0:
            user["inventory"][k_n] -= 1
            return "normal"
        elif user["inventory"][k_l] > 0:
            user["inventory"][k_l] -= 1
            return "limit"
    return None

def resolve_fishing_result(user, place, bait_type):
    """캐스팅 이후 /챔질 시점에 결과를 계산합니다."""
    if not place:
        return "⚠️ 먼저 장소를 설정해주세요. (/장소 바다 or /장소 민물)"
    if len(user["bag"]) >= user["max_slot"]:
        return f"⚠️ 가방이 가득 찼습니다. ({len(user['bag'])}/{user['max_slot']}칸)\n\n" + bag_text(user)

    # 물고기 크기 결정
    roll = random.random()
    if roll < 0.6: size = "소형"
    elif roll < 0.9: size = "중형"
    else: size = "대형"

    fish_info = random.choice(FISH_POOL[place][size])
    fish_name, min_len, max_len = fish_info
    length = random.randint(min_len, max_len)
    
    exp, gold = get_exp_and_gold(size)

    # 장소 보정
    if place == "바다":
        exp = int(exp * 0.5); gold = int(gold * 1.5)
    elif place == "민물":
        exp = int(exp * 1.5); gold = int(gold * 0.5)

    user["exp"] += exp
    user["gold"] += gold

    # 미끼 잔량(일반/제한) 표시값
    k_n, k_l = bait_keys(bait_type)
    normal_left = user["inventory"].get(k_n, 0)
    limit_left = user["inventory"].get(k_l, 0)
    
    fish_obj = {
        "name": fish_name, "length": length, "size": size,
        "place": place, "time": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
    }
    user["bag"].append(fish_obj)
    user["record"].append(fish_obj)

    msg = [
        f"뭔가.... 걸린..것 ...같다!",
        "",
        "",
        "",
        f"🎣 낚시 성공! {fish_name} {length}cm ({size}어종)",
        f"| {bait_type}(골드(거래불가) {limit_left}개 남음)",
        f"| {bait_type}(일반골드 {normal_left}개 남음)",
        f"획득: 💰{gold} Gold | ✨+{exp} Exp | 장소: {place}",
        "\n" + bag_text(user)
    ]
    return "\n".join(msg)

# ---------------- 상점/판매/출석 등 ----------------



def handle_buy(user, name, amount_txt):
    """구매 로직을 처리합니다. 지렁이/떡밥은 골드(거래불가)→일반골드 순서로 충전."""
    if name not in SHOP_PRICE:
        return "⚠️ 상점에 없는 품목입니다. '/상점'으로 목록을 확인하세요."
    
    amount = parse_amount(amount_txt)
    if amount <= 0: return "⚠️ 구매 수량을 올바르게 입력하세요. 예) /구매 지렁이 10"

    unit = SHOP_PRICE[name]
    total_price = unit * amount

    used_limit = 0
    # 미끼일 때만 골드(거래불가) 사용
    is_bait = name in ("지렁이", "떡밥")
    if is_bait:
        # 골드(거래불가)로 커버 가능한 수량
        max_by_limit = min(amount, user["limit_gold"] // unit)
        if max_by_limit > 0:
            used_limit = max_by_limit * unit
            user["limit_gold"] -= used_limit
            # 제한 재고 추가
            k_n, k_l = bait_keys(name)
            added = add_bait_with_limit(user, k_l, max_by_limit)
            if added < max_by_limit:
                return f"⚠️ {name}(판매불가)은 최대 50개까지 보유 가능합니다. {max_by_limit - added}개는 구매되지 않았습니다."
        # 남은 수량은 일반골드 결제
        remain_cnt = amount - (used_limit // unit)
        price_normal = remain_cnt * unit
        if price_normal > 0:
            if user["gold"] < price_normal:
                return f"⚠️ 골드가 부족합니다. (부족한 골드: {price_normal - user['gold']})"
            user["gold"] -= price_normal
            k_n, k_l = bait_keys(name)
            added = add_bait_with_limit(user, k_n, remain_cnt)
            if added < remain_cnt:
                return f"⚠️ {name}(일반)은 최대 50개까지 보유 가능합니다. {remain_cnt - added}개는 구매되지 않았습니다."
    else:
        # 일반 아이템
        if user["gold"] < total_price:
            return f"⚠️ 골드가 부족합니다. (부족한 골드: {total_price - user['gold']})"
        user["gold"] -= total_price
        if name in user["items"]:
            user["items"][name] += amount

    txt_limit = f" (골드(거래불가) {used_limit} 사용)" if used_limit else ""
    # 잔량 안내(미끼만)
    extra = ""
    if is_bait:
        k_n, k_l = bait_keys(name)
        extra = f"\n보유 {name}: 일반 {user['inventory'][k_n]} / 제한 {user['inventory'][k_l]}"
    return f"✅ 구매 완료: {name} x{amount}{txt_limit}\n남은 Gold: 💰{user['gold']}{extra}"

def handle_sell(user, name, amount_txt):
    """판매 로직을 처리합니다. 미끼는 일반→제한 순서로 차감하여 판매."""
    amount = parse_amount(amount_txt)
    if amount <= 0: return "⚠️ 판매 수량을 올바르게 입력하세요."

    if name in ("지렁이", "떡밥"):
        k_n, k_l = bait_keys(name)
        have = user["inventory"].get(k_n, 0) + user["inventory"].get(k_l, 0)
        if have < amount: return "⚠️ 보유 수량이 부족합니다."
        # 일반 먼저 차감, 부족분을 제한에서
        use_n = min(user["inventory"][k_n], amount)
        user["inventory"][k_n] -= use_n
        remain = amount - use_n
        if remain > 0:
            user["inventory"][k_l] -= remain
    elif name in user["items"]:
        if user["items"][name] < amount: return "⚠️ 보유 수량이 부족합니다."
        user["items"][name] -= amount
    else:
        return "⚠️ 판매 불가 품목입니다."

    if name not in SHOP_PRICE: return "⚠️ 가격 정보가 없는 품목입니다."

    earn = SHOP_PRICE[name] * amount // 2
    user["gold"] += earn
    return f"✅ 판매 완료: {name} x{amount} → 💰{earn}\n현재 Gold: 💰{user['gold']}"

def check_in(user):
    """출석 보상 로직을 처리합니다."""
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
        return f"✅ 출석 완료! ({title}) 골드(거래불가) {reward}이 지급되었습니다.\n(현재 골드(거래불가): {user['limit_gold']})"
    
    return "⚠️ 출석 보상을 지급할 수 없습니다."

def set_place(user, place_txt):
    """장소 설정 로직을 처리합니다."""
    place = place_txt.strip()
    if place not in ("바다", "민물"):
        return "⚠️ 장소는 '바다' 또는 '민물'만 가능합니다."
    user["place"] = place
    return f"🌊 낚시 장소가 [{place}]로 설정되었습니다."

def set_nickname(user, nick):
    """닉네임 설정 로직을 처리합니다."""
    if user["nickname"]:
        return "⚠️ 닉네임은 이미 설정되어 있어 변경할 수 없습니다."
    
    user["nickname"] = nick.strip()
    user["limit_gold"] += 2000
    return (
        f"✅ 닉네임 설정 완료: {user['nickname']}\n"
        f"보너스 2000골드(거래불가)가 지급되었습니다!\n\n"
        "👉 이제 '/도움말' 또는 '/'를 입력해서 게임을 시작해보세요!"
    )

# ---------------- 메인 명령어 핸들러 ----------------

def handle_command(user_id, utter):
    """입력된 명령어를 분석하고 적절한 함수를 호출합니다."""
    user = get_user(user_id)

    # 개별 판매 확인 단계 처리
    # 개별 판매 확인 단계 처리
    if user.get("pending_sell_index") is not None:
        if utter.strip() == "예":
            idx = user["pending_sell_index"]
            if idx >= len(user["bag"]):
                user["pending_sell_index"] = None
                return "⚠️ 해당 슬롯에 물고기가 없습니다."
            fish = user["bag"].pop(idx)
            price = calc_sell_price(fish)
            user["gold"] += price
            user["pending_sell_index"] = None
            return f"✅ 판매 완료: {fish['name']} {fish['length']}cm → 💰{price}\n현재 Gold: 💰{user['gold']}"
        elif utter.strip() == "아니오":
            user["pending_sell_index"] = None
            return "❌ 판매가 취소되었습니다."

    # 일괄판매 확인 단계 처리
    if user.get("bulk_sell_pending"):
        if utter.strip() == "네":
            sold_count = len(user["bag"]) + len(user["net"])
            total_gold = sum(calc_sell_price(fish) for fish in user["bag"])
            total_gold += sum(calc_sell_price(fish) for fish in user["net"])
            user["gold"] += total_gold
            user["bag"].clear()
            user["net"].clear()
            user["bulk_sell_pending"] = False
            return f"✅ 모든 물고기 {sold_count}마리를 판매했습니다.\n획득 Gold: 💰{total_gold}\n현재 Gold: 💰{user['gold']}"
        elif utter.strip() == "아니오":
            user["bulk_sell_pending"] = False
            return "❌ 일괄판매가 취소되었습니다."

    parts = utter.strip().split()
    command = parts[0]

    if command in ("/", "/홈"):
        return home_text(user)

    if command == "/마스터":
        return handle_master(user, parts)

    if command == "/도움말":
        return help_text()

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
    
    if command == "/일괄판매":
        if not user["bag"] and not user["net"]:
            return "⚠️ 판매할 물고기가 없습니다."
        
        user["bulk_sell_pending"] = True
        lines = ["📦 가방에 있는 물고기 목록"]
        for i, fish in enumerate(user["bag"], start=1):
            lines.append(f"{i}. {fish['name']} {fish['length']}cm ({fish['size']}어종, {fish['place']})")
        
        if any(item.get("name") == "어망" for item in user["bag"]):
            lines.append("⚠️ 주의! 어망에 있는 물고기도 일괄 판매됩니다.")
        
        lines.append("\n모든 물고기를 일괄판매 하시겠습니까? (네/아니오)")
        return "\n".join(lines)

    if command == "/판매":
        if len(parts) >= 3 and parts[1] == "가방":
            try:
                idx = int(parts[2]) - 1
                if idx < 0 or idx >= len(user["bag"]):
                    return "⚠️ 해당 슬롯에 물고기가 없습니다."
                fish = user["bag"][idx]
                user["pending_sell_index"] = idx
                return f"📦 선택한 물고기: {fish['name']} {fish['length']}cm ({fish['size']}어종, {fish['place']})\n정말로 판매하시겠습니까? (예/아니오)"
            except ValueError:
                return "⚠️ 숫자를 입력해주세요. 예) /판매 가방 2"
        if len(parts) < 3:
            return "사용법: /판매 [이름] [수량]"
        return handle_sell(user, parts[1], parts[2])
    if command == "/출석":
        return check_in(user)
    if command == "/가방":
        return bag_text(user)
    if command == "/기록":
        return record_text(user)
    if command == "/상태":
        return (
            f"[{get_title(user['level'])}] {user['nickname']}
"
            f"Lv.{user['level']}  Exp: {user['exp']}/100
"
            f"Gold: 💰{user['gold']} | 골드(거래불가): 💰{user['limit_gold']}
"
            f"착용 낚싯대: 철제 낚싯대

{bag_text(user)}"
        )

        if command == "/어망":
        if not user["net"]:
            return "🪣 어망이 비어있습니다."
        lines = [f"🪣 어망 ({len(user['net'])}/20)"]
        for i, fish in enumerate(user["net"], start=1):
            lines.append(f"{i}. {fish['name']} {fish['length']}cm ({fish['size']}어종, {fish['place']})")
        return "\n".join(lines)

    if command == "/칭호":
        return (
            "📜 칭호 구간 안내\n\n"
            "Lv. 1 ~ 40  → 🐟 낚린이\n"
            "Lv. 41 ~ 69 → 🎣 낚시인\n"
            "Lv. 70 ~ 99 → 🐠 프로낚시꾼\n"
            "Lv. 100 이상 → 🐳 강태공"
        )

        return (
            f"[{get_title(user['level'])}] {user['nickname']}\n"
            f"Lv.{user['level']}  Exp: {user['exp']}/100\n"
            f"Gold: 💰{user['gold']} | 골드(거래불가): 💰{user['limit_gold']}\n"
            f"착용 낚싯대: 철제 낚싯대\n\n{bag_text(user)}"
        )
    if command == "/낚시":
        if len(parts) < 2: return "사용법: /낚시 [1~60]초"
        sec = parse_amount(parts[1])
        if not 1 <= sec <= 60: return "⚠️ 1~60초 사이로 입력해주세요."
        if not user.get("place"):
            return "⚠️ 먼저 장소를 설정해주세요. (/장소 바다 or /장소 민물)"
        if len(user["bag"]) >= user["max_slot"]:
            return f"⚠️ 가방이 가득 찼습니다. ({len(user['bag'])}/{user['max_slot']}칸)\n\n" + bag_text(user)
        if user.get("casting"):
            elapsed = int(time.time() - user["casting"]["start"])
            remain = max(0, user["casting"]["wait"] - elapsed)
            return f"⚠️ 이미 캐스팅 중입니다! 남은 {remain}초 후 /챔질 하세요."
        bait_type = "지렁이" if user["place"] == "바다" else "떡밥"
        if bait_total(user, bait_type) <= 0:
            return f"⚠️ {bait_type}가 부족합니다. 상점에서 구매해주세요."
        # 캐스팅 시점에 미끼 1개 차감 (제한 → 일반 우선 소진)
        consumed_from = consume_bait(user, bait_type, prefer="limit_first")
        user["casting"] = {"start": time.time(), "wait": sec, "bait": bait_type, "place": user["place"]}
        return f"🎣 캐스팅...! {sec}초 후에 /챔질 하세요."
    if command == "/챔질":
        cast = user.get("casting")
        if not cast:
            return "⚠️ 먼저 /낚시로 캐스팅부터 해주세요."
        elapsed = time.time() - cast["start"]
        wait = cast["wait"]
        if elapsed < wait:
            remain = int(wait - elapsed)
            return f"⏳ 아직 챔질할 수 없습니다. 남은 시간: {remain}초"
        # 결과 계산
        user["casting"] = None
        return resolve_fishing_result(user, cast["place"], cast["bait"])
    if command == "/초기화":
        if len(parts) < 2: return "사용법: /초기화 [닉네임]"
        target_nick = parts[1]
        target_id_to_delete = None
        for uid, udata in users.items():
            if udata.get("nickname") == target_nick:
                target_id_to_delete = uid; break
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
"""

@app.route("/")
def index():
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
    app.run(host="0.0.0.0", port=8000, debug=True)





def handle_master(user, parts):
    if len(parts) < 4:
        return "사용법: /마스터 [닉네임] [항목] [값]"

    target_nick, field, value = parts[1], parts[2], parts[3]
    target_user = None
    for uid, udata in users.items():
        if udata.get("nickname") == target_nick:
            target_user = udata
            break
    if not target_user:
        return f"⚠️ 닉네임 '{target_nick}' 을(를) 찾을 수 없습니다."

    def parse_delta(val):
        if val.startswith(("+", "-")):
            return int(val), True
        return int(val), False

    # 레벨
    if field == "Lv":
        num, is_delta = parse_delta(value)
        if is_delta:
            target_user["level"] = max(1, target_user["level"] + num)
        else:
            target_user["level"] = num
        return f"✅ {target_nick}님의 레벨이 {target_user['level']} 으로 변경되었습니다."

    # 골드
    if field == "골드":
        num, is_delta = parse_delta(value)
        target_user["gold"] += num
        if target_user["gold"] < 0:
            target_user["gold"] = 0
        return f"✅ {target_nick}님의 골드가 {num:+} 되었습니다. (현재: {target_user['gold']})"

    # 경험치
    if field == "경험치":
        num, is_delta = parse_delta(value)
        target_user["exp"] += num
        if target_user["exp"] < 0:
            target_user["exp"] = 0
        return f"✅ {target_nick}님의 경험치가 {num:+} 되었습니다. (현재: {target_user['exp']})"

    # 장비
    if field == "장비":
        if value.startswith("+"):
            item = value[1:]
            target_user.setdefault("items", {})
            target_user["items"][item] = target_user["items"].get(item, 0) + 1
            return f"✅ {target_nick}님께 '{item}' 장비를 지급했습니다."
        elif value.startswith("-"):
            item = value[1:]
            if target_user.get("items", {}).get(item, 0) > 0:
                target_user["items"][item] -= 1
                return f"✅ {target_nick}님의 '{item}' 장비를 회수했습니다."
            return f"⚠️ {target_nick}님은 '{item}' 장비를 가지고 있지 않습니다."

    # 아이템
    if field == "아이템":
        if value.startswith("+"):
            item = value[1:]
            target_user.setdefault("items", {})
            target_user["items"][item] = target_user["items"].get(item, 0) + 1
            return f"✅ {target_nick}님께 '{item}' 아이템을 지급했습니다."
        elif value.startswith("-"):
            item = value[1:]
            if target_user.get("items", {}).get(item, 0) > 0:
                target_user["items"][item] -= 1
                return f"✅ {target_nick}님의 '{item}' 아이템을 회수했습니다."
            return f"⚠️ {target_nick}님은 '{item}' 아이템을 가지고 있지 않습니다."

    return "⚠️ 지원하지 않는 항목입니다."
