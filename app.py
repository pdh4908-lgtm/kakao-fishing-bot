# app.py
import os, json, random
from datetime import datetime, time, date
from flask import Flask, request, jsonify

app = Flask(__name__)
DATA_PATH = os.environ.get("DATA_PATH", "data.json")

# -----------------------------
# 상수/정책
# -----------------------------
RESTRICTED_CAP = 1000   # 제한골드 최대 보유치
MAX_CONSUMABLE = 100    # 지렁이/떡밥 최대 보유 한도
BAG_CAP = 5             # 가방 칸 수

# -----------------------------
# 상점/아이템 정의
# -----------------------------
PRICES = {
    "지렁이": 10, "떡밥": 10, "집어제": 500,
    "케미라이트1등급": 600,
    "케미라이트2등급": 350,
    "케미라이트3등급": 200,
    "철제 낚싯대": 1000,
    "강화 낚싯대": 5000,
    "프로 낚싯대": 20000,
    "레전드 낚싯대": 100000,
}
CONSUMABLES = {"지렁이","떡밥","집어제","케미라이트1등급","케미라이트2등급","케미라이트3등급"}
RESTRICTED_ALLOWED = {"지렁이","떡밥"}

STRICT_CMDS = {
    "/", "/상점", "/전부판매", "/출석", "/초보자찬스",
    "/릴감기", "/판매확인", "/판매취소", "/기록",
    "/상태", "/가방"  # ← 추가
}
PREFIX_CMDS = {
    "/닉네임 ", "/구매 ", "/아이템판매 ", "/낚시 ", "/장소 ",
    "/케미라이트1등급 사용", "/케미라이트2등급 사용", "/케미라이트3등급 사용",
    "/집어제사용",
}

def is_allowed_command(text:str)->bool:
    if not text or not text.startswith("/"): return False
    if text in STRICT_CMDS: return True
    for p in PREFIX_CMDS:
        if text.startswith(p): return True
    return False

# -----------------------------
# 물고기 데이터 (민물/바다, 소형~대형)
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
    if not os.path.exists(DATA_PATH): return {"users":{}}
    try:
        with open(DATA_PATH,"r",encoding="utf-8") as f: return json.load(f)
    except: return {"users":{}}

def save_store(store):
    tmp=DATA_PATH+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(store,f,ensure_ascii=False,indent=2)
    os.replace(tmp,DATA_PATH)

def today_str(): return date.today().isoformat()

# -----------------------------
# 칭호/레벨
# -----------------------------
def get_title(lv:int)->str:
    if lv<=0: lv=1
    if lv<31: return "낚린이"
    elif lv<71: return "낚시인"
    elif lv<100: return "전문낚시인"
    else: return "프로"

def title_attendance_reward(title:str)->int:
    return {"낚린이":150,"낚시인":300,"전문낚시인":1000,"프로":3000}.get(title,0)

def level_threshold(lv:int)->int:
    return 100+50*(lv-1)

# -----------------------------
# 신규 유저
# -----------------------------
def get_user(store,uid):
    u=store["users"].get(uid)
    if u is None:
        u={"nickname":None,"nick_locked":False,"gold":0,"restricted_gold":0,"level":1,"exp":0,
           "rod":"철제 낚싯대","inventory":{},"fish":[],"attendance_last":None,
           "newbie":{"date":None,"count":0},"additive_uses":0,"pending_sale":None,
           "location":None,"records":{"min":None,"max":None},"casting":None,"active_buff":None}
        store["users"][uid]=u
    return u

# -----------------------------
# 유틸
# -----------------------------
def kakao_text(t): 
    return jsonify({"version":"2.0","template":{"outputs":[{"simpleText":{"text":t}}]}})

def fmt_money(g,r): return f"Gold: 💰{g:,} | 제한골드: 💰{r:,}"
def is_night(now=None): 
    now=now or datetime.now(); t=now.time()
    return (t>=time(20,0)) or (t<time(5,0))

def menu_text(u)->str:
    lines=[]
    lines.append(f"[{u.get('nickname') or '손님'}] {get_title(u['level'])} Lv.{u['level']}  EXP {u['exp']}/{level_threshold(u['level'])}")
    lines.append(fmt_money(u['gold'], u['restricted_gold']))
    lines.append(f"가방: {len(u['fish'])}/{BAG_CAP}칸 | 장소: {u['location'] or '미설정'}")
    lines.append("")
    lines.append("• 1줄: /상태, /가방")
    lines.append("• 2줄: /상점, /구매 [이름] [수량], /아이템판매 [이름] [수량], /전부판매")
    lines.append("• 3줄: /출석, /초보자찬스(낚린이 전용), /장소 [바다|민물], /낚시 [1~60]s, /릴감기, /기록")
    return "\n".join(lines)

# -----------------------------
# 확률 계산
# -----------------------------
def calc_prob(seconds:int,u)->dict:
    sec=min(seconds,60)
    base={"소형":0.30,"중형":0.01,"대형":0.00005}
    # 시간 보정
    base["소형"]+=0.10*(sec/60)
    base["중형"]+=0.01*(sec/60)
    base["대형"]+=0.00005*(sec/60)
    # 집어제 효과
    if u["additive_uses"]>0:
        base["중형"]+=0.02
        base["대형"]+=0.00005
        fail_before=1-sum(base.values())
        fail_after=fail_before*0.8
        base["실패"]=fail_after
    # 케미라이트 효과
    buff=u.get("active_buff")
    if buff=="케미라이트3등급":
        for k in ["소형","중형","대형"]: base[k]*=1.05
    elif buff=="케미라이트2등급":
        for k in ["소형","중형","대형"]: base[k]*=1.20
    elif buff=="케미라이트1등급":
        for k in ["소형","중형","대형"]: base[k]*=1.30
    total=sum(v for v in base.values() if v>0)
    base["실패"]=max(0.0,1.0-total)
    return base

# -----------------------------
# 낚시
# -----------------------------
def handle_cast(u,seconds:int):
    if not u.get("location"): return "⚠️ 먼저 /장소 [바다|민물] 을 설정하세요."
    if len(u["fish"])>=BAG_CAP: return "⚠️ 가방이 가득 찼습니다."
    u["casting"]={"seconds":seconds,"start":datetime.now().isoformat()}
    return f"{seconds}초 캐스팅 시작! 시간이 끝나면 /릴감기 로 확인하세요."

def handle_reel(u):
    if not u.get("casting"): return "⚠️ 캐스팅 기록이 없습니다."
    if len(u["fish"])>=BAG_CAP: return "⚠️ 가방이 가득 찼습니다."
    seconds=u["casting"]["seconds"]
    prob=calc_prob(seconds,u)
    roll=random.random(); outcome="실패"; cum=0.0
    for k,v in prob.items():
        cum+=v
        if roll<=cum: outcome=k; break
    if outcome=="실패": 
        u["casting"]=None
        return "🎣 낚시 실패..."
    loc=u["location"]; fishlist=FISH_POOL[loc][outcome]
    name,smin,smax=random.choice(fishlist); cm=random.randint(smin,smax)
    price=cm*(1 if outcome=="소형" else (100 if outcome=="중형" else 1000))
    exp=cm*(1 if outcome=="소형" else (10 if outcome=="중형" else 100))
    # 민물/바다 보정
    if loc=="민물": price=int(price*0.5); exp=int(exp*1.5)
    else: price=int(price*1.5); exp=int(exp*0.5)
    fish_obj={"name":name,"cm":cm,"grade":outcome,"price":price,"location":loc,"caught_at":today_str()}
    u["fish"].append(fish_obj); u["casting"]=None
    rec=u["records"]
    if rec["min"] is None or cm<rec["min"]["cm"]: rec["min"]=fish_obj
    if rec["max"] is None or cm>rec["max"]["cm"]: rec["max"]=fish_obj
    u["exp"]+=exp
    while u["exp"]>=level_threshold(u["level"]):
        u["exp"]-=level_threshold(u["level"]); u["level"]+=1
    return f"🎣 {name} {cm}cm ({outcome})!\n가격:💰{price} | EXP:+{exp}"

# -----------------------------
# 상태/가방
# -----------------------------
def handle_status(u)->str:
    lines = [
        f"[{u.get('nickname') or '손님'}] {get_title(u['level'])} Lv.{u['level']}  EXP {u['exp']}/{level_threshold(u['level'])}",
        fmt_money(u['gold'], u['restricted_gold']),
        f"장소: {u['location'] or '미설정'} | 낚싯대: {u.get('rod','미보유')}",
        f"가방: {len(u['fish'])}/{BAG_CAP}칸",
    ]
    return "\n".join(lines)

def handle_bag(u)->str:
    lines=[]
    if u["inventory"]:
        lines.append("🎒 보유 아이템")
        for name,qty in u["inventory"].items():
            tip=""
            if name.startswith("케미라이트"): tip=" (밤에 확률 소폭↑)"
            if name=="집어제": tip=" (중형/대형 확률 보정)"
            lines.append(f"- {name} ×{qty}{tip}")
    else:
        lines.append("🎒 보유 아이템 없음")
    if u["fish"]:
        lines.append("")
        lines.append("🪱 가방(잡은 물고기)")
        for f in u["fish"]:
            lines.append(f"- {f['name']} {f['cm']}cm | {f['location']} | {f['caught_at']} | 가격:{f['price']}")
    else:
        lines.append("")
        lines.append("🪱 가방에 물고기 없음")
    return "\n".join(lines)

# -----------------------------
# 거래 기능
# -----------------------------
def sell_all_fish(u):
    total=sum(f["price"] for f in u["fish"]); u["gold"]+=total; u["fish"].clear()
    return f"전부판매 완료: 💰{total:,}\n{fmt_money(u['gold'],u['restricted_gold'])}"

def start_resell(u,name,qty):
    if name not in PRICES: return "해당 아이템은 되팔 수 없습니다."
    have=u["inventory"].get(name,0)
    if qty<=0 or have<qty: return "수량이 부족합니다."
    refund=(PRICES[name]*qty)//2
    u["pending_sale"]={"name":name,"qty":qty,"refund":refund}
    return f"⚠️ 되팔기 {name}×{qty} → 환불 {refund}골드\n/판매확인 | /판매취소"

def confirm_resell(u,ok:bool):
    if not u.get("pending_sale"): return "대기 중인 되팔기 없음"
    if not ok: u["pending_sale"]=None; return "판매 취소"
    ps=u["pending_sale"]; u["inventory"][ps["name"]]-=ps["qty"]
    if u["inventory"][ps["name"]]<=0: u["inventory"].pop(ps["name"])
    u["gold"]+=ps["refund"]; u["pending_sale"]=None
    return f"판매 완료: +{ps['refund']}골드\n{fmt_money(u['gold'],u['restricted_gold'])}"

def try_buy(u,name,qty):
    if name not in PRICES: return False,"존재하지 않는 상품"
    if qty<=0: return False,"수량 오류"
    total=PRICES[name]*qty
    if name in RESTRICTED_ALLOWED:
        use_restricted=min(u["restricted_gold"],total); remain=total-use_restricted
        if remain>u["gold"]: return False,"골드 부족"
        u["gold"]-=remain; u["restricted_gold"]-=use_restricted
    else:
        if total>u["gold"]: return False,"골드 부족"
        u["gold"]-=total
    u["inventory"][name]=u["inventory"].get(name,0)+qty
    return True,f"{name}×{qty} 구매 완료!\n{fmt_money(u['gold'],u['restricted_gold'])}"

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
    user_req=body.get("userRequest",{}); utt=(user_req.get("utterance") or "").strip()
    uid=user_req.get("user",{}).get("id") or "anon"
    if not is_allowed_command(utt): return kakao_text(""),200
    store=load_store(); u=get_user(store,uid)
    text=""

    # 닉네임
    if not u["nick_locked"]:
        if utt.startswith("/닉네임 "):
            nickname=utt.replace("/닉네임 ","",1).strip()
            u["nickname"]=nickname; u["nick_locked"]=True
            text=f"닉네임 '{nickname}' 설정 완료!"
        elif utt=="/":
            text="닉네임을 먼저 설정하세요. /닉네임 [이름]"
        else:
            text=""
    else:
        # 닉네임 설정 완료 유저의 '/' → 메인 메뉴
        if utt=="/":
            text = menu_text(u)
        elif utt.startswith("/낚시"):
            try:
                sec=int(''.join(ch for ch in utt if ch.isdigit()))
                text=handle_cast(u,sec)
            except:
                text="형식: /낚시 [1~60]s"
        elif utt=="/릴감기":
            text=handle_reel(u)
        elif utt=="/출석":
            today=today_str()
            if u["attendance_last"]==today:
                text="이미 출석함"
            else:
                u["attendance_last"]=today
                title=get_title(u["level"])
                reward=title_attendance_reward(title)
                if title=="낚린이":
                    before=u["restricted_gold"]; after=min(RESTRICTED_CAP,before+reward); gained=after-before
                    u["restricted_gold"]=after
                    text="제한골드 상한" if gained==0 else f"출석보상 {gained} 지급"
                else:
                    u["restricted_gold"]+=reward
                    text=f"출석보상 {reward} 지급"
        elif utt=="/전부판매":
            text=sell_all_fish(u)
        elif utt=="/판매확인":
            text=confirm_resell(u,True)
        elif utt=="/판매취소":
            text=confirm_resell(u,False)
        elif utt.startswith("/아이템판매"):
            parts=utt.split()
            if len(parts)<3:
                text="형식: /아이템판매 [이름] [수량]"
            else:
                name=" ".join(parts[1:-1]); qty=int(parts[-1]); text=start_resell(u,name,qty)
        elif utt.startswith("/구매 "):
            parts=utt.split()
            if len(parts)<3:
                text="형식: /구매 [이름] [수량]"
            else:
                name=" ".join(parts[1:-1]); qty=int(parts[-1]); ok,msg=try_buy(u,name,qty); text=msg
        elif utt=="/기록":
            rec=u["records"]; mn=rec.get("min"); mx=rec.get("max"); lines=[]
            lines.append(f"[최대] {mx['name']} {mx['cm']}cm ({mx['grade']}) - {mx['location']}" if mx else "[최대] 기록 없음")
            lines.append(f"[최소] {mn['name']} {mn['cm']}cm ({mn['grade']}) - {mn['location']}" if mn else "[최소] 기록 없음")
            if u["fish"]:
                lines.append("📜 잡은 물고기 기록")
                seen=set()
                for f in u["fish"]:
                    if f["name"] not in seen:
                        seen.add(f["name"])
                        lines.append(f"- {f['name']} {f['cm']}cm | {f['location']} | {f['caught_at']}")
            else:
                lines.append("기록 없음")
            text="\n".join(lines)
        elif utt.startswith("/장소"):
            parts=utt.split()
            if len(parts)>=2 and parts[1] in ("바다","민물"):
                u["location"]=parts[1]; text=f"장소 {u['location']} 설정 완료"
            else:
                text="형식: /장소 [바다|민물]"
        elif utt=="/상태":
            text = handle_status(u)
        elif utt=="/가방":
            text = handle_bag(u)

    save_store(store)
    return kakao_text(text or ""),200

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
