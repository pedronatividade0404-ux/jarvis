import os,time,uuid,json,httpx
from fastapi import FastAPI,Header,HTTPException,UploadFile,File
from pydantic import BaseModel

app=FastAPI(
    title="JARVIS Cloud",
    version="10.1",
    description="Cloud API do JARVIS"
)
TOKEN=os.getenv("JARVIS_TOKEN","dev-token")
KEY=os.getenv("GROQ_API_KEY","")
MODEL=os.getenv("GROQ_MODEL","openai/gpt-oss-120b")
STT_MODEL=os.getenv("GROQ_STT_MODEL","whisper-large-v3-turbo")

devices={}; events=[]; chats={}; improvements=[]; routines=[]; commands={}

def auth(a):
    if a!=f"Bearer {TOKEN}": raise HTTPException(401,"Token inválido")

class HB(BaseModel):
    device_id:str; kind:str; name:str; data:dict={}
class Chat(BaseModel):
    device_id:str="mobile"; text:str
class Event(BaseModel):
    source:str; type:str; data:dict={}
class Improvement(BaseModel):
    title:str; reason:str; risk:str="low"
class Routine(BaseModel):
    name:str; trigger:str; actions:list[dict]
class Command(BaseModel):
    target:str; action:str; args:dict={}

@app.get("/")
def root():
    return {
        "ok": True,
        "name": "JARVIS Cloud",
        "version": "10.1",
        "docs": "/docs",
        "health": "/api/health"
    }

@app.get("/api")
def api_root():
    return {"ok": True, "service": "JARVIS Cloud API", "version": "10.1"}

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "groq_configured": bool(KEY),
        "jarvis_token_configured": TOKEN != "dev-token",
        "model": MODEL,
        "stt_model": STT_MODEL
    }

@app.post("/api/device/heartbeat")
def hb(x:HB,authorization:str|None=Header(None)):
    auth(authorization)
    devices[x.device_id]={"device_id":x.device_id,"kind":x.kind,"name":x.name,"data":x.data,"last_seen":time.time()}
    return {"ok":True}

@app.get("/api/devices")
def dev(authorization:str|None=Header(None)):
    auth(authorization); now=time.time()
    return [{**x,"online":now-x["last_seen"]<45} for x in devices.values()]

@app.post("/api/events")
def event(x:Event,authorization:str|None=Header(None)):
    auth(authorization)
    item={"id":str(uuid.uuid4()),"ts":time.time(),**x.model_dump()}
    events.append(item); del events[:-500]
    return item

@app.get("/api/events")
def get_events(since:float=0,authorization:str|None=Header(None)):
    auth(authorization); return [e for e in events if e["ts"]>since][-200:]

@app.post("/api/chat")
async def chat(x:Chat,authorization:str|None=Header(None)):
    auth(authorization)
    if not KEY: raise HTTPException(500,"GROQ_API_KEY não configurada")
    h=chats.setdefault(x.device_id,[])
    h.append({"role":"user","content":x.text}); h[:]=h[-20:]
    system={"role":"system","content":(
        "Você é JARVIS, assistente doméstico em português do Brasil. Responda de forma curta e natural para voz. "
        "Nunca diga que executou uma ação física sem confirmação do dispositivo. "
        "Se o pedido for para controlar PC, TV, música, mapa ou rotina, explique brevemente o resultado recebido do dispositivo."
    )}
    ctx={"role":"system","content":f"Estado atual dos dispositivos: {json.dumps(list(devices.values()),ensure_ascii=False)}"}
    async with httpx.AsyncClient(timeout=60) as c:
        r=await c.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"},
            json={"model":MODEL,"messages":[system,ctx]+h,"temperature":0.35})
    if r.status_code>=400: raise HTTPException(r.status_code,r.text)
    ans=r.json()["choices"][0]["message"]["content"]
    h.append({"role":"assistant","content":ans}); h[:]=h[-20:]
    return {"text":ans,"model":MODEL}

@app.post("/api/stt")
async def stt(audio:UploadFile=File(...),authorization:str|None=Header(None)):
    auth(authorization)
    if not KEY: raise HTTPException(500,"GROQ_API_KEY não configurada")
    raw=await audio.read()
    async with httpx.AsyncClient(timeout=90) as c:
        r=await c.post("https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization":f"Bearer {KEY}"},
            data={"model":STT_MODEL,"language":"pt","response_format":"json"},
            files={"file":(audio.filename or "audio.webm",raw,audio.content_type or "audio/webm")})
    if r.status_code>=400: raise HTTPException(r.status_code,r.text)
    return r.json()

@app.post("/api/commands")
def enqueue(x:Command,authorization:str|None=Header(None)):
    auth(authorization)
    item={"id":str(uuid.uuid4()),"ts":time.time(),"status":"pending",**x.model_dump()}
    commands.setdefault(x.target,[]).append(item)
    return item

@app.get("/api/commands/{target}")
def poll_commands(target:str,authorization:str|None=Header(None)):
    auth(authorization)
    q=commands.setdefault(target,[])
    out=[x for x in q if x["status"]=="pending"][:20]
    for x in out: x["status"]="delivered"
    return out

@app.post("/api/routines")
def add_routine(x:Routine,authorization:str|None=Header(None)):
    auth(authorization)
    item={"id":str(uuid.uuid4()),"enabled":True,**x.model_dump()}
    routines.append(item); return item

@app.get("/api/routines")
def list_routines(authorization:str|None=Header(None)):
    auth(authorization); return routines

@app.get("/api/geocode")
async def geocode(q:str,authorization:str|None=Header(None)):
    auth(authorization)
    async with httpx.AsyncClient(timeout=20,headers={"User-Agent":"JARVIS-V6/1.0"}) as c:
        r=await c.get("https://nominatim.openstreetmap.org/search",params={"q":q,"format":"json","limit":5})
    return r.json()

@app.get("/api/route")
async def route(from_lat:float,from_lon:float,to_lat:float,to_lon:float,authorization:str|None=Header(None)):
    auth(authorization)
    url=f"https://router.project-osrm.org/route/v1/driving/{from_lon},{from_lat};{to_lon},{to_lat}"
    async with httpx.AsyncClient(timeout=25) as c:
        r=await c.get(url,params={"overview":"full","geometries":"geojson","steps":"true","alternatives":"true"})
    return r.json()

@app.post("/api/improvements")
def improve(x:Improvement,authorization:str|None=Header(None)):
    auth(authorization)
    item={"id":str(uuid.uuid4()),"status":"pending","created_at":time.time(),**x.model_dump()}
    improvements.append(item); return item

@app.get("/api/improvements")
def get_improvements(authorization:str|None=Header(None)):
    auth(authorization); return improvements[-100:]
