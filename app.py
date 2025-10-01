
import os
import json
import random
from datetime import datetime, time, date
from flask import Flask, request, jsonify
import threading

app = Flask(__name__)
DATA_PATH = os.environ.get("DATA_PATH", "data.json")

# -----------------------------
# 상수/정책
# -----------------------------
RESTRICTED_CAP = 1000
BAG_CAP = 5

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
CONSUMABLES = {"지렁이","떡밥","집어제","케미라이트1등급","케미라이트2등급","케미라이트3등급"}
RESTRICTED_ALLOWED = {"지렁이","떡밥"}

STRICT_CMDS = {"/","/상점","/전부판매","/출석","/초보자찬스","/릴감기","/판매확인","/판매취소","/기록"}
PREFIX_CMDS = {"/닉네임 ","/구매 ","/아이템판매 ","/낚시 ","/장소 ",
               "/케미라이트1등급 사용","/케미라이트2등급 사용","/케미라이트3등급 사용","/집어제사용"}

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
# 데이터 저장/로드
# -----------------------------
def load_store():
    if not os.path.exists(DATA_PATH):
        return {"users":{}}
    try:
        with open(DATA_PATH,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"users":{}}

def save_store(store):
    tmp=DATA_PATH+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(store,f,ensure_ascii=False,indent=2)
    os.replace(tmp,DATA_PATH)

def today_str():
    return date.today().isoformat()

def kakao_text(t):
    return jsonify({"version":"2.0","template":{"outputs":[{"simpleText":{"text":t}}]}})

def fmt_money(g,r):
    return f"Gold: 💰{g:,} | 제한골드: 💰{r:,}"

def is_night(now=None):
    now=now or datetime.now()
    t=now.time()
    return (t>=time(20,0)) or (t<time(5,0))

# -----------------------------
# 유저 데이터
# -----------------------------
def get_user(store, uid):
    u=store["users"].get(uid)
    if u is None:
        u={"nickname":None,"nick_locked":False,"gold":0,"restricted_gold":0,
           "level":1,"exp":0,"rod":"철제 낚싯대","inventory":{},"fish":[],
           "attendance_last":None,"newbie":{"date":None,"count":0},
           "additive_uses":0,"location":None,"records":{"min":None,"max":None},
           "casting":None,"active_buff":None}
        store["users"][uid]=u
    return u

def get_title(level):
    if level<31: return "낚린이"
    elif level<71: return "낚시인"
    elif level<100: return "전문낚시인"
    else: return "프로"

def level_threshold(lv):
    return 100+50*(lv-1)

def add_exp(u,amount):
    u["exp"]+=amount
    while u["exp"]>=level_threshold(u["level"]):
        u["exp"]-=level_threshold(u["level"]); u["level"]+=1

# -----------------------------
# 가방
# -----------------------------
def slot_usage(u):
    used=0; slots=[]
    for f in u["fish"]:
        if used<5: slots.append({"type":"fish","data":f}); used+=1
    for name,cnt in u["inventory"].items():
        if cnt>0 and name in CONSUMABLES and used<5:
            slots.append({"type":"consumable","name":name,"count":cnt}); used+=1
    while used<5:
        slots.append({"type":"empty"}); used+=1
    return slots

def bag_full(u):
    return all(s["type"]!="empty" for s in slot_usage(u))

def will_overflow_if_add_consumable(u,name):
    cnt=u["inventory"].get(name,0)
    if cnt>0: return False
    return all(s["type"]!="empty" for s in slot_usage(u))

def add_consumable(u,name,qty):
    before=u["inventory"].get(name,0)
    after=before+qty
    limit=100 if name in {"지렁이","떡밥"} else None
    note=None
    if limit is not None and after>limit:
        u["inventory"][name]=limit
    else:
        u["inventory"][name]=max(0,after)
    if u["inventory"][name]<=0: del u["inventory"][name]
    return note

def bag_text_lines(u):
    slots=slot_usage(u)
    used=sum(1 for s in slots if s["type"]!="empty")
    lines=[f"[가방] {used}/5칸 사용"]
    for i,s in enumerate(slots,start=1):
        if s["type"]=="empty":
            lines.append(f"{i}. 비어있음")
        elif s["type"]=="fish":
            f=s["data"]
            lines.append(f"{i}. {f['name']} {f['cm']}cm ({f['grade']}) - 판매가 {f['price']}골드")
        else:
            lines.append(f"{i}. {s['name']} ({s['count']}개)")
    return lines

# -----------------------------
# 홈 화면
# -----------------------------
def home_text(u):
    lines=[
        "🎣 낚시 RPG 사용법",
        "1) /장소 [바다|민물] ← 먼저 장소를 설정하세요",
        "2) /낚시 [1~60]s ← 예: /낚시 15s 또는 /낚시 15초",
        "3) 시간이 끝나면 자동으로 결과 확인",
        "4) /기록 → 잡아본 물고기 확인",
        "",
        "🏪 상점 이용 방법",
        "/상점 → 상점 목록 보기",
        "/구매 [이름] [갯수]",
        "/아이템판매 [이름] [수량]",
        "",
        "(출석/보너스)",
        "/출석 → 출석 보상",
        "/초보자찬스 → 1일 2회 (잔액 0일 때만)",
        "",
    ]
    title=get_title(u["level"])
    lines.append(f"닉네임: [{title}] {u['nickname']}")
    lines+=[f"Lv.{u['level']}  Exp: {u['exp']}/{level_threshold(u['level'])}",fmt_money(u['gold'],u['restricted_gold']),f"착용 낚싯대: {u['rod']}"]
    lines.append("")
    lines+=bag_text_lines(u)
    owned=set(k for k,v in u["inventory"].items() if v>0)
    missing=[x for x in ["지렁이","떡밥","집어제","케미라이트1등급","케미라이트2등급","케미라이트3등급"] if x not in owned]
    if missing:
        lines.append("보유하지 않은 물품: "+", ".join(missing))
    return "\n".join(lines)

# -----------------------------
# 낚시 처리
# -----------------------------
def ensure_bait_and_consume(u):
    loc=u.get("location")
    if not loc: return False,"⚠️ /장소 [바다|민물] 먼저 설정하세요."
    bait="지렁이" if loc=="바다" else "떡밥"
    if u["inventory"].get(bait,0)<=0:
        return False,f"⚠️ {bait}가 없어 {loc}에서 낚시할 수 없습니다."
    add_consumable(u,bait,-1)
    return True,f"✅ {bait} 1개 사용됨 (남은 {bait}: {u['inventory'].get(bait,0)}개)"

def calc_prob(seconds):
    sec=min(seconds,60)
    base={"소형":0.30,"중형":0.005,"대형":0.000025}
    base["소형"]+=0.05*(sec/60)
    base["중형"]+=0.005*(sec/60)
    base["대형"]+=0.000025*(sec/60)
    total=sum(base.values())
    base["실패"]=max(0.0,1.0-total)
    return base

def handle_cast(u,seconds):
    if u.get("casting"): return "⚠️ 이미 캐스팅 중입니다."
    ok,msg=ensure_bait_and_consume(u)
    if not ok: return msg
    u["casting"]={"seconds":seconds,"start":datetime.now().isoformat()}
    threading.Timer(seconds,auto_reel,[u]).start()
    return f"뭔가가 걸렸다 !!\n{seconds}초 캐스팅 시작!"

def auto_reel(u):
    store=load_store()
    uid=None
    for k,v in store["users"].items():
        if v is u: uid=k; break
    if not uid: return
    text=handle_reel(u)
    save_store(store)

def handle_reel(u):
    if not u.get("casting"): return "⚠️ 캐스팅 기록 없음."
    seconds=u["casting"]["seconds"]
    prob=calc_prob(seconds)
    roll=random.random(); outcome="실패"; cum=0
    for k,v in prob.items():
        cum+=v
        if roll<=cum: outcome=k; break
    u["casting"]=None
    if outcome=="실패":
        bait="지렁이" if u["location"]=="바다" else "떡밥"
        return f"🎣 낚시 실패... 다시 도전하세요!\n남은 {bait}: {u['inventory'].get(bait,0)}개"
    loc=u["location"]
    fishlist=FISH_POOL[loc][outcome]
    name,smin,smax=random.choice(fishlist)
    cm=random.randint(smin,smax)
    if outcome=="소형": price,exp=cm,cm
    elif outcome=="중형": price,exp=cm*100,cm*10
    else: price,exp=cm*1000,cm*100
    fish={"name":name,"cm":cm,"grade":outcome,"price":price,"location":loc,"caught_at":today_str()}
    u["fish"].append(fish); add_exp(u,exp)
    bait="지렁이" if loc=="바다" else "떡밥"
    return f"🎣 {name} {cm}cm ({outcome}) 낚음!\n가격:💰{price} | 경험치+{exp}\n남은 {bait}: {u['inventory'].get(bait,0)}개"

# -----------------------------
# 명령 처리
# -----------------------------
def handle_cmd(u,utt):
    t=utt.strip()
    if not u["nick_locked"]:
        if t.startswith("/닉네임 "):
            nick=t.replace("/닉네임 ","",1).strip()
            u["nickname"]=nick; u["nick_locked"]=True
            return f"닉네임이 '{nick}'으로 설정되었습니다. 이제 '/' 입력으로 홈 화면을 보세요."
        if t=="/":
            return "🎣 낚시 RPG에 오신 걸 환영합니다!\n닉네임을 먼저 설정하세요.\n설정 방법: /닉네임 원하는이름\n예) /닉네임 홍길동"
        return ""
    if t=="/": return home_text(u)
    if t.startswith("/장소"):
        parts=t.split()
        if len(parts)>=2 and parts[1] in ("바다","민물"):
            u["location"]=parts[1]
            return f"장소를 '{u['location']}'로 설정했습니다."
        return "형식: /장소 [바다|민물]"
    if t.startswith("/낚시"):
        num=0
        for ch in t:
            if ch.isdigit(): num=num*10+int(ch)
        if num<=0 or num>60: return "낚시 시간은 1~60초."
        return handle_cast(u,num)
    if t=="/릴감기": return handle_reel(u)
    if t=="/상점":
        return "🏪 상점\n- 지렁이 (바다낚시 전용)\n- 떡밥 (민물낚시 전용)"
    if t=="/기록":
        rec=u.get("records") or {}
        return str(rec)
    return ""

# -----------------------------
# 라우팅
# -----------------------------
@app.route("/skill",methods=["POST"])
def skill():
    body=request.get_json(silent=True) or {}
    utter=(body.get("userRequest",{}).get("utterance") or "").strip()
    uid=body.get("userRequest",{}).get("user",{}).get("id") or "anon"
    if not is_allowed_command(utter): return kakao_text(""),200
    store=load_store(); u=get_user(store,uid)
    text=handle_cmd(u,utter); save_store(store)
    return kakao_text(text or ""),200

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
