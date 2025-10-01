import os
import json
import random
import time
from datetime import datetime, time as dtime, date
from flask import Flask, request, jsonify

app = Flask(__name__)
DATA_PATH = os.environ.get("DATA_PATH", "data.json")

# -----------------------------
# 상수/정책
# -----------------------------
RESTRICTED_CAP = 1000
BAG_CAP = 5
PRICES = {
    "지렁이": 10,   # 제한골드 가능
    "떡밥": 10,     # 제한골드 가능
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

def is_allowed_command(text:str)->bool:
    if not text or not text.startswith("/"): return False
    if text in STRICT_CMDS: return True
    for p in PREFIX_CMDS:
        if text==p or text.startswith(p): return True
    return False

# -----------------------------
# 유저 데이터
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

def kakao_text(t):
    return jsonify({"version":"2.0","template":{"outputs":[{"simpleText":{"text":t}}]}})

def fmt_money(g,r): return f"Gold: 💰{g:,} | 제한골드: 💰{r:,}"
def is_night(now=None): 
    now=now or datetime.now(); t=now.time()
    return (t>=dtime(20,0)) or (t<dtime(5,0))

# -----------------------------
# 레벨/칭호
# -----------------------------
def get_title(level:int)->str:
    if level<31: return "낚린이"
    elif level<71: return "낚시인"
    elif level<100: return "전문낚시인"
    return "프로"
def title_attendance_reward(title:str)->int:
    return {"낚린이":150,"낚시인":300,"전문낚시인":1000,"프로":3000}.get(title,0)
def level_threshold(lv:int)->int: return 100+50*(lv-1)
def add_exp(u, amount):
    u["exp"]+=amount
    while u["exp"]>=level_threshold(u["level"]):
        u["exp"]-=level_threshold(u["level"]); u["level"]+=1

# -----------------------------
# 미끼 유틸
# -----------------------------
def _bait_key_for(loc):
    return "지렁이" if loc=="바다" else ("떡밥" if loc=="민물" else None)

def ensure_bait_and_consume(u:dict):
    loc=u.get("location")
    if not loc: return False,"⚠️ 먼저 /장소 [바다|민물] 을 설정하세요."
    need=_bait_key_for(loc)
    inv=u.setdefault("inventory",{})
    have=inv.get(need,0)
    if have<=0:
        return False,f"⚠️ {need}가 없어 '{loc}'에서 낚시할 수 없습니다.\n/상점 에서 {need}를 구매해 주세요."
    inv[need]=have-1
    return True,f"✅ {need} 1개 사용됨 (남은 {need}: {inv[need]}개)"

# -----------------------------
# 낚시 확률
# -----------------------------
FISH_POOL = {
    "민물": {
        "소형":[("붕어",1,40),("피라미",5,35),("미꾸라지",3,20)],
        "중형":[("잉어",41,99),("메기",60,90)],
        "대형":[("철갑상어",100,300),("쏘가리",100,180)],
    },
    "바다": {
        "소형":[("전어",10,30),("멸치",5,15),("고등어",20,40)],
        "중형":[("방어",50,90),("도미",60,95)],
        "대형":[("참치",100,600),("상어",200,800)],
    }
}

def calc_prob(seconds:int,u)->dict:
    sec=min(seconds,60)
    base={"소형":0.30,"중형":0.005,"대형":0.00005}  # 중형 절반
    base["소형"]+=0.05*(sec/60)  # 보정치 절반
    base["중형"]+=0.005*(sec/60)
    base["대형"]+=0.000025*(sec/60)
    if u.get("additive_uses",0)>0:
        base["중형"]+=0.01;base["대형"]+=0.00005
    total=sum(base.values())
    base["실패"]=max(0.0,1.0-total)
    return base

# -----------------------------
# 낚시/릴감기
# -----------------------------
def handle_reel(u,seconds):
    prob=calc_prob(seconds,u)
    roll=random.random()
    outcome="실패";cum=0.0
    for k,v in prob.items():
        cum+=v
        if roll<=cum: outcome=k;break
    if outcome=="실패":
        msg="🎣 뭔가가 걸렸다 !! 하지만 놓쳤습니다...\n"
    else:
        loc=u["location"];fishlist=FISH_POOL[loc][outcome]
        name,smin,smax=random.choice(fishlist); cm=random.randint(smin,smax)
        if outcome=="소형": price,exp=cm*1,cm*1
        elif outcome=="중형": price,exp=cm*100,cm*10
        else: price,exp=cm*1000,cm*100
        if loc=="민물": price=int(price*0.5);exp=int(exp*1.5)
        else: price=int(price*1.5);exp=int(exp*0.5)
        fish_obj={"name":name,"cm":cm,"grade":outcome,"price":price,
                  "location":loc,"caught_at":today_str()}
        u["fish"].append(fish_obj); add_exp(u,exp)
        msg=f"🎣 뭔가가 걸렸다 !!\n{name} {cm}cm ({outcome}) 낚음!\n가격:💰{price:,} | 경험치 +{exp} | 장소:{loc}\n"
    need=_bait_key_for(u["location"])
    if need: msg+=f"남은 {need}: {u['inventory'].get(need,0)}개"
    return msg

# -----------------------------
# 명령 처리
# -----------------------------
def handle_cmd(u, utt:str):
    t=(utt or "").strip()

    # 닉네임 미설정
    if not u["nick_locked"]:
        if t.startswith("/닉네임 "):
            nickname=t.replace("/닉네임 ","",1).strip()
            if not nickname: return "닉네임 설정 형식: /닉네임 원하는이름"
            u["nickname"]=nickname;u["nick_locked"]=True
            return f"닉네임이 '{nickname}'(으)로 설정되었습니다.\n이제 '/' 로 홈 화면을 확인해 보세요."
        if t=="/":
            return (
                "🎣 낚시 RPG에 오신 것을 환영합니다!\n"
                "반갑습니다 😊\n\n"
                "닉네임을 먼저 설정해 주세요.\n"
                "닉네임은 한 번 설정하면 변경할 수 없습니다.\n\n"
                "설정 방법: /닉네임 [원하는이름]\n"
                "예) /닉네임 홍길동"
            )
        return ""

    # 홈
    if t=="/":
        lines=[
            "🎣 낚시 RPG 사용법",
            "1) /장소 [바다|민물] ← 먼저 장소를 설정하세요",
            "2) /낚시 [1~60]s ← 해당 초 만큼 캐스팅 (예: /낚시 15s 또는 /낚시 15초)",
            "3) 시간이 끝나면 자동으로 결과 확인",
            "4) /기록 → 잡아본 물고기 확인",
            "",
            "🏪 상점 이용 방법",
            "/상점 → 상점 목록 보기",
            "/구매 [이름] [갯수] → 예: /구매 지렁이 10개",
            "/아이템판매 [이름] [수량] → 되팔기(구매가의 50%)",
            "",
            "(출석/보너스)",
            "/출석 → 출석 보상 받기",
            "/초보자찬스 → 낚린이 전용 보너스(1일 2회, 잔액 0일 때만 수령)",
            "",
            f"닉네임: [{get_title(u['level'])}] {u['nickname']}",
            f"[상태]\nLv.{u['level']}  Exp:{u['exp']}/{level_threshold(u['level'])}\n{fmt_money(u['gold'],u['restricted_gold'])}\n착용 낚싯대: {u['rod']}"
        ]
        return "\n".join(lines)

    # 장소
    if t.startswith("/장소"):
        parts=t.split()
        if len(parts)>=2 and parts[1] in ("바다","민물"):
            u["location"]=parts[1]
            if u["location"]=="바다":
                return "장소를 '바다'로 설정했습니다.\n💰 골드 1.5배 | EXP 0.5배"
            else:
                return "장소를 '민물'로 설정했습니다.\n💰 골드 0.5배 | EXP 1.5배"
        return "형식: /장소 [바다|민물]"

    # 낚시
    if t.startswith("/낚시"):
        raw=t.replace("/낚시","",1).strip().lower()
        num="" 
        for ch in raw:
            if ch.isdigit(): num+=ch
        if not num: return "낚시 시간은 숫자로 입력해 주세요."
        seconds=int(num)
        if seconds<=0 or seconds>60: return "낚시 시간은 1~60초"
        ok,msg=ensure_bait_and_consume(u)
        if not ok: return msg
        time.sleep(seconds)
        return handle_reel(u,seconds)

    return ""
# -----------------------------
# 라우팅
# -----------------------------
@app.get("/")
def health(): return "OK",200

@app.route("/skill",methods=["GET","POST"],strict_slashes=False)
@app.route("/skill/",methods=["GET","POST"],strict_slashes=False)
def skill():
    if request.method=="GET": return kakao_text(""),200
    body=request.get_json(silent=True) or {}
    user_req=body.get("userRequest",{})
    utter=(user_req.get("utterance") or "").strip()
    uid=user_req.get("user",{}).get("id") or "anonymous"
    if not is_allowed_command(utter): return kakao_text(""),200
    store=load_store(); u=get_user(store,uid)
    text=handle_cmd(u,utter); save_store(store)
    return kakao_text(text or ""),200

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)