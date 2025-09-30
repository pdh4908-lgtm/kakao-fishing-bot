# game.py
import os, json, random, threading, time
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

class KakaoResp:
    @staticmethod
    def text(text: str):
        return {
            "version":"2.0",
            "template":{"outputs":[{"simpleText":{"text": text}}]}
        }

    @staticmethod
    def multi_text(lines):
        outputs = [{"simpleText":{"text": s}} for s in lines]
        return {"version":"2.0","template":{"outputs": outputs}}

class Store:

def get_meta(self):
    with self._lock:
        db = self._read()
        if "meta" not in db:
            db["meta"] = {"access_enabled": False, "owner": None}
            self._write(db)
        return db["meta"]

def set_meta(self, meta:dict):
    with self._lock:
        db = self._read()
        db["meta"] = meta
        self._write(db)

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        if not os.path.exists(self.path):
            self._write({"users":{}, "meta":{"access_enabled": False, "owner": None}})

    def _read(self):
        try:
            with open(self.path,"r",encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"users":{}, "meta":{"access_enabled": False, "owner": None}}

    def _write(self, data):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp,"w",encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def load_user(self, uid: str):
        with self._lock:
            db = self._read()
            u = db["users"].get(uid)
            if not u:
                u = {
                    "nickname": None,
                    "nick_locked": False,
                    "lv": 1, "exp": 0,
                    "gold": 0,
                    "gold_restricted": 0,
                    "newbie_chance": {"date":"", "count":0},
                    "pending_sale": {},
                    "spot": "민물",
                    # 소지품
                    "inventory": {
                        "지렁이":0,"떡밥":0,"집어제":0,
                        "케미라이트1등급": 600,"케미라이트2등급": 350,"케미라이트3등급": 200
                    },
                    "bag": [],  # 물고기 보관
                    "additive_ready": False,   # (Deprecated)
                    "additive_uses": 0,   # 집어제 남은 횟수(3회 지속)"
                    "chem_ready": False, "chem_grade": 0,  # 케미라이트 사용 대기
                    "rod": "대나무 낚싯대",    # 현재 장착
                    "rods_owned": {"대나무 낚싯대": True},  # 보유 목록
                    "last_attend": 0
                }
                db["users"][uid] = u
                self._write(db)
            return u

    def save_user(self, uid: str, user: dict):
        with self._lock:
            db = self._read()
            db["users"][uid] = user
            self._write(db)

class FishingGame:
    def __init__(self, db_path="fishing.json"):
        self.store = Store(db_path)
        random.seed()

        # 상점 품목 (번호 고정)
        self.shop_items = [
            {"id":1,"name":"지렁이1마리","price":10,"desc":"바다낚시 소모품×1","give":{"지렁이":1}},
            {"id":2,"name":"지렁이5마리","price":50,"desc":"바다낚시 소모품×5","give":{"지렁이":5}},
            {"id":3,"name":"지렁이10마리","price":100,"desc":"바다낚시 소모품×10","give":{"지렁이":10}},
            {"id":4,"name":"떡밥1마리","price":10,"desc":"민물낚시 소모품×1","give":{"떡밥":1}},
            {"id":5,"name":"떡밥5마리","price":50,"desc":"민물낚시 소모품×5","give":{"떡밥":5}},
            {"id":6,"name":"떡밥10마리","price":100,"desc":"민물낚시 소모품×10","give":{"떡밥":10}},
            {"id":7,"name":"집어제","price":500,"desc":"다음 1회 성공확률 +5%p","give":{"집어제":1}},
            {"id":8,"name":"케미라이트1등급","price":600,"desc":"다음 1회 대형 +5%p (20:00~05:00 사용)","give":{"케미라이트1등급": 600}},
            {"id":9,"name":"케미라이트2등급","price":350,"desc":"다음 1회 중형 +3%p (20:00~05:00 사용)","give":{"케미라이트2등급": 350}},
            {"id":10,"name":"케미라이트3등급","price":200,"desc":"다음 1회 소형 +1%p (20:00~05:00 사용)","give":{"케미라이트3등급": 200}},
            # 낚시대
            {"id":11,"name":"철제 낚싯대","price":1000,"desc":"소형·중형 +2%p (대형 0)","rod":True},
            {"id":12,"name":"강화 낚싯대","price":5000,"desc":"소형·중형 +5%p (대형 0)","rod":True},
            {"id":13,"name":"프로 낚싯대","price":20000,"desc":"대형 +2%p, 소형 -5%p","rod":True},
            {"id":14,"name":"레전드 낚싯대","price":100000,"desc":"대형 +5%p, 소형 -20%p","rod":True},
        ]
self.required_bait = {"바다":"지렁이","민물":"떡밥"}
self.unit_price_map = {
    "지렁이": 10,
    "떡밥": 10,
    "집어제": 500,
    "케미라이트1등급": 600,
    "케미라이트2등급": 350,
    "케미라이트3등급": 200,
    "철제 낚싯대": 1000,
    "강화 낚싯대": 5000,
    "프로 낚싯대": 20000,
    "레전드 낚싯대": 100000,
}

        # 어종/사이즈 범위
        self.fish_catalog = {
            "바다":{
                "소형":[("전갱이",8,25),("정어리",10,20),("고등어",12,30),("전어",10,25),("학꽁치",15,35)],
                "중형":[("참돔",30,60),("우럭",30,55),("광어",35,65),("농어",40,80),("감성돔",25,55)],
                "대형":[("방어",60,120),("부시리",70,150),("삼치",70,120),("참다랑어",100,200),("민어",70,120)]
            },
            "민물":{
                "소형":[("피라미",6,15),("몰개",6,14),("버들치",5,12),("납자루",6,13),("참붕어",10,20)],
                "중형":[("붕어",20,35),("잉어",30,60),("향어",35,70),("꺽지",20,35),("동자개",18,30)],
                "대형":[("가물치",60,110),("메기",70,130),("민물장어",60,120),("강준치",50,90),("누치",40,70)]
            }
        }

    # ── 도움말/시작/닉네임 ─────────────────────────────────
    def help_text(self, extra:str=""):
        lines = [
            "🎣 낚시 RPG 사용법",
            "0) /시작 → /닉네임 [이름]   ← 최초 1회 설정(변경 불가)",
            "1) /장소 [바다|민물]   ← 먼저 장소를 설정하세요",
            "2) /낚시 [1~60]s      ← 해당 초 만큼 캐스팅 (예: /낚시 15s)",
            "3) 시간이 끝나면 /릴감기 로 결과 확인",
            "",
            "기타 명령어:",
            "/상태, /가방",
            "/상점, 구매 [번호], 판매 [번호], 전부판매",
            "/출석",
        ]
        if extra: lines.append(f"\n⚠️ {extra}")
        return "\n".join(lines)

    def cmd_start(self, uid:str):
        u = self.store.load_user(uid)
        if not u.get("nick_locked"):
            return "처음 오셨네요! 닉네임을 설정해 주세요. (닉네임은 이후 변경 불가)
예) /닉네임 낚시왕카카오"
        return "이미 닉네임이 설정되었습니다. 메뉴를 보려면 '/' 를 입력하세요."


    def cmd_set_nickname(self, uid:str, arg:str):
        name = arg if arg is not None else ""
        if not name or name.strip() == "":
            return "닉네임을 함께 입력해 주세요. 예) /닉네임 낚시왕카카오"
        if len(name) > 10:
            return "닉네임은 최대 10글자까지 가능합니다."
        u = self.store.load_user(uid)
        if u.get("nick_locked"):
            return KakaoResp.multi_text(["뭔가 걸린 것 같다....", f"닉네임은 이미 '{u.get('nickname')}' 로 설정되어 있어요. (변경 불가)"])
        u["nickname"] = name
        u["nick_locked"] = True
        self.store.save_user(uid, u)
        return f"닉네임이 '{name}'(으)로 설정되었습니다!\n\n" + self.help_text()

    # ── 칭호/레벨 보정 ────────────────────────────────────
    def title_by_level(self, lv:int)->str:
        if lv >= 100: return "프로"
        if lv >= 71: return "전문낚시인"
        if lv >= 31: return "낚시인"
        return "낚린이"

    def level_bonus(self, lv:int, grade:str)->float:
        # 모든등급 공통 보정은 소형만. 중형/대형은 등급별 보정만
        if lv >= 100:
            if grade == "소형": return 10.0
            if grade == "중형": return 15.0
            if grade == "대형": return 3.0
            return 0.0
        if lv >= 71:
            if grade == "소형": return 10.0
            if grade == "중형": return 10.0
            return 0.0
        if lv >= 31:
            if grade == "소형": return 10.0
            if grade == "중형": return 5.0
            return 0.0
        # 1~30
        if grade == "소형": return 10.0
        return 0.0

    def display_name(self, u:dict)->str:
        nick = u.get("nickname") or "모험가"
        return f"{self.title_by_level(u['lv'])} {nick}"

    # ── 상태/가방 ────────────────────────────────────────
    def cmd_status(self, uid:str):
        u = self.store.load_user(uid)
        inv = u["inventory"]
        used, _ = self.count_used_slots(u)
        return (f"[상태] {self.display_name(u) + (f"\n집어제 효과 남은 횟수: {u.get(\'additive_uses\',0)}회" if u.get("additive_uses",0)>0 else "")} | Lv.{u['lv']}  Exp:{u['exp']}/{self.required_exp(u.get('lv',1))}  Gold:{u['gold']} | 제한골드:{u.get('gold_restricted',0)}\n"
                f"장소: {u['spot']}  |  장착 낚시대: {u['rod']}\n"
                f"가방: {used}/5칸 사용\n"
                f"지렁이({inv['지렁이']}), 떡밥({inv['떡밥']}), 집어제({inv['집어제']}), "
                f"케미1({inv['케미라이트1등급']}), 케미2({inv['케미라이트2등급']}), 케미3({inv['케미라이트3등급']})")

    def cmd_inventory(self, uid:str):
    u = self.store.load_user(uid)
    inv = u["inventory"]
    used, max_slot = self.count_used_slots(u)
    lines = [f"[가방] {used}/{max_slot}칸 사용"]

    # Build slot entries: fishes first (as recorded), then consumables present (1-slot per type)
    slots = []
    # 1) Fishes in bag
    for fish in u["bag"]:
        sale = self.sale_price_from_record(fish)
        slots.append(f"{fish['name']} {fish['size']}cm ({fish['grade']}) - 판매가 {sale}골드")
    # 2) Consumables (if present)
    def add_consume_line(name, label):
        if inv.get(name,0) > 0:
            if name == "집어제":
                slots.append(f"{label} ({inv[name]}개) - 소모품 · 사용: /집어제사용")
            elif name.startswith("케미라이트"):
                grade = "1" if "1등급" in label else ("2" if "2등급" in label else "3")
                slots.append(f"{label} ({inv[name]}개) - 소모품 · 사용: /{label} 사용 (20:00~05:00)")
            elif name in ("지렁이","떡밥"):
                slots.append(f"{label} ({inv[name]}개) - 소모품")
            else:
        # 집어제 지속 차감
        if u.get("additive_uses",0) > 0:
            u["additive_uses"] -= 1
                slots.append(f"{label} ({inv[name]}개)")
    add_consume_line("지렁이","지렁이")
    add_consume_line("떡밥","떡밥")
    add_consume_line("집어제","집어제")
    add_consume_line("케미라이트1등급","케미라이트1등급")
    add_consume_line("케미라이트2등급","케미라이트2등급")
    add_consume_line("케미라이트3등급","케미라이트3등급")

    # Cap to 5 slots and pad with empty
    view_slots = slots[:5]
    while len(view_slots) < 5:
        view_slots.append("비어있음")

    # Numbered lines 1~5
    for i, entry in enumerate(view_slots, 1):
        lines.append(f"{i}. {entry}")

    # Missing (not owned) consumables list
    missing = []
    for key, label in [("지렁이","지렁이"),("떡밥","떡밥"),("집어제","집어제"),
                       ("케미라이트1등급","케미라이트1등급"),("케미라이트2등급","케미라이트2등급"),("케미라이트3등급","케미라이트3등급")]:
        if inv.get(key,0) <= 0:
            missing.append(label)
    if missing:
        lines.append("")
        lines.append("보유하지 않은 물품: " + ", ".join(missing))

    return "
".join(lines)


    def inventory_slot_lines(self, u:dict):
    # (Deprecated in new layout) Kept for compatibility if referenced elsewhere.
    inv = u["inventory"]
    lines = []
    if inv.get("지렁이",0) > 0: lines.append(f"지렁이 ({inv['지렁이']}개) - 소모품")
    if inv.get("떡밥",0) > 0: lines.append(f"떡밥 ({inv['떡밥']}개) - 소모품")
    if inv.get("집어제",0) > 0: lines.append(f"집어제 ({inv['집어제']}개) - 소모품 · 사용: /집어제사용")
    if inv.get("케미라이트1등급",0) > 0: lines.append(f"케미라이트1등급 ({inv['케미라이트1등급']}개) - 소모품 · 사용: /케미라이트사용 1")
    if inv.get("케미라이트2등급",0) > 0: lines.append(f"케미라이트2등급 ({inv['케미라이트2등급']}개) - 소모품 · 사용: /케미라이트사용 2")
    if inv.get("케미라이트3등급",0) > 0: lines.append(f"케미라이트3등급 ({inv['케미라이트3등급']}개) - 소모품 · 사용: /케미라이트사용 3")
    return lines


    def count_used_slots(self, u:dict):
        inv = u["inventory"]
        used = len(u["bag"])
        # 미끼 각 1칸(보유 시)
        if inv["지렁이"] > 0: used += 1
        if inv["떡밥"] > 0: used += 1
        # 집어제/케미는 개수만큼
        used += inv["집어제"]
        used += inv["케미라이트1등급"] + inv["케미라이트2등급"] + inv["케미라이트3등급"]
        return used, {}

    # ── 장소/상점/구매/판매/출석/버프 ──────────────────────
    def cmd_set_spot(self, uid:str, arg:str):
        arg = (arg or "").strip()
        if arg not in ("바다","민물"):
            return "장소는 바다/민물 중 하나로 입력해 주세요. 예) /장소 바다"
        u = self.store.load_user(uid)
        u["spot"] = arg
        self.store.save_user(uid,u)
        need = {"바다":"지렁이","민물":"떡밥"}[arg]
        return f"장소를 {arg}(으)로 설정했어요. 이제 /낚시 [1~60]s 으로 시작하세요! (필요 소모품: {need})"

    def get_spot(self, uid:str):
        u = self.store.load_user(uid)
        return u.get("spot","민물")

    def cmd_shop(self):
        lines = ["[상점]"]
        for it in self.shop_items:
            lines.append(f"{it['id']}. {it['name']} - {it['price']}골드 ({it['desc']})")
        return "\n".join(lines)

    def cmd_buy(self, uid:str, arg:str):
        if not arg.isdigit():
            return "구매할 번호를 입력해 주세요. 예) /구매 1"
        item_id = int(arg)
        item = next((x for x in self.shop_items if x["id"]==item_id), None)
        if not item:
            return "없는 상품 번호예요."
        u = self.store.load_user(uid)
        # 결제 가능 여부 (제한골드 우선 사용: 지렁이/떡밥만)
price = item["price"]
name = item.get("name","")
can_use_restricted = ("지렁이" in name) or ("떡밥" in name)
normal = u.get("gold",0)
restricted = u.get("gold_restricted",0)
if can_use_restricted:
    use_restricted = min(price, restricted)
    remain = price - use_restricted
    if normal < remain:
        return "골드가 부족해요."
else:
    if normal < price:
        return "골드가 부족해요."

        # 슬롯 체크 (소모품만)
        if not item.get("rod"):
            inv = u["inventory"]
            give = item.get("give",{})
            # 사전 시뮬레이션
            tmp = inv.copy()
            for k,v in give.items():
                tmp[k] = tmp.get(k,0) + v
            used = len(u["bag"])
            if tmp["지렁이"] > 0: used += 1
            if tmp["떡밥"] > 0: used += 1
            used += tmp["집어제"]
            used += tmp["케미라이트1등급"] + tmp["케미라이트2등급"] + tmp["케미라이트3등급"]
            if used > 5:
                return f"가방가 부족해요. (구매 후 {used}/5칸)"

        # 결제 + 지급
        # 실제 차감
price = item["price"]
name = item.get("name","")
can_use_restricted = ("지렁이" in name) or ("떡밥" in name)
if can_use_restricted:
    use_restricted = min(price, u.get("gold_restricted",0))
    u["gold_restricted"] = u.get("gold_restricted",0) - use_restricted
    u["gold"] -= (price - use_restricted)
else:
    u["gold"] -= price
        if item.get("rod"):
            u["rods_owned"][item["name"]] = True
            msg_tail = " (낚시대 보유 목록에 추가)"
        else:
            for k,v in item.get("give",{}).items():
                u["inventory"][k] = u["inventory"].get(k,0) + v
            msg_tail = ""
        self.store.save_user(uid,u)
        return f"{item['name']}을(를) 구매했어요. 잔액 일반 {u['gold']}골드 | 제한 {u.get('gold_restricted',0)}골드{msg_tail}"

    def sale_multiplier(self, grade:str) -> float:
        if grade == "소형": return 1.0
        if grade == "중형": return 2.0
        if grade == "대형": return 3.0
        return 1.0

    def sale_price_from_record(self, fish:dict) -> int:
        base = int(fish.get("price", 0))
        m = self.sale_multiplier(fish.get("grade", "소형"))
        return int(round(base * m))

    def cmd_sell_one(self, uid:str, arg:str):
        if not arg.isdigit(): return "판매할 번호를 입력해 주세요. 예) /판매 1"
        idx = int(arg)-1
        u = self.store.load_user(uid)
        if idx<0 or idx>=len(u["bag"]): return "해당 번호의 물고기가 없어요."
        fish = u["bag"].pop(idx)
        sale = self.sale_price_from_record(fish)
        u["gold"] += sale
        self.store.save_user(uid,u)
        return f"{fish['name']} {fish['size']}cm를 {sale}골드에 판매! 현재 {u['gold']}골드"

    def cmd_sell_all(self, uid:str):
        u = self.store.load_user(uid)
        total = sum(self.sale_price_from_record(f) for f in u["bag"])
        cnt = len(u["bag"])
        u["bag"].clear()
        u["gold"] += total
        self.store.save_user(uid,u)
        return f"총 {cnt}마리, {total}골드 획득! 현재 {u['gold']}골드"

    def cmd_attend(self, uid:str):
        u = self.store.load_user(uid)

        # 서울 표준시 기준 날짜(YYYY-MM-DD)
        try:
            tz = ZoneInfo("Asia/Seoul") if ZoneInfo else None
        except Exception:
            tz = None
        if tz is not None:
            today_str = datetime.now(tz).strftime("%Y-%m-%d")
        else:
            # Fallback: UTC+9
            t = time.gmtime(time.time() + 9*3600)
            today_str = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"

        # 과거 int 기반 출석값 호환
        if isinstance(u.get("last_attend"), int) and not u.get("last_attend_date"):
            u["last_attend_date"] = ""

        if u.get("last_attend_date") == today_str:
            return "오늘은 이미 출석하셨어요. (기준: 서울 00:00)"

        # 칭호별 차등 보상
        title = self.title_by_level(u.get("lv", 1))
        if title == "프로":
            reward = 3000
        elif title == "전문낚시인":
            reward = 1000
        elif title == "낚시인":
            reward = 300
        else:
            reward = 150  # 낚린이 및 기본

        # 기록/보상
        u["last_attend_date"] = today_str
        u["gold_restricted"] = u.get("gold_restricted", 0) + reward
        self.store.save_user(uid, u)
        return f"✅ 출석 보상 {reward}골드! ({title})"


    def seoul_now(self):
        try:
            return datetime.now(ZoneInfo("Asia/Seoul")) if ZoneInfo else datetime.now()
        except Exception:
            return datetime.now()

    def cmd_use_chem(self, uid:str, arg:str):
        # /케미라이트사용 [1|2|3] - 밤 20:00~05:00만 사용 가능
        u = self.store.load_user(uid)
        grade = (arg or "").strip()
        if grade not in ("1","2","3"):
            return "사용법: /케미라이트사용 [1|2|3]"
        hour = self.seoul_now().hour
        allowed = (hour >= 20 or hour < 5)
        if not allowed:
            return "케미라이트는 20:00~05:00 사이에만 사용할 수 있어요. (서울 기준)"
        key = f"케미라이트{grade}등급"
        if u["inventory"].get(key,0) <= 0:
            return f"{key}이(가) 없어요. 상점에서 구매해 주세요."
        if u["chem_ready"]:
            return "이미 케미라이트 효과가 대기 중입니다. (다음 1회 자동 적용)"
        u["inventory"][key] -= 1
        u["chem_ready"] = True
        u["chem_grade"] = int(grade)
        self.store.save_user(uid,u)
        bonus_txt = {1:"대형 +0.2%p",2:"중형 +3%p",3:"소형 +20%p"}[int(grade)]
        return f"케미라이트 {grade}등급을 사용했습니다. 다음 1회: {bonus_txt}"

    # ── 낚시대 ───────────────────────────────────────────
    def cmd_rod_list(self):
        lines = ["[낚시대 종류 & 효과]",
                 "• 대나무 낚싯대 — 0골드 | 효과: 없음",
                 "• 철제 낚싯대 — 1,000골드 | 효과: 소형·중형 성공률 +2%p (대형 0)",
                 "• 강화 낚싯대 — 5,000골드 | 효과: 소형·중형 성공률 +5%p (대형 0)",
                 "• 프로 낚싯대 — 20,000골드 | 효과: 대형 +2%p, 소형 -5%p",
                 "• 레전드 낚싯대 — 100,000골드 | 효과: 대형 +5%p, 소형 -20%p",
                 "구매: /구매 [번호]   장착: /장착 낚시대 [이름]"]
        return "\n".join(lines)

    def cmd_equip_rod(self, uid:str, arg:str):
        # /장착 낚시대 [이름]
        parts = (arg or "").split(maxsplit=1)
        if len(parts) == 0 or parts[0] != "낚시대":
            return "사용법: /장착 낚시대 [이름]  (예: /장착 낚시대 철제 낚싯대)"
        name = parts[1].strip() if len(parts)>1 else ""
        if not name:
            return "장착할 낚시대 이름을 입력해 주세요."
        u = self.store.load_user(uid)
        if not u["rods_owned"].get(name):
            return f"'{name}' 을(를) 보유하고 있지 않습니다."
        u["rod"] = name  # 한 개만 착용 가능 (자동 교체)
        self.store.save_user(uid,u)
        return f"{name} 을(를) 장착했습니다!"

    # ── 낚시 처리 ────────────────────────────────────────
    def prepare_cast(self, uid:str, spot:str):
        if spot not in ("바다","민물"):
            return False, "장소는 바다/민물만 가능해요."
        u = self.store.load_user(uid)
        need = {"바다":"지렁이","민물":"떡밥"}[spot]
        if u["inventory"][need] <= 0:
            return False, f"{spot} 낚시에는 {need}이(가) 필요해요. /상점 에서 구매해 주세요."
        # 소모품 차감
        u["inventory"][need] -= 1
        self.store.save_user(uid,u)
        return True, f"{spot} 낚시 소모품 {need} 1개 사용!"

    # 소형/중형/대형 가격 & 경험치
    def calc_price(self, grade:str, size_cm:int):
        if grade == "소형":
            return max(1, int(size_cm * 0.1))
        if grade == "중형":
            return size_cm * 1
        if grade == "대형":
            return size_cm * 10
        return size_cm

    
def calc_exp(self, grade:str, size_cm:int) -> int:
    """
    EXP 계산 규칙:
    - 소형: size_cm
    - 중형: size_cm * 10
    - 대형: size_cm * 100
    """
    if grade == "대형":
        return size_cm * 100
    if grade == "중형":
        return size_cm * 10
    return size_cm  # 소형


    SIZE_BINS = [("XS",0.40),("S",0.30),("M",0.20),("L",0.07),("XL",0.03)]
    BASE_BY_GRADE_BIN = {
        "소형": {"XS":2.40,"S":1.80,"M":1.20,"L":0.42,"XL":0.18},          # 각 어종 6%p 분배
        "중형": {"XS":0.132,"S":0.099,"M":0.066,"L":0.0231,"XL":0.0099},  # 각 어종 0.33%p 분배
        "대형": {"XS":0.002,"S":0.0015,"M":0.001,"L":0.00035,"XL":0.00015} # 각 어종 0.005%p 분배
    }

    def pick_species_and_size(self, spot:str, grade:str):
        name, smin, smax = random.choice(self.fish_catalog[spot][grade])
        # 사이즈 구간 선택(확률 가중)
        r = random.random()
        acc = 0.0
        chosen_bin = "XS"
        for b, w in self.SIZE_BINS:
            acc += w
            if r <= acc:
                chosen_bin = b
                break
        # 구간 범위 동일 5등분
        span = max(1, smax - smin + 1)
        step = span / 5.0
        bin_idx = {"XS":0,"S":1,"M":2,"L":3,"XL":4}[chosen_bin]
        low = int(smin + bin_idx*step)
        high = int(smin + (bin_idx+1)*step) - 1
        if high < low: high = low
        size = random.randint(low, min(high, smax))
        base = self.BASE_BY_GRADE_BIN[grade][chosen_bin]
        return {"name":name, "size":size, "grade":grade, "base_prob":base, "bin":chosen_bin}

    def resolve_fishing(self, uid:str, spot:str, chosen_sec:int, elapsed_sec:int, early_penalty:bool):
        u = self.store.load_user(uid)

        # 등급 평균 확률에 맞춘 1차 등급 결정 (소형30, 중형1, 대형0.01)
                # 등급 선택 확률(기본): 소형 98.99%, 중형 1.00%, 대형 0.01%
        P_SMALL, P_MED, P_LARGE = 98.99, 1.0, 0.01
        # '모든 장비+아이템' 콤보(강화 낚싯대, 집어제 준비, 케미 2등급 준비, 60s 이상) 시 중형 가중치 상승
        rod = u.get("rod","대나무 낚싯대")
        if (rod in ("강화 낚싯대","철제 낚싯대") and u.get("additive_ready") and u.get("chem_ready") and u.get("chem_grade") == 2 and secs >= 60):
            P_MED = 5.5
            P_SMALL = 100.0 - P_MED - P_LARGE
        r = random.random()*100.0
        if r <= P_SMALL:
            grade = "소형"
        elif r <= P_SMALL + P_MED:
            grade = "중형"
        else:
            grade = "대형"


        # 등급별 시간 보정 (초당: 최대보정/60, 상한 적용)
        secs = elapsed_sec if early_penalty else chosen_sec
        time_bonus = 0.0
        if g == "소형":
            time_bonus = min(38.2252, secs * (38.2252/60.0))
        elif g == "중형":
            time_bonus = min(5.0, secs * (5.0/60.0))
        elif g == "대형":
            time_bonus = min(1.0, secs * (1.0/60.0))

        pick = self.pick_species_and_size(spot, grade)
        name, size, g = pick["name"], pick["size"], pick["grade"]
        base = pick["base_prob"]

        # 집어제/케미라이트
        bonus = 0.0
        if u.get("additive_uses",0) > 0:
            bonus += 5.0
            u["additive_uses"] = u.get("additive_uses",0)  # 차감은 결과 처리 후
        if u.get("chem_ready"):
            cg = u.get("chem_grade",0)
            if cg == 1 and g == "대형": bonus += 5.0
            if cg == 2 and g == "중형": bonus += 3.0
            if cg == 3 and g == "소형": bonus += 1.0
            u["chem_ready"] = False
            u["chem_grade"] = 0

        # 낚시대 보정 (철/강=소·중만, 프로/레전드=대형 only + 소형 감소)
        rod = u.get("rod","대나무 낚싯대")
        if rod == "철제 낚싯대" and g in ("소형","중형"): bonus += 2.0
        if rod == "강화 낚싯대" and g in ("소형","중형"): bonus += 5.0
        if rod == "프로 낚싯대":
            if g == "대형": bonus += 2.0
            if g == "소형": bonus -= 5.0
        if rod == "레전드 낚싯대":
            if g == "대형": bonus += 5.0
            if g == "소형": bonus -= 20.0

        # 레벨 보정 (소형 공통 + 등급별)
        bonus += self.level_bonus(u["lv"], g)

        # 조기 릴 패널티
        if early_penalty:
            bonus -= 80.0

        # 최종 성공률 (0~95로 클램프)
        final_p = max(0.0, min(95.0, base + time_bonus + bonus))
        roll = random.random()*100.0

        if roll <= final_p:
        # 집어제 지속 차감
        if u.get("additive_uses",0) > 0:
            u["additive_uses"] -= 1
            # 가방 슬롯 체크(물고기 1마리=1칸)
            used, _ = self.count_used_slots(u)
            if used >= 5:
                self.store.save_user(uid,u)
                return "가방가 가득(5/5)이라 물고기를 보관할 수 없어요. 판매(/전부판매) 후 다시 시도해 주세요."
            price = self.calc_price(g, size)
            exp = self.calc_exp(g, size)
            u["bag"].append({"name": name, "size": size, "grade": g, "price": price})
            self.gain_exp(u, exp)
            self.store.save_user(uid,u)
            prefix = "⏱ 조기 릴 성공! " if early_penalty else "🎉 성공! "
            sale = self.sale_price_from_record(u["bag"][-1])
            return (f"{prefix}[{spot}] {name} {size}cm ({g})\n"
                    f"가격(판매가 표기): {sale}골드 | 경험치 +{exp}\n"
                    f"/가방 으로 보관함 확인, /전부판매 로 일괄 판매 가능")
        else:
            self.store.save_user(uid,u)
            if early_penalty:
                return KakaoResp.text("놓친 것 같다.....")
            return KakaoResp.text("놓친 것 같다.....")

    

def required_exp(self, lv:int) -> int:
    """
    레벨업 임계치: 레벨별 상승 (선형)
    - 다음 레벨까지 필요한 Exp = 100 + 50*(lv-1)
      (Lv1→2:100, Lv2→3:150, Lv3→4:200, ...)
    """
    if lv < 1: lv = 1
    return 100 + 50*(lv-1)
# ── 경험치/레벨업 ────────────────────────────────────
    def gain_exp(self, u:dict, exp:int):
        u["exp"] += exp
        while True:
            need = self.required_exp(u.get("lv",1))
            if u["exp"] < need:
                break
            u["exp"] -= need
            u["lv"] += 1
        # 저장은 호출부에서


    def cmd_newbie_chance(self, uid:str):
        u = self.store.load_user(uid)
        # 등급 확인
        title = self.title_by_level(u.get("lv",1))
        if title != "낚린이":
            return "초보자 찬스는 낚린이 등급에서만 사용할 수 있어요."

        # 오늘 날짜
        try:
            tz = ZoneInfo("Asia/Seoul") if ZoneInfo else None
        except Exception:
            tz = None
        if tz is not None:
            today_str = datetime.now(tz).strftime("%Y-%m-%d")
        else:
            t = time.gmtime(time.time() + 9*3600)
            today_str = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"

        nb = u.get("newbie_chance", {"date":"", "count":0})
        if nb.get("date") != today_str:
            nb = {"date": today_str, "count": 0}

        if nb["count"] >= 3:
            return f"오늘은 더 받을 수 없어요. (3/3)"

        nb["count"] += 1
        u["newbie_chance"] = nb
        u["gold_restricted"] = u.get("gold_restricted", 0) + 1000
        self.store.save_user(uid, u)
        return f"✅ 초보자찬스! 1000골드(제한) 획득. 오늘 사용 {nb['count']}/3 | 제한골드 {u['gold_restricted']}"


def cmd_home(self, uid:str):
    u = self.store.load_user(uid)
    header = "\n".join([
        "🎣 낚시 RPG 사용법",
        "1) /장소 [바다|민물]   ← 먼저 장소를 설정하세요",
        "2) /낚시 [1~60]s      ← 해당 초 만큼 캐스팅 (예: /낚시 15s)",
        "3) 시간이 끝나면 /릴감기 로 결과 확인",
        ""
    ])
    shop = "\n".join([
        "🏪 상점 이용 방법",
        "/상점               → 상점 목록 보기",
        "/구매 [번호]        → 해당 번호 아이템 구매",
        "/판매 [번호]        → 해당 번호 물고기 판매",
        "/전부판매           → 가방 속 물고기 전부 판매",
        "",
        "/출석               → 출석 보상 받기",
        "/초보자찬스         → 낚린이 전용 보너스(1일 3회)",
    ])
    try:
        tz = ZoneInfo("Asia/Seoul") if ZoneInfo else None
    except Exception:
        tz = None
    if tz is not None:
        today_str = datetime.now(tz).strftime("%Y-%m-%d")
    else:
        t = time.gmtime(time.time() + 9*3600)
        today_str = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
    nb = u.get("newbie_chance", {"date":"", "count":0})
    used = nb["count"] if nb.get("date")==today_str else 0
    title = self.title_by_level(u.get("lv",1))
    if title == "낚린이":
        shop += f"\n(오늘 사용: {used}회, 남은 횟수: {max(0,3-used)}회)\n"
    else:
        shop += "\n(초보자찬스는 낚린이 전용입니다)\n"
    nick = f"닉네임: {u.get('nickname') or '-'}"
    stat = self.cmd_status(uid)
    bag = self.cmd_inventory(uid)
    return "\n".join([header, shop, "", nick, stat, "", bag])


def cmd_sell_item(self, uid:str, arg:str):
    arg = arg.strip()
    if not arg:
        return "아이템 이름과 수량을 입력해 주세요. 예) /아이템판매 지렁이 3"
    parts = arg.split()
    if len(parts) == 1:
        name, qty = parts[0], 1
    else:
        name = " ".join(parts[:-1])
        qty_str = parts[-1]
        if qty_str.isdigit():
            qty = int(qty_str)
        else:
            name = " ".join(parts)
            qty = 1

    if qty < 1:
        return "수량은 1 이상이어야 합니다."

    u = self.store.load_user(uid)
    if name in ("철제 낚싯대","강화 낚싯대","프로 낚싯대","레전드 낚싯대"):
        if u["rod"] == name:
            return "착용 중인 낚싯대는 판매할 수 없습니다."
        if not u["rods_owned"].get(name):
            return f"{name}은(는) 보유하고 있지 않습니다."
        owned_others = [r for r,v in u["rods_owned"].items() if v and r != name]
        if not owned_others:
            return "최소 1개의 낚싯대는 보유해야 합니다. 판매가 불가능합니다."
        price = self.unit_price_map.get(name, 0)
        refund = int(price * 0.5)
        u["rods_owned"][name] = False
        u["gold"] = u.get("gold", 0) + refund
        self.store.save_user(uid, u)
        return f"{name}을(를) 판매했습니다. 환불 금액 {refund}골드. 현재 골드 {u['gold']}골드"

    inv = u["inventory"]
    if name not in inv:
        return f"{name}은(는) 판매할 수 없는 품목입니다."
    if inv[name] <= 0:
        return f"{name}이(가) 가방에 없습니다."
    if inv[name] < qty:
        return f"{name} 보유 수량이 부족합니다. (보유: {inv[name]}개)"

    unit = self.unit_price_map.get(name, 0)
    if unit <= 0:
        return f"{name}은(는) 환불이 불가능한 품목입니다."

    inv[name] -= qty
    refund = int(unit * 0.5) * qty
    u["gold"] = u.get("gold", 0) + refund
    self.store.save_user(uid, u)
    return f"{name} {qty}개를 판매했습니다. 환불 금액 {refund}골드. 현재 골드 {u['gold']}골드"


def cmd_use_chum(self, uid:str):
    u = self.store.load_user(uid)
    inv = u["inventory"]
    if inv.get("집어제",0) <= 0:
        return "집어제가 없어요. 상점에서 구매해 주세요."
    inv["집어제"] -= 1
    u["additive_uses"] = 3
    u["additive_ready"] = False
    self.store.save_user(uid, u)
    return f"✅ 집어제 1개를 사용했습니다. (남은 수량: {inv['집어제']}개)\n효과가 3회 낚시 동안 지속됩니다."


def cmd_use_chem_named(self, uid:str, item_name:str):
    u = self.store.load_user(uid)
    hour = self.seoul_now().hour
    allowed = (hour >= 20 or hour < 5)
    if not allowed:
        return "케미라이트는 20:00~05:00 사이에만 사용할 수 있어요. (서울 기준)"
    inv = u["inventory"]
    if inv.get(item_name,0) <= 0:
        return f"{item_name}이(가) 없어요. 상점에서 구매해 주세요."
    inv[item_name] -= 1
    grade = 1 if "1등급" in item_name else (2 if "2등급" in item_name else 3)
    u["chem_ready"] = True
    u["chem_grade"] = grade
    self.store.save_user(uid, u)
    return f"✅ {item_name} 1개를 사용했습니다. (남은 수량: {inv[item_name]}개)"


def cmd_sell_item_prepare(self, uid:str, arg:str):
    arg = (arg or "").strip()
    if not arg:
        return "아이템 이름과 수량을 입력해 주세요. 예) /아이템판매 지렁이 3"

    parts = arg.split()
    if len(parts) == 1:
        name, qty = parts[0], 1
    else:
        name = " ".join(parts[:-1])
        qty_str = parts[-1]
        qty = int(qty_str[:-1]) if qty_str.endswith("개") and qty_str[:-1].isdigit() else (int(qty_str) if qty_str.isdigit() else 1)

    if qty < 1:
        return "수량은 1 이상이어야 합니다."

    u = self.store.load_user(uid)

    # Rod handling
    if name in ("철제 낚싯대","강화 낚싯대","프로 낚싯대","레전드 낚싯대"):
        if u["rod"] == name:
            return "착용 중인 낚싯대는 판매할 수 없습니다."
        if not u["rods_owned"].get(name):
            return f"{name}은(는) 보유하고 있지 않습니다."
        owned_others = [r for r,v in u["rods_owned"].items() if v and r != name]
        if not owned_others:
            return "최소 1개의 낚싯대는 보유해야 합니다. 판매가 불가능합니다."
        price = self.unit_price_map.get(name, 0)
        refund = int(price * 0.5)
        u["pending_sale"] = {"type":"rod","name":name,"qty":1,"refund":refund}
        self.store.save_user(uid, u)
        return (f"⚠️ 되팔기 안내\n"
                f"상점에서 산 물건을 되팔면 구매가격의 50%만 환불됩니다.\n\n"
                f"판매 대상: {name} ×1\n"
                f"환불 예정: 💰{refund}\n\n"
                f"진행하시겠습니까?\n/판매확인  |  /판매취소")

    # Consumables
    inv = u["inventory"]
    if name not in inv:
        return f"{name}은(는) 판매할 수 없는 품목입니다."
    if inv[name] <= 0:
        return f"{name}이(가) 가방에 없습니다."
    if inv[name] < qty:
        return f"{name} 보유 수량이 부족합니다. (보유: {inv[name]}개)"

    unit = self.unit_price_map.get(name, 0)
    if unit <= 0:
        return f"{name}은(는) 환불이 불가능한 품목입니다."

    refund = int(unit * 0.5) * qty
    u["pending_sale"] = {"type":"consumable","name":name,"qty":qty,"refund":refund}
    self.store.save_user(uid, u)
    return (f"⚠️ 되팔기 안내\n"
            f"상점에서 산 물건을 되팔면 구매가격의 50%만 환불됩니다.\n\n"
            f"판매 대상: {name} ×{qty}\n"
            f"환불 예정: 💰{refund}\n\n"
            f"진행하시겠습니까?\n/판매확인  |  /판매취소")


def cmd_sell_item_confirm(self, uid:str):
    u = self.store.load_user(uid)
    p = u.get("pending_sale") or {}
    if not p:
        return "대기 중인 판매가 없습니다. 예) /아이템판매 집어제 1"
    name = p.get("name")
    qty = p.get("qty", 1)
    refund = int(p.get("refund", 0))
    typ = p.get("type")

    if typ == "rod":
        if u["rod"] == name:
            return "착용 중인 낚싯대는 판매할 수 없습니다."
        if not u["rods_owned"].get(name):
            u["pending_sale"] = {}
            self.store.save_user(uid, u)
            return f"{name}은(는) 더 이상 보유하고 있지 않습니다."
        owned_others = [r for r,v in u["rods_owned"].items() if v and r != name]
        if not owned_others:
            return "최소 1개의 낚싯대는 보유해야 합니다. 판매가 불가능합니다."
        u["rods_owned"][name] = False
        u["gold"] = u.get("gold", 0) + refund
        u["pending_sale"] = {}
        self.store.save_user(uid, u)
        return f"{name}을(를) 판매했습니다. 환불 금액 💰{refund}. 현재 골드 💰{u['gold']}"

    inv = u["inventory"]
    if inv.get(name,0) < qty:
        u["pending_sale"] = {}
        self.store.save_user(uid, u)
        return f"{name} 수량이 변경되어 판매할 수 없습니다. (보유: {inv.get(name,0)}개)"
    inv[name] -= qty
    u["gold"] = u.get("gold", 0) + refund
    u["pending_sale"] = {}
    self.store.save_user(uid, u)
    return f"{name} {qty}개를 판매했습니다. 환불 금액 💰{refund}. 현재 골드 💰{u['gold']}"

def cmd_sell_item_cancel(self, uid:str):
    u = self.store.load_user(uid)
    if u.get("pending_sale"):
        u["pending_sale"] = {}
        self.store.save_user(uid, u)
        return "되팔기를 취소했습니다."
    return "취소할 대기 중인 판매가 없습니다."


def cmd_enable_access(self, uid:str):
    meta = self.store.get_meta()
    if not meta.get("access_enabled"):
        meta["access_enabled"] = True
        meta["owner"] = uid
        self.store.set_meta(meta)
        return "채널 기능이 활성화되었습니다. (설정자: 본인)"
    if meta.get("owner") in (None, uid):
        meta["access_enabled"] = True
        meta["owner"] = uid if meta.get("owner") is None else meta.get("owner")
        self.store.set_meta(meta)
        return "이미 활성화되어 있습니다."
    return "이미 다른 사용자가 활성화했습니다. 변경은 채널 주인만 가능합니다."

def cmd_disable_access(self, uid:str):
    meta = self.store.get_meta()
    owner = meta.get("owner")
    if owner not in (None, uid):
        return "채널 주인만 해제할 수 있습니다."
    meta["access_enabled"] = False
    meta["owner"] = owner if owner else uid
    self.store.set_meta(meta)
    return "채널 기능을 해제했습니다."
