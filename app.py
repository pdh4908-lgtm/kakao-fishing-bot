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
# 상점/아이템 정의 (가격 수정 반영)
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
# 확률 계산 (보정치 절반, 중형 절반 반영)
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
# 낚시/릴감기 (자동 진행 + 중복투척 방지 + 미끼소모 + 잔량표시)
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
# 명령 처리 (원래 app.py 전체 로직 반영)
# -----------------------------
def handle_cmd(u, utt:str):
    t = (utt or "").strip()
    # 닉네임 미설정 시 안내
    if not u["nick_locked"]:
        if t.startswith("/닉네임 "):
            nickname = t.replace("/닉네임 ","",1).strip()
            if not nickname:
                return "닉네임 설정 형식: /닉네임 원하는이름"
            u["nickname"] = nickname
            u["nick_locked"] = True
            return f"닉네임이 '{nickname}'(으)로 설정되었습니다.\n이제 '/' 로 홈 화면을 확인해 보세요."
        if t == "/":
            return ("🎣 낚시 RPG에 오신 것을 환영합니다!\n\n닉네임을 먼저 설정해 주세요.\n닉네임은 한 번 설정하면 변경할 수 없습니다.\n\n"
                    "설정 방법: /닉네임 [원하는이름]\n예) /닉네임 홍길동")
        return ""

    # 닉네임 설정 후 홈
    if t in ("/","홈","home","메뉴"):
        return f"닉네임: {u['nickname']}\n레벨: {u['level']} (Exp {u['exp']})"

    # 장소 설정
    if t.startswith("/장소"):
        parts=t.split()
        if len(parts)>=2 and parts[1] in ("바다","민물"):
            u["location"]=parts[1]
            return f"장소를 '{u['location']}'(으)로 설정했습니다."
        return "형식: /장소 [바다|민물]"

    # 상점
    if t=="/상점":
        return "\n".join([f"- {k} {v}골드" for k,v in PRICES.items()])

    # 출석
    if t=="/출석":
        today=today_str()
        if u["attendance_last"]==today:
            return "오늘은 이미 출석 체크했습니다."
        u["attendance_last"]=today
        u["restricted_gold"]=min(RESTRICTED_CAP,u["restricted_gold"]+150)
        return f"출석 보상 지급! {fmt_money(u['gold'],u['restricted_gold'])}"

    # 초보자찬스 (1일 2회)
    if t=="/초보자찬스":
        today=today_str()
        nb=u["newbie"]
        if nb.get("date")!=today:
            nb["date"]=today; nb["count"]=0
        if nb["count"]>=2:
            return "오늘은 이미 2회 모두 사용했습니다."
        if u["restricted_gold"]!=0:
            return "제한골드 잔액이 0이어야 합니다."
        u["restricted_gold"]=RESTRICTED_CAP
        nb["count"]+=1
        return f"초보자찬스 사용 {nb['count']}/2회 완료."

    # 낚시
    if t.startswith("/낚시"):
        num=0
        for ch in t:
            if ch.isdigit(): num=num*10+int(ch)
        if num<=0 or num>60:
            return "낚시 시간은 1~60초 입력."
        return handle_cast(u,num)

    if t=="/릴감기":
        return handle_reel(u)

    return ""

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
    if not is_allowed_command(utter):
        return kakao_text(""),200
    text=handle_cmd(u,utter)
    save_store(store)
    return kakao_text(text or ""),200

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
