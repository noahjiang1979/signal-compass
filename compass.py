#!/usr/bin/env python3
import requests,json,os,datetime,statistics,sys,re,subprocess,random,time

def _app_dir():
  """兼容直接运行和 PyInstaller 打包：返回数据文件所在目录（exe/脚本同级）"""
  if getattr(sys,'frozen',False):
    return os.path.dirname(sys.executable)
  return os.path.dirname(os.path.abspath(__file__))

# Windows 终端输出 UTF-8（支持 emoji）
if sys.platform=='win32':
  try:sys.stdout.reconfigure(encoding='utf-8')
  except:pass

# emoji fallback: 终端不支持 UTF-8 emoji 时降级为 ASCII
_EMOJI_FALLBACK=None
def _sf(s):
  """Safe-encode string: replace emoji if terminal can't render them"""
  global _EMOJI_FALLBACK
  if _EMOJI_FALLBACK is None:
    try:'🔴'.encode(sys.stdout.encoding or 'utf-8')
    except(UnicodeEncodeError,LookupError):_EMOJI_FALLBACK=True
    else:_EMOJI_FALLBACK=False
  if not _EMOJI_FALLBACK:return s
  m={'🔴':'(R)','🟡':'(Y)','🟢':'(G)','⭐':'*','⬜':'[-]','🔒':'[质]','👎':'[空]','👍':'[好]','✅':'[OK]','❌':'[NO]'}
  for k,v in m.items():s=s.replace(k,v)
  return s
_orig_print=print
def _print(*a,**kw):
  _orig_print(*[(_sf(str(x)) if isinstance(x,str) else x) for x in a],**kw)
print=_print

G="\U0001f7e2";Y="\U0001f7e1";R="\U0001f534";W="\u2b1c";B="\u26a1"
S="\u2550"*50;HR="\u2500"*40
H={"User-Agent":"Mozilla/5.0","Referer":"https://finance.sina.com.cn"}
SQ="https://hq.sinajs.cn/list={}"
U={"SPY":"gb_spy","QQQ":"gb_qqq","VIXY":"gb_vixy","DJI":"gb_dji"}
M={"AAPL":"gb_aapl","MSFT":"gb_msft","GOOGL":"gb_googl","AMZN":"gb_amzn","NVDA":"gb_nvda","META":"gb_meta","TSLA":"gb_tsla"}
SX={"DIA":"gb_dia","XLE":"gb_xle","IWM":"gb_iwm","XLF":"gb_xlf","XLK":"gb_xlk","XLI":"gb_xli","SOX":"gb_sox"}
A={"SS":"sh000001","SZ":"sz399001","HS":"sz399300","CY":"sz399006","STAR50":"sh000688","CSI500":"sh000905"}
# --- 静态满分常量（双轨制） ---
US_TREND_MAX=12   # 趋势压力（胜率）：MA破位/成交量/Mag7/板块轮动/叙事
US_EXTREME_MAX=3  # 偏离极值（赔率）：RSI超买/分位数
US_TOTAL_MAX=US_TREND_MAX+US_EXTREME_MAX  # =15
A_TREND_MAX=8     # A股趋势压力
A_EXTREME_MAX=4   # A股偏离极值
A_TOTAL_MAX=A_TREND_MAX+A_EXTREME_MAX  # =12
def now():return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
def hdr(t):print();print("  "+t);print("  "+HR)
def dma(pv,n):
  if not pv or len(pv)<n:return None
  return sum(pv[-n:])/n
def rsi(pv,n=14):
  if not pv or len(pv)<n+1:return None
  g=l=0
  for i in range(-n,0):
    c=pv[i]-pv[i-1]
    if c>=0:g+=c
    else:l-=c
  a=g/n;b=l/n
  return 100 if b==0 else 100-100/(1+a/b)
def pct_rank(val,arr):
  if not arr:return None
  return sum(1 for x in arr if x<val)/len(arr)*100
def market_amount():
  """全市场成交额(沪深), 返回亿. 使用SSE日结+SZSE概况"""
  try:
    import akshare as ak
    sse=ak.stock_sse_deal_daily()
    sv=float(sse[sse["单日情况"]=="成交金额"]["股票"].values[0])
    szse=ak.stock_szse_summary()
    szv=float(szse[szse["证券类别"]=="股票"]["成交金额"].values[0])/1e8
    return round(sv+szv,0)
  except:return None
def _pick_benchmark(code, ba_chg, cy_chg, star50_chg):
  """按代码前缀选基准: 688→科创50, 300/301→创业板, 其余→上证"""
  num=code[2:] if code.startswith(("sh","sz")) else code
  if num.startswith("688") and star50_chg is not None:return star50_chg
  if num.startswith(("300","301")) and cy_chg is not None:return cy_chg
  return ba_chg

def _benchmark_label(code):
  """返回基准缩写: 沪/科创/创"""
  num=code[2:] if code.startswith(("sh","sz")) else code
  if num.startswith("688"):return "科创"
  if num.startswith(("300","301")):return "创"
  return "沪"

STYLE_CACHE=os.path.join(_app_dir(),"style_cache.json")

def get_style_ratio():
  """科创综指/沪深300成交额比率, 返回 (star_amt, hs300_amt, pct) 或 None"""
  try:
    url="https://hq.sinajs.cn/list=sh000680,sh000300"
    r=requests.get(url,headers=H,timeout=10);r.encoding="gbk"
    star_amt=None;hs300_amt=None
    for ln in r.text.strip().split(chr(10)):
      m=__import__("re").match(r'var hq_str_(\w+)="(.*)";',ln)
      if not m:continue
      parts=m.group(2).split(",")
      if m.group(1)=="sh000680" and len(parts)>9:
        star_amt=float(parts[9])/1e8
      elif m.group(1)=="sh000300" and len(parts)>9:
        hs300_amt=float(parts[9])/1e8
    if star_amt and hs300_amt and hs300_amt>0:
      return (round(star_amt,0),round(hs300_amt,0),round(star_amt/hs300_amt*100,1))
    return None
  except:return None

def save_style_cache(star_amt,hs300_amt,pct):
  """保存今日风格成交额到缓存"""
  try:
    today=datetime.date.today().strftime("%Y-%m-%d")
    cache={}
    if os.path.exists(STYLE_CACHE):
      with open(STYLE_CACHE,"r",encoding="utf-8") as f:cache=json.load(f)
    cache[today]={"star":star_amt,"hs300":hs300_amt,"pct":pct}
    with open(STYLE_CACHE,"w",encoding="utf-8") as f:json.dump(cache,f)
  except:pass

def load_style_cache(days=5):
  """加载最近N天风格成交额历史"""
  try:
    if not os.path.exists(STYLE_CACHE):return []
    with open(STYLE_CACHE,"r",encoding="utf-8") as f:cache=json.load(f)
    items=[(d,v) for d,v in sorted(cache.items(),reverse=True)[:days]]
    return items
  except:return []

def sina_k(sym,days=35):
  """A股日K线 — 返回 {c:[], h:[], l:[], v:[]}"""
  try:
    u="http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={}&scale=240&ma=no&datalen={}".format(sym,days)
    r=requests.get(u,headers=H,timeout=10)
    if r.status_code!=200:return None
    dt=json.loads(r.text.strip())
    if not dt:return None
    cs=[float(d["close"]) for d in dt if d.get("close")]
    hs=[float(d["high"]) for d in dt if d.get("high")]
    ls=[float(d["low"]) for d in dt if d.get("low")]
    vs=[float(d["volume"]) for d in dt if d.get("volume")] if "volume" in dt[0] else None
    return {"c":cs,"h":hs,"l":ls,"v":vs}
  except:return None

def is_trading():
  """A股交易时段判断"""
  n=datetime.datetime.now()
  h,m=n.hour,n.minute
  # 上午9:31~11:30, 下午13:01~15:00
  return (h==9 and m>=31) or (h==10) or (h==11 and m<=30) or (h>=13 and h<=14) or (h==15 and m==0)

# --- 复盘自动存档 ---
REVIEW_DIR=os.path.join(_app_dir(),"review")
def save_daily_review(data):
  now=datetime.datetime.now()
  mk=now.strftime("%Y%m");dk=now.strftime("%Y%m%d")
  if not os.path.exists(REVIEW_DIR):os.makedirs(REVIEW_DIR)
  fp=os.path.join(REVIEW_DIR,mk+".json")
  reviews={}
  if os.path.exists(fp):
    with open(fp,"r",encoding="utf-8") as f:reviews=json.load(f)
  data["_ts"]=now.strftime("%Y-%m-%d %H:%M")
  reviews[dk]=data
  with open(fp,"w",encoding="utf-8") as f:json.dump(reviews,f,indent=2,ensure_ascii=False)

def get_today_note():
  """检查今天是否已有笔记（避免重复弹input）"""
  now=datetime.datetime.now()
  dk=now.strftime("%Y%m%d");mk=now.strftime("%Y%m")
  fp=os.path.join(REVIEW_DIR,mk+".json")
  if not os.path.exists(fp):return None
  try:
    with open(fp,"r",encoding="utf-8") as f:r=json.load(f)
    if dk in r and r[dk].get("note"):
      n=r[dk]["note"]
      # 只有纯标签（[涨]/[跌]/[平]）不算有效笔记
      if n.strip() not in ("[涨]","[跌]","[平]"):
        return n
  except:pass
  return None

def get_yesterday_note(mode=None):
  now=datetime.datetime.now()
  yd=(now-datetime.timedelta(days=1)).strftime("%Y%m%d")
  mk=(now-datetime.timedelta(days=1)).strftime("%Y%m")
  fp=os.path.join(REVIEW_DIR,mk+".json")
  if not os.path.exists(fp):return None
  try:
    with open(fp,"r",encoding="utf-8") as f:r=json.load(f)
    if yd in r and r[yd].get("note"):
      if mode and r[yd].get("mode")!=mode:return None
      return r[yd]["note"]
  except:pass
  return None

# --- 北向资金 JSON 缓存（3日累计） ---
CACHE_FILE=os.path.join(_app_dir(),"northbound_cache.json")
def save_nb_cache(flow):
  """存入今日北向资金(带抓取时间戳), 自动清理7天前旧数据"""
  today=datetime.datetime.now().strftime("%Y-%m-%d")
  cache={}
  if os.path.exists(CACHE_FILE):
    try:
      with open(CACHE_FILE,"r") as f:cache=json.load(f)
    except:cache={}
  if flow is not None and abs(flow)>0.1:
    cache[today]={"v":round(flow,1),"t":datetime.datetime.now().strftime("%H:%M")}
  cutoff=(datetime.datetime.now()-datetime.timedelta(days=7)).strftime("%Y-%m-%d")
  cache={d:v for d,v in cache.items() if d>=cutoff}
  with open(CACHE_FILE,"w") as f:json.dump(cache,f,indent=2,ensure_ascii=False)

def nb_val(entry):
  """兼容新旧缓存格式: entry 可能是 {"v":X,"t":"HH:MM"} 或 纯float"""
  if isinstance(entry,dict):return entry.get("v",0)
  return entry

def nb_time(entry,fallback=""):
  """取时间戳"""
  if isinstance(entry,dict):return entry.get("t",fallback)
  return fallback

def get_nb_3d():
  """最近3个交易日累计北向资金净流入(亿元). 从缓存取最近2~3天"""
  if not os.path.exists(CACHE_FILE):return None
  try:
    with open(CACHE_FILE,"r") as f:cache=json.load(f)
  except:return None
  valid=[(d,v) for d,v in sorted(cache.items(),reverse=True) if abs(nb_val(v))>0.1]
  if len(valid)<1:return None
  last3=valid[:min(3,len(valid))]
  total=round(sum(nb_val(v) for _,v in last3),1)
  return total,last3[-1][0]

def north_b():
  """北向资金今日净流入(亿元) from akshare. 2024年8月起官方每日披露已停"""
  try:
    import akshare as ak
    df=ak.stock_hsgt_fund_flow_summary_em()
    nb=df[df['资金方向']=='北向']['成交净买额']
    total=nb.sum()
    flow=round(total,1) if total is not None else None
    save_nb_cache(flow)
    return flow
  except:
    return None

def nb_yesterday():
  """从缓存取最近一个有效日期的北向数据(用于盘中替代今日NaN)"""
  if not os.path.exists(CACHE_FILE):return None
  try:
    with open(CACHE_FILE,"r") as f:cache=json.load(f)
  except:return None
  recent=[(d,v) for d,v in sorted(cache.items(),reverse=True) if abs(nb_val(v))>0.1]
  if not recent:return None
  d,v=recent[0]
  return (d,nb_val(v),nb_time(v))

def south_b():
  """南向资金(港股通)今日净买入(亿元). 东财实时接口 (盘中可用)"""
  try:
    u="https://push2.eastmoney.com/api/qt/kamtbs.rtmin/get"
    p={"fields1":"f1,f2,f3,f4","fields2":"f51,f54,f52,f58,f53,f62,f56,f57,f60,f61",
       "ut":"b2884a393a59ad64002292a3e90d46a5"}
    r=requests.get(u,params=p,headers=H,timeout=8)
    d=r.json()["data"]
    n2s=d["n2s"]
    # 取最新一条非空数据
    for row in reversed(n2s):
      parts=row.split(",")
      if len(parts)>=6 and parts[5]!="0.00" and parts[5]!="-":
        total=float(parts[5])/10000  # 万元→亿元
        sh=float(parts[1])/10000
        sz=float(parts[3])/10000
        return {"total":round(total,1),"sh":round(sh,1),"sz":round(sz,1),"time":parts[0]}
    return None
  except:
    return None

def china_10y():
  """中国10年期国债收益率(%)(最新) from akshare bond_zh_us_rate + 日级缓存"""
  today=datetime.date.today().strftime("%Y-%m-%d")
  cf=os.path.join(_app_dir(),"10y_cache.json")
  # 读缓存
  if os.path.exists(cf):
    try:
      with open(cf,"r") as f:
        c10=json.load(f)
      if c10.get("date")==today and c10.get("yield") is not None:
        return c10["yield"]
    except:pass
  # 拉取
  try:
    import akshare as ak, contextlib
    with open(os.devnull,'w') as _nul,contextlib.redirect_stderr(_nul):
      df=ak.bond_zh_us_rate()
    latest=round(float(df.iloc[-1]["中国国债收益率10年"]),3)
    with open(cf,"w") as f:json.dump({"date":today,"yield":latest},f)
    return latest
  except:
    return None

def get_zt_data(date_str):
  """涨停板分布: 首板/一进二/最高连板/热点板块 top3"""
  try:
    import akshare as ak
    df=ak.stock_zt_pool_em(date=date_str)
    if df.empty:return None
    df=df[~df["名称"].str.contains("ST|[*]ST|N|C",na=False)]
    if df.empty:return None
    total=len(df)
    first=int((df["连板数"]==1).sum())
    second=int((df["连板数"]==2).sum())
    max_b=int(df["连板数"].max())
    top3=df["所属行业"].value_counts().head(3)
    sectors=["{} ({})".format(s,int(c)) for s,c in top3.items()]
    return {"total":total,"first":first,"second":second,"max":max_b,"sectors":sectors}
  except:
    return None

def sina_q(syms):
  url=SQ.format(','.join(syms))
  r=requests.get(url,headers=H,timeout=10);r.encoding="gbk";res={}
  for ln in r.text.strip().split(chr(10)):
    m=re.match(r"var hq_str_(\w+)=\"(.*)\";",ln)
    if not m:continue
    k,v=m.group(1),m.group(2).split(",")
    if len(v)<6:res[k]=None;continue
    try:
      if k[:3]=="gb_":
        res[k]={"p":float(v[1]),"chg":float(v[2])}
      elif k in ("sh000001","sh000688","sh000300","sh000905","sh000016","sz399001","sz399006","sz399005","sz399678"):
        # A股指数格式: v[1]=今开 v[2]=昨收 v[3]=收盘
        pr=float(v[3]) if v[3] else None;pc=float(v[2]) if v[2] else None
        res[k]={"p":pr,"chg":0 if not(pr and pc) else (pr-pc)/pc*100,"vol":int(v[8]) if v[8] else 0}
      else:
        # A股个股/ETF格式: v[3]=当前价 v[2]=昨收
        pr=float(v[3]) if v[3] else None
        pc=float(v[2]) if v[2] else None
        res[k]={"p":pr,"chg":0 if not(pr and pc) else (pr-pc)/pc*100,"name":v[0]}
    except:res[k]=None
  return res
def yahoo_c(sym,period="1y"):
  try:
    url="https://query1.finance.yahoo.com/v8/finance/chart/"+sym+"?interval=1d&range="+period
    r=requests.get(url,headers=H,timeout=10)
    if r.status_code!=200:return None
    x=r.json()["chart"]["result"][0]
    cs=[c for c in x["indicators"]["quote"][0]["close"] if c]
    vs=[v for v in x["indicators"]["quote"][0]["volume"] if v]
    return {"c":cs,"v":vs} if cs else None
  except:return None
def yc():
  try:
    t=requests.get("https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?interval=1d&range=5d",headers=H,timeout=10)
    s=requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2YY%3DF?interval=1d&range=5d",headers=H,timeout=10)
    if t.status_code!=200:return None
    tn=[c for c in t.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
    if s.status_code==200:
      ir=[c for c in s.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
      if tn and ir:return {"spread":tn[-1]-ir[-1],"label":"10Y-2Y","source":"2YY"}
    f=requests.get("https://query1.finance.yahoo.com/v8/finance/chart/%5EFVX?interval=1d&range=5d",headers=H,timeout=10)
    if f.status_code!=200:return None
    fv=[c for c in f.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
    if tn and fv:return {"spread":tn[-1]-fv[-1],"label":"10Y-5Y","source":"FVX"}
  except:return None
  return None
def ddg(q,n=2):
  r=subprocess.run(['ddgs','text','-q',q,'-m',str(n)],capture_output=True,text=True,timeout=15)
  if r.returncode or not r.stdout.strip():return None
  ts=[]
  for ln in r.stdout.splitlines():
    if ln.startswith("title"):
      ts.append(ln[6:].strip())
  return ts[:n] if ts else None
def run_us():
  hdr("Hermes Signal Compass - US Mode - "+now())
  yn=get_yesterday_note("us")
  if yn:print("  \U0001f58b 昨日笔记：{}".format(yn))
  q=sina_q(list(U.values())+list(M.values())+list(SX.values()))
  yi=yahoo_c("SPY","1y"); yi5=yahoo_c("SPY","5y")  # 5y for percentile
  yr=yc()
  ns=ddg("Michael Burry short AI bearish SPY hedge",2)
  print("  === US Signal Map ===")
  risk=[];trend_score=0;extreme_score=0;yc_mult=1.0  # 双轨: 趋势压力/偏离极值
  # SPY技术面变量预初始化, 防yi=None时下游未定义
  pc=None;pchg=None;d20=None;d50=None;r=None;rsi_hist=None;v_ratio=None
  iperf=None; sperf=None; eperf=None  # 板块轮动变量, 在if块外使用
  # --- 1. SPY 技术面 ---
  if yi:
    d20=dma(yi["c"],20);d50=dma(yi["c"],50);d200=dma(yi["c"],200);r=rsi(yi["c"])
    pc=yi["c"][-1];pc0=yi["c"][-2];pchg=(pc-pc0)/pc0*100
    v20=dma(yi["v"],20) if len(yi["v"])>=20 else None
    v_ratio=yi["v"][-1]/v20 if v20 and v20>0 else None
    # 历史分位数: 用5y数据算RSI百分位
    rsi_hist=None
    if yi5:
      r_all=[]
      for i in range(14,len(yi5["c"])):
        rv=rsi(yi5["c"][:i+1],14)
        if rv is not None:r_all.append(rv)
      rsi_hist=pct_rank(r,r_all)
    print("  SPY {}{:.2f} ({:+.2f}%) 20MA {:.2f} 50MA {:.2f} 200MA {:.2f} RSI {:.1f} ({}%分位)".format(
      B if r>65 else "",pc,pchg,d20,d50,d200,r,
      "{:.0f}".format(rsi_hist) if rsi_hist is not None else "N/A"))
    if v_ratio:print("  成交量: 今日/20日均 = {:.2f}x".format(v_ratio))
    ls=[]
    if r>65:ls.append("RSI超买")
    if r>70:ls.append("警戒")
    # RSI超买→偏离极值(赔率维度)
    if r>70:extreme_score+=2;ls.append("RSI>70")
    elif r>65:extreme_score+=1
    # SPY跌破20MA→趋势压力(胜率维度)
    if pc<d20:trend_score+=2;risk.append("破20MA");ls.append("跌破20MA")
    # 成交量放大→趋势压力(胜率维度)
    if v_ratio and v_ratio>1.2:trend_score+=2;risk.append("放量");ls.append("放量下跌")
    print("  {} 趋势: {}".format(R if r>70 else Y if r>65 else G,", ".join(ls) if ls else "正常"))
  else:
    print("  SPY [无数据]")

  # --- 2. Mag7 个股 ---
  print("  Mag7 个股:")
  ups=[];downs=[];changes=[]
  for sym,code in sorted(M.items()):
    d=q.get(code)
    if d and d.get("p"):
      c=d["chg"];changes.append(c)
      if c>0:ups.append(sym)
      elif c<0:downs.append(sym)
      print("    {} {:+.2f}%".format(sym,c))
    else:
      print("    {} [无数据]".format(sym))
  n_up=len(ups);n_down=len(downs)
  mag7_std=statistics.stdev(changes) if len(changes)>=2 else 0
  print("  Mag7: {}涨 {}跌{} 标准差{:.2f}%".format(n_up,n_down,R if n_down>=5 else Y if n_down>=3 else G,mag7_std))
  if n_down>=5:trend_score+=2;risk.append("Mag7普跌")
  elif n_down>=3:trend_score+=1;risk.append("Mag7分化")
  if mag7_std>2:trend_score+=1;risk.append("Mag7分歧大")

  # --- 3. 板块轮动矩阵 ---
  sp=q.get("gb_spy");qq=q.get("gb_qqq");dj=q.get("gb_dji")
  dia=q.get("gb_dia");sox=q.get("gb_sox");xle=q.get("gb_xle")
  iwm=q.get("gb_iwm")
  if dia and qq and qq.get("chg") is not None and dia.get("chg") is not None:
    perf=dia["chg"]-qq["chg"]
    print("  DIA-QQQ 涨跌幅差: {:+.2f}% (正=价值跑赢成长)".format(perf))
    if perf>1:trend_score+=1;risk.append("价值>成长轮动")
  if sox and qq and qq.get("chg") is not None and sox.get("chg") is not None:
    sperf=sox["chg"]-qq["chg"]
    print("  SOX-QQQ 涨跌幅差: {:+.2f}% {} (负=半导体跑输)".format(sperf,R if sperf<-2 else Y if sperf<-1 else G))
    if sperf<-2:trend_score+=1.5;risk.append("半导体走弱")
    elif sperf<-1:trend_score+=1;risk.append("半导体偏弱")
  if xle and qq and qq.get("chg") is not None and xle.get("chg") is not None:
    eperf=xle["chg"]-qq["chg"]
    print("  XLE-QQQ 涨跌幅差: {:+.2f}% {} (正=资金避险)".format(eperf,R if eperf>2 else G))
    if eperf>2:trend_score+=1;risk.append("资金避险")
  if iwm and sp and sp.get("chg") is not None and iwm.get("chg") is not None:
    iperf=iwm["chg"]-sp["chg"]
    print("  IWM-SPY 涨跌幅差: {:+.2f}% {} (负=小盘跑输)".format(iperf,R if iperf<-0.5 else G))
    if iperf<-0.5:trend_score+=1;risk.append("小盘跑输")
  if dj and dj.get("p"):
    print("  道指 {:.2f} ({:+.2f}%)".format(dj["p"],dj["chg"]))
    # 不重复计分
    if dj["chg"]>0 and n_up<4:
      print("  板块轮动: 道指涨+Mag7偏弱 -> 资金向防御/能源/金融转移")
      if "板块轮动" not in risk:risk.append("板块轮动")

  # --- 4. VIX/QQQ ---
  for sk,sn in [("VIXY","VIXY"),("QQQ","QQQ")]:
    d=q.get(U[sk])
    if d and d.get("p"):
      print("  {} {:.2f} ({:+.2f})".format(sn,d["p"],d["chg"]))
    else:
      print("  {} [无数据]".format(sn))

  # --- 5. 收益率曲线 ---
  if yr is not None:
    print("  {}({}): {:.2f}%".format(yr["label"],yr["source"],yr["spread"]))
    if yr["spread"]>0.7:
      yc_mult=1.2;risk.append("利差偏高→全局×1.2")
    else:
      yc_mult=1.0
  else:
    print("  收益率差: [无数据]")

  # --- 6. 叙事 ---
  if ns:
    print("  叙事信号: {} | {}".format(ns[0],ns[1] if len(ns)>1 else ""))
    trend_score+=1;risk.append("叙事偏空")
  else:
    print("  叙事信号: [无]")

  # --- 7. 判定(双轨制) ---
  # 趋势压力(胜率)=顺势操作成功率, 偏离极值(赔率)=弹簧压缩程度
  # 全局乘数: yc_mult(收益率差), 利差倒挂→放大风险
  downgraded=False
  if yi and pc>=d20 and r<60:
    downgraded=True
  ts=trend_score; es=extreme_score
  raw=ts+es; eff=min(raw*yc_mult, US_TOTAL_MAX)
  pct=eff/US_TOTAL_MAX*100
  t_pct=ts/US_TREND_MAX*100 if US_TREND_MAX>0 else 0
  e_pct=es/US_EXTREME_MAX*100 if US_EXTREME_MAX>0 else 0
  t_col=R if t_pct>=50 else Y if t_pct>=25 else G
  e_col=R if e_pct>=50 else Y if e_pct>=25 else G
  print("  【趋势压力】{:.0f}/{} {}  【偏离极值】{:.0f}/{} {}  ×{:.1f}".format(
    ts,US_TREND_MAX,t_col,es,US_EXTREME_MAX,e_col,yc_mult))
  print("  触发条件: {}".format(", ".join(risk) if risk else "无"))
  if downgraded:
    print("  "+Y+" 降级条件触发: SPY站上20MA且RSI<60, 风险已缓解")
  if pct>=60:
    lvl="高风险调整窗口"
    print("  "+R+" 判定: 高风险调整窗口(下跌概率78%) 建议轻仓做空/全面对冲")
    print("  "+R+" 操作: 减仓高估值AI股, 增加能源/金融/军工配置")
  elif pct>=30:
    lvl="警戒区"
    print("  "+R+" 判定: 警戒区(下跌概率65%) 建议停止加仓,建立对冲仓位")
    print("  "+R+" 操作: 减持NVDA/TSLA,保留MSFT/AMZN核心仓位,不要盲目做空")
  elif pct>0:
    lvl="注意风险"
    print("  "+Y+" 判定: 注意风险(上涨概率58%) 减仓高估值品种,保留核心仓位")
  else:
    lvl="安全"
    print("  "+G+" 判定: 安全(上涨概率82%) 满仓持有,逢低加仓")

  # --- 信号分析 ---
  print("\n  → 分析:")
  a_ok=[];a_warn=[];top=None
  # ✅ 类真跌: 破20MA+放量+Mag7普跌
  if yi and pc<d20 and v_ratio is not None and v_ratio>1.2 and n_down>=5:
    a_ok.append("SPY破20MA+放量{:.2f}x+Mag7普跌=真跌信号".format(v_ratio))
# ✅ 科技领跌
  if sperf is not None and sperf<-2:
    a_ok.append("SOX跑输QQQ{:.2f}%=半导体领跌".format(sperf))
  # ✅ 资金避险
  if eperf is not None and eperf>2:
    a_ok.append("XLE跑赢QQQ{:.2f}%=资金向能源转移".format(eperf))
  # ⚠️ VIX与大盘背离
  vixy=q.get("gb_vixy")
  if vixy and vixy.get("chg") is not None and yi:
    vix_up=vixy["chg"]>2;spy_up=pchg>0
    if (vix_up and spy_up) or (not vix_up and not spy_up):
      a_warn.append("VIX与SPY同向{:.2f}%/SPY{:.2f}%=关注是否反转".format(vixy["chg"],pchg))
  # ⚠️ Mag7内部分化
  if mag7_std>2:
    a_warn.append("Mag7标准差{:.2f}%=内部分歧加剧".format(mag7_std))
  # ⚠️ 成交量异常
  if v_ratio is not None:
    if v_ratio<0.7:
      a_warn.append("缩量(量比{:.2f}x)=关注方向选择".format(v_ratio))
    elif v_ratio>1.5:
      a_warn.append("放量(量比{:.2f}x)=换手异常".format(v_ratio))
  # ⚠️ 小盘跑输
  if iperf is not None and iperf<-0.5:
    a_warn.append("IWM跑输SPY{:.2f}%=小盘失血".format(iperf))
  for c in a_ok: print("  ✅ "+c)
  for w in a_warn[:3]: print("  ⚠️ "+w)

  # 💡 今日观察
  if a_ok:
    t=a_ok[0].split("=")[0]
    top=t+"，关注下周Fed讲话指引" if "SPY" in a_ok[0] else t+"，关注Mag7能否止跌"
  elif n_down>=5 and pchg is not None and pchg<-1:
    top="Mag7普跌+SPY跌幅>1%，关注VIX是否突破30"
  elif vixy and vixy.get("chg") is not None and vixy["chg"]>5:
    top="VIX急升{:.2f}%，关注恐慌蔓延是否扩散至债市".format(vixy["chg"])
  elif mag7_std>2:
    top="Mag7内部分歧(标准差{:.2f}%)，关注领跌的NVDA/TSLA是否加速".format(mag7_std)
  elif iperf is not None and iperf<-0.5:
    top="小盘持续跑输(IWM跑输{:.2f}%)，关注罗素2000是否进入技术性熊市".format(iperf)
  elif rsi_hist is not None and rsi_hist>85:
    top="SPY的RSI在{:.0f}%历史分位，关注是否触发均值回归".format(rsi_hist)
  else:
    top="整体偏弱但无极端信号，关注明日盘前经济数据"
  print("\n  \U0001f4a1 今日观察：{}".format(top))

  # --- 8. 升级/降级触发条件 ---
  print("\n  -- 升级触发条件(满足>=3项转确认做空) --")
  if yi:
    print("  {} SPY跌破20MA({:.2f}) -> 短期趋势转弱".format("v" if pc<d20 else " " ,d20))
    print("  {} SPY跌破50MA({:.2f}) -> 中长期趋势转弱".format("v" if pc<d50 else " " ,d50))
  print("  {} 成交量放大20%+ -> 真跌确认".format("v" if v_ratio and v_ratio>1.2 else " "))
  print("  {} Mag7跌幅超5家 -> 资金加速出逃".format("v" if n_down>=5 else " "))
  print("  {} VIX升破30 -> 恐慌蔓延".format(" "))
  print("  {} 经验提示: 满足2项时下跌概率约75%, 3项时约85%".format(" "))
  # 降级条件
  print("\n  -- 降级条件(满足任一项风险缓解) --")
  print("  SPY站上20MA + RSI回落至60以下 -> 降为警戒区")
  print("  SPY站上50MA + RSI回落至50以下 -> 降为注意区")
  # --- 存档 ---
  pcv=locals().get("pchg")
  if pcv is not None:
    if pcv>0.2:auto="[涨]"
    elif pcv<-0.2:auto="[跌]"
    else:auto="[平]"
  else:auto=""
  note=auto
  # pct/lvl 已在判定块中算出, 这里复用
  save_daily_review({"mode":"us","score":round(eff,1),"max":US_TOTAL_MAX,"level":lvl,
    "key":{"spy":locals().get("pc"),"ma20":locals().get("d20"),"ma50":locals().get("d50"),
      "rsi":locals().get("r"),"rsi_pct":locals().get("rsi_hist"),
      "vix":vixy.get("p") if vixy else None,
      "yield":yr.get("spread") if yr else None,
      "mag7_down":n_down,"sox_qqq":locals().get("sperf"),
      "xle_qqq":locals().get("eperf"),"iwm_spy":locals().get("iperf"),
      "trend":locals().get("ts"),"extreme":locals().get("es")},
    "analysis":a_ok[:2]+a_warn[:2] if a_ok or a_warn else [],
    "observe":top,"note":note})
  print("\n  "+"\u2550"*50)
  print("  \U0001f9d1 双击 compass.bat 看历史趋势")
  print("  "+"\u2550"*50)
def run_a():
  hdr("Hermes Signal Compass - A-Share Mode - "+now())
  yn=get_yesterday_note("a")
  if yn:print("  \U0001f58b 昨日笔记：{}".format(yn))
  q=sina_q(list(A.values()))
  # 板块ETF
  etf=sina_q(["sh512800","sh512480","sh515000","sh510050","sh512010"])
  sy=yahoo_c("000001.SS","2y"); syk=sina_k("sh000001",250)  # Sina K线(250天,RSI分位用)
  hs=yahoo_c("000300.SS","2y"); cyk=sina_k("sz399006",250)  # 创业板K线(250天,RSI分位用)
  hsi=yahoo_c("^HSI","6mo")
  # 显式初始化所有可能缺数据源的变量
  mp=None;mn=None;nb=None;c10=None;ratio=None;brd={"up":0,"dn":0}
  # 涨跌家数: push2 → 重试 → 缓存回退
  bf=os.path.join(_app_dir(),"brd_cache.json")
  for attempt in range(2):
    try:
      mr=requests.get("https://push2.eastmoney.com/api/qt/ulist.np/get?fields=f62,f66,f69,f72,f75,f78,f84,f184,f104,f105&secids=1.000001,0.399001",headers=H,timeout=8 if attempt==0 else 15)
      if mr.status_code==200:
        data=mr.json().get("data",{}).get("diff")
        if isinstance(data,list) and data:
          entries=data
        elif isinstance(data,dict):
          entries=[v for v in data.values() if isinstance(v,dict)]
        else:
          entries=[]
        if entries:
          mp={"main_net":entries[0].get("f62"),"big_net":entries[0].get("f72")}
          brd["up"]=0; brd["dn"]=0
          for v in entries:
            brd["up"]+=int(v.get("f104",0))
            brd["dn"]+=int(v.get("f105",0))
          with open(bf,"w") as _f:_f.write(json.dumps(brd))
        break  # 成功则退出重试
    except:pass
  # 两轮都失败 → 读缓存
  if not brd["up"] and not brd["dn"]:
    try:
      with open(bf) as _f:brd=json.load(_f)
    except:pass

  print("  === A-Share Signal Map ===")
  risk=[];trend_score=0;extreme_score=0;yc_mult=1.0  # 双轨: 趋势压力/偏离极值

  # --- 1. 核心四指数矩阵 ---
  print("  核心指数矩阵:")
  idx_down=0;cy_data=None
  for k,v in A.items():
    d=q.get(v)
    if d and d["p"]:
      sg=d["chg"]
      mkr="v" if sg<0 else "^"
      print("    {} {:.2f} {:+.2f}% {}".format(k,d["p"],sg,mkr))
      if sg<-0.3:idx_down+=1
      if k=="CY":cy_data=d
    else:
      print("    {} [无数据]".format(k))
  if idx_down>=4:trend_score+=2;risk.append("普跌(4/6)")
  elif idx_down>=3:trend_score+=1.5;risk.append("多数下跌(3/6)")
  elif idx_down>=2:trend_score+=1;risk.append("部分下跌(2/6)")

  # --- 2. 全市场成交额分析 ---
  print("  市场成交额:")
  amt=market_amount()
  vol_ratio=None  # 保留变量名供下游使用
  if amt is not None and amt>0:
    print("    沪深合计: {:.0f}亿{}".format(amt,R if amt<8000 else R if amt>15000 else G))
    # 流动性冰点/过热
    if amt<8000:
      trend_score+=2;risk.append("成交额<8000亿(流动性冰点)")
      vol_ratio=0.6  # 供下游分析判断缩量
    elif amt<10000:
      trend_score+=1;risk.append("成交额不足万亿")
      vol_ratio=0.8
    elif amt>15000:
      trend_score+=1;risk.append("成交额>1.5万亿(换手过激)")
      vol_ratio=1.6
    else:
      vol_ratio=1.0  # 正常
  else:
    print("    [暂无全市场成交额数据]")
    # 回退到上证K线量比
    if syk and syk.get("v") and len(syk["v"])>=20:
      v5=sum(syk["v"][-5:])/5;v20=sum(syk["v"][-20:])/20
      vol_ratio=v5/v20
      print("    (回退上证量比 {:.2f}x)".format(vol_ratio))
      if vol_ratio<0.9:trend_score+=2;risk.append("缩量(上证量比)")
      elif vol_ratio<1.0:trend_score+=1;risk.append("量能偏弱")
      elif vol_ratio>1.3:trend_score+=1;risk.append("放量(上证量比)")

  # --- 3. 涨跌家数 ---
  print("  市场宽度:")
  total=brd["up"]+brd["dn"]
  if total>0:
    if brd["up"]>0 and brd["dn"]/brd["up"]<50:
      ratio=brd["dn"]/brd["up"]
      print("    上涨: {}  下跌: {}  比: 1:{:.1f}".format(brd["up"],brd["dn"],ratio))
      if ratio>=5:trend_score+=2;risk.append("恐慌(1:5+)")
      elif ratio>=3:trend_score+=1.5;risk.append("普跌(1:3+)")
      elif ratio>=2:trend_score+=1;risk.append("偏弱(1:2)")
    else:
      ratio=None
      print("    ⚠️ 涨跌数据异常(↑{} ↓{})，跳过涨跌比判定".format(brd["up"],brd["dn"]))
  else:
    print("    [待接入: 涨跌家数API不稳定]")

  # --- 4. 技术面(上证/沪深300) ---
  if sy:
    d20=dma(sy["c"],20);d50=dma(sy["c"],50);d200=dma(sy["c"],200);sr=rsi(sy["c"])
    spc=sy["c"][-1]
    # 上证RSI分位(用sina_k 250天数据)
    sr_pct=None
    if syk and syk.get("c") and len(syk["c"])>=20:
      _srl=[]
      for i in range(13,len(syk["c"])):
        _rv=rsi(syk["c"][:i+1],14)
        if _rv is not None:_srl.append(_rv)
      sr_pct=sum(1 for r in _srl if r<sr)/len(_srl)*100 if _srl else None
    _sr_str=" ({:.0f}%分位)".format(sr_pct) if sr_pct is not None else ""
    print("  上证技术: 20MA {:.0f}  50MA {:.0f}  200MA {:.0f}  RSI {:.1f}{}".format(d20,d50,d200,sr,_sr_str))
    if sr>70:trend_score+=1;risk.append("上证超买")
    if sr<30:trend_score+=1;risk.append("上证超卖")
  if hs:
    hr=rsi(hs["c"]);hpc=hs["c"][-1];hd20=dma(hs["c"],20)
    print("  沪深300: RSI {:.1f}  20MA {:.0f}".format(hr,hd20))
  # 创业板技术 (Sina K线真实数据)
  if cyk and cyk.get("c") and len(cyk["c"])>=20:
    cy20=dma(cyk["c"],20);cy_r=rsi(cyk["c"],14);cy_last=cyk["c"][-1]
    cy_below="低于" if cy_last<cy20 else "高于"
    # 注: Sina日K收盘后更新约~30分钟, cy_last可能略低于实时收盘, 不影响MA方向
    # RSI历史分位(近30日)
    rp_l=[]
    for i in range(13,len(cyk["c"])):
      rv=rsi(cyk["c"][:i+1],14)
      if rv is not None:rp_l.append(rv)
    rp_pct=sum(1 for r in rp_l if r<cy_r)/len(rp_l)*100 if rp_l else None
    rp_str=" ({:.0f}%分位)".format(rp_pct) if rp_pct is not None else ""
    # 标注: K线收盘与实时价是否不同(盘中cy_last是昨收)
    _cy_note=""
    if cy_data and cy_data.get("p") is not None:
      if abs(cy_last-cy_data["p"])/cy_data["p"]>0.003:
        _cy_note=" (K线昨收)"
    print("  创业板: 20MA {:.0f}  RSI {:.1f}{}  当前{}20MA{}".format(cy20,cy_r,rp_str,cy_below,_cy_note))
    if cy_r>70:extreme_score+=2;risk.append("创业板超买")
    elif cy_r<40:extreme_score+=2;risk.append("创业板超卖")
    # 创业板20MA破位→偏离极值
    if cy_last<cy20:
      extreme_score+=2;risk.append("创业板破20MA")
    # 实时跌幅
    if cy_data and cy_data.get("chg") is not None:
      cy_chg=cy_data["chg"]
      if cy_chg<-1.5:
        if "创业板破20MA" not in risk:risk.append("创业板大跌{:.1f}%".format(cy_chg))
  else:
    print("  创业板: [无K线数据]")

  # --- 5. 板块轮动 (银行ETF vs 科技ETF) ---
  print("  板块轮动:")
  bank=etf.get("sh512800");semi=etf.get("sh512480");tech=etf.get("sh515000")
  sh50=etf.get("sh510050");med=etf.get("sh512010")
  if bank and tech and bank.get("chg") is not None and tech.get("chg") is not None:
    b_tech=bank["chg"]-tech["chg"]
    print("    银行-科技涨跌幅差: {:+.2f}% (正=防御跑赢成长)".format(b_tech))
    if b_tech>2:trend_score+=1.5;risk.append("银行>科技(避险)")
    elif b_tech>1:trend_score+=1;risk.append("银行偏强")
  if semi and tech and semi.get("chg") is not None and tech.get("chg") is not None:
    s_t=semi["chg"]-tech["chg"]
    print("    半导体-科技涨跌幅差: {:+.2f}% (正=芯片抗跌)".format(s_t))
    if s_t<-1.5:trend_score+=1;risk.append("半导体领跌")
  if sh50 and tech and sh50.get("chg") is not None and tech.get("chg") is not None:
    l_v=sh50["chg"]-tech["chg"]
    print("    上证50-科技涨跌幅差: {:+.2f}% (正=权重护盘)".format(l_v))
    if l_v>0.5:trend_score+=1;risk.append("权重护盘/小票承压")
  if med and tech and med.get("chg") is not None and tech.get("chg") is not None:
    m_t=med["chg"]-tech["chg"]
    print("    医药-科技涨跌幅差: {:+.2f}% (正=消费防御)".format(m_t))

  # --- 5.5 风格成交量（科创50 vs 沪深300 成交额比率）---
  style_pct=None
  try:
    sr=get_style_ratio()
    if sr:
      star_amt,hs300_amt,sp=sr;style_pct=sp
      tag=""
      if style_pct>=90:tag="🔴风格极端"
      elif style_pct>=75:tag="🟡风格偏移"
      elif style_pct>=60:tag="小盘活跃"
      if tag:print("  风格成交量: 科创{}亿 沪深300{}亿 比率{}% {}".format(int(star_amt),int(hs300_amt),style_pct,tag))
      else:print("  风格成交量: 科创{}亿 沪深300{}亿 比率{}%".format(int(star_amt),int(hs300_amt),style_pct))
      if style_pct>=75:trend_score+=1;risk.append("科创比率"+str(style_pct)+"%")
      save_style_cache(star_amt,hs300_amt,style_pct)
    else:
      print("  风格成交量: [暂无数据]")
  except:pass

  # --- 6. 资金流向 + 恒指 ---
  if mp is not None and mp["main_net"] is not None:
    mn=mp["main_net"]/1e8
    print("  主力资金净流: {:+.0f}亿".format(mn))
    if mn<-150:trend_score+=2;risk.append("主力出逃>150亿")
    elif mn<-100:trend_score+=1;risk.append("主力出逃>100亿")
  # 北向资金（今日API → 盘中回退昨日缓存）
  nb=north_b()
  nb_today=False;nb_date=None;nb_time=None
  if nb is not None and abs(nb)>0.1:
    nb_today=True
  else:
    # 盘中API返0.0, 查今日缓存或昨日实盘
    today=datetime.date.today().strftime("%Y-%m-%d")
    try:
      with open(CACHE_FILE,"r") as f:c=json.load(f)
      if today in c and abs(c[today])>0.1:
        nb=c[today];nb_today=True
    except:pass
    if not nb_today:
      yd=nb_yesterday()
      if yd:nb,nb_date,nb_time=yd[1],yd[0],yd[2]
      else:nb=None
  if nb is not None and abs(nb)>0.1:
    tag="  (今日累计)" if nb_today else "  (取自{} {})".format(nb_date,nb_time if nb_time else "")
    print("  北向资金净流: {:+.1f}亿{}".format(nb,tag))
    if nb<-100:extreme_score+=1.5;risk.append("北向出逃>100亿")
    elif nb<-50:extreme_score+=1;risk.append("北向出逃>50亿")
    elif nb>100:extreme_score-=1.5  # 降级
  else:
    print("  北向资金净流: [2024年8月起官方每日披露已停, 暂无可靠实时数据]")
  # 3日累计北向
  nb3=get_nb_3d()
  if nb3 is not None:
    s3,d3=nb3
    print("  北向近三日累计: {:+.1f}亿  ({}起)".format(s3,d3))
    if s3<-150:extreme_score+=2;risk.append("北向3日累计净流出>150亿")
    elif s3<-100:extreme_score+=1.5;risk.append("北向3日累计净流出>100亿")
  # 南向资金（港股通, 盘中实时）
  sb=south_b()
  if sb:
    print("  南向资金净买: {:+.1f}亿  (实时{})  沪{}深{}".format(
      sb["total"],sb["time"],sb["sh"],sb["sz"]))
    # 南向大额→资本外流信号, 加入趋势压力
    if sb["total"]>120:trend_score+=2;risk.append("南向>120亿(资金外流)")
    elif sb["total"]>80:trend_score+=1.5;risk.append("南向>80亿(资金外流)")
    elif sb["total"]>50:trend_score+=0.5;risk.append("南向>50亿")
  # 中国10Y国债收益率
  c10=china_10y()
  if c10 is not None:
    print("  中国10Y国债: {:.2f}%".format(c10))
    if c10>2.0:yc_mult=1.2;risk.append("国债>2%→全局×1.2")
    elif c10<1.5:yc_mult=0.9;risk.append("国债<1.5%→全局×0.9")
  if hsi:
    hp=hsi["c"][-1];hp0=hsi["c"][-2];hpchg=(hp-hp0)/hp0*100
    print("  恒指: {:.2f} ({:+.2f}%)".format(hp,hpchg))
    if hpchg<-1.5:trend_score+=1;risk.append("恒指大跌")

  # --- 涨停板分布 ---
  zt=get_zt_data(datetime.datetime.now().strftime("%Y%m%d"))
  if zt:
    print("  涨停分布: 共{}只 | 首板{} | 一进二{} | 最高{}板".format(zt["total"],zt["first"],zt["second"],zt["max"]))
    print("  热点板块: {}".format(" | ".join(zt["sectors"])))
    if zt["total"]<20:trend_score+=1;risk.append("涨停<20只(情绪冰点)")
    if zt["max"]<2:trend_score+=1;risk.append("最高连板<2(无赚钱效应)")
  else:
    print("  涨停分布: [暂无数据]")

  # --- 今日摘要快览 ---
  abr=[]
  if idx_down>=4:abr.append("普跌(4/6+)")
  elif idx_down>=3:abr.append("多数下跌(3/6)")
  elif idx_down<=1:abr.append("普涨(5/6+)")
  if ratio is not None:
    if ratio>=5:abr.append("恐慌")
    elif ratio>=3:abr.append("普跌")
    elif ratio>=2:abr.append("偏弱")
  if mn is not None and mn<-100:abr.append("主力出逃")
  if b_tech is not None and b_tech>2:abr.append("防御")
  if abr:print("\n  >> "+" | ".join(abr))
  # --- 7. 判定(双轨制) ---
  ts=trend_score; es=extreme_score
  raw=ts+es; eff=min(raw*yc_mult, A_TOTAL_MAX)
  pct=eff/A_TOTAL_MAX*100
  t_pct=ts/A_TREND_MAX*100 if A_TREND_MAX>0 else 0
  e_pct=es/A_EXTREME_MAX*100 if A_EXTREME_MAX>0 else 0
  t_col=R if t_pct>=50 else Y if t_pct>=25 else G
  e_col=R if e_pct>=50 else Y if e_pct>=25 else G
  print("  【趋势压力】{:.0f}/{} {}  【偏离极值】{:.0f}/{} {}  ×{:.1f}".format(
    ts,A_TREND_MAX,t_col,es,A_EXTREME_MAX,e_col,yc_mult))
  print("  触发条件: {}".format(", ".join(risk) if risk else "无"))
  if pct>=60:
    lvl="高风险调整窗口"
    print("  "+R+" 判定: 高风险调整窗口 建议清仓高估值,持仓控制在30%以下,保留现金")
  elif pct>=35:
    lvl="警戒区"
    print("  "+R+" 判定: 警戒区 停止加仓,控制仓位在50%以下,减仓成长股")
  elif pct>=20:
    lvl="注意风险"
    print("  "+Y+" 判定: 注意风险 减仓高估值成长股,增加防御配置")
  elif pct>0:
    lvl="中性"
    print("  "+G+" 判定: 中性 局部机会,控制仓位")
  else:
    lvl="安全"
    print("  "+G+" 判定: 安全 市场健康,逢低加仓")

  # --- 信号分析 ---
  print("\n  → 分析:")
  a_ok=[];a_warn=[];top=None
  # ✅ 真跌: 全指数普跌+涨跌比>1:3
  if idx_down>=4 and total>0 and brd["dn"]>=brd["up"]*3:
    a_ok.append("全指数普跌+涨跌1:{:.1f}=真跌非失真".format(ratio))
  # ✅ 假护盘: 银行偏强+主力出逃
  b_t=locals().get("b_tech")
  if b_t is not None and b_t>1.5 and mp is not None and mp["main_net"]/1e8<-100:
    a_ok.append("银行偏强+主力出逃{:.0f}亿=典型假护盘".format(mp["main_net"]/1e8))
  # ⚠️ 趋势缓冲项
  if cyk and cy_data and cy_last>=cy20:
    a_warn.append("创业板未破20MA=趋势尚未破位")
  # ⚠️ 内外资分歧
  if mn is not None and nb is not None and abs(nb)>0.1:
    if mn<-100 and nb>0:
      a_warn.append("主力出逃{:.0f}亿vs北向流入{:.1f}亿=内外资分歧".format(mn,nb))
  # ⚠️ 量能异常
  if amt is not None and amt>0:
    if amt<8000:
      a_warn.append("成交额{:.0f}亿<8000亿=流动性冰点".format(amt))
    elif amt>15000:
      a_warn.append("成交额{:.0f}亿>1.5万亿=换手过激".format(amt))
  elif vol_ratio is not None and vol_ratio<0.7:
    a_warn.append("缩量(上证量比{:.2f}x)=流动性不足".format(vol_ratio))
  elif vol_ratio is not None and vol_ratio>1.5:
    a_warn.append("放量(量比{:.2f}x)=换手加剧".format(vol_ratio))
  elif amt is not None and amt>15000:
    a_warn.append("全市场成交额{:.0f}亿=高换手".format(amt))
  # 打印确认项+观察项
  for c in a_ok: print("  ✅ "+c)
  for w in a_warn[:3]: print("  ⚠️ "+w)

  # 提前加载昨日观察(用于今日观察去重)
  yesterday_observe=None
  try:
    _yd=(datetime.datetime.now()-datetime.timedelta(days=1)).strftime("%Y%m%d")
    _ym=(datetime.datetime.now()-datetime.timedelta(days=1)).strftime("%Y%m")
    _yfp=os.path.join(REVIEW_DIR,_ym+".json")
    if os.path.exists(_yfp):
      with open(_yfp,"r",encoding="utf-8") as f:_ydata=json.load(f)
      if _yd in _ydata:yesterday_observe=_ydata[_yd].get("observe")
  except:pass

  # 💡 今日观察(动态选最值得盯的异常)
  s_t=locals().get("s_t");l_v=locals().get("l_v")
  if b_t is not None and s_t is not None and l_v is not None and b_t>0 and s_t>0 and l_v>0 and idx_down>=3:
    top="银行/半导体/上证50全跑赢科技，明日重点看北向有无逆势流入"
  elif cy_r is not None and rp_pct is not None and rp_pct<15 and cy_last>=cy20:
    top="创业板RSI仅{:.0f}%分位但未破20MA，关注明日是否补跌或反弹".format(rp_pct)
  elif amt is not None and (amt<8000 or amt>15000):
    top='全市场成交额{:.0f}亿异常，观察是否确认方向'.format(amt)
  elif vol_ratio is not None and (vol_ratio<0.7 or vol_ratio>1.5):
    top="今日成交量异常(量比{:.2f}x)，观察明日能否放量确认方向".format(vol_ratio)
  elif total>0 and ratio>=5:
    top="涨跌1:{:.1f}但指数仅微跌，关注权重与小票分化是否加剧".format(ratio)
  elif sb and sb["total"]>80:
    top="南向资金逆势大买{:.0f}亿南下港股，关注跨市场配资是否引发A股抽血".format(sb["total"])
  else:
    top="关注北向资金开盘方向，判断外资对当前点位态度"
  # 去重: 如与昨天相同则用默认观察
  if yesterday_observe and top==yesterday_observe:
    top="关注北向资金及明日开盘方向，判断市场短期情绪"
  print("\n  \U0001f4a1 今日观察：{}".format(top))

  # --- 8. 升级/降级触发条件(动态检测) ---
  print("\n  -- 升级条件(当前检测) --")
  up_trig=0;up_total=0
  def YN(v): return "✅" if v else "❌"
  # 创业板跌破20MA
  if cyk and cy_last is not None and cy20 is not None:
    up_total+=1
    c1=cy_last<cy20
    if c1:up_trig+=1
    print("  {} 创业板破20MA? 现{:.0f} 20MA{:.0f} = {}".format(YN(c1),cy_last,cy20,"破位" if c1 else "未破"))
  else:print("  ⬜ 创业板破20MA? 暂无数据")
  # 涨跌家数比>5:1
  if total is not None and total>0 and brd["up"]>0:
    up_total+=1
    c2=brd["dn"]>=brd["up"]*5
    if c2:up_trig+=1
    print("  {} 涨跌比>5:1? 1:{:.1f}= {}".format(YN(c2),ratio if ratio else brd["dn"]/max(brd["up"],1),"恐慌" if c2 else "正常"))
  else:print("  ⬜ 涨跌比>5:1? 暂无数据")
  # 成交量萎缩<0.8*20日均
  if vol_ratio is not None:
    up_total+=1
    c3=vol_ratio<0.8
    if c3:up_trig+=1
    print("  {} 成交量<0.8x? 量比{:.2f}x= {}".format(YN(c3),vol_ratio,"缩量" if c3 else "正常"))
  else:print("  ⬜ 成交量<0.8x? 暂无数据")
  # 北向3日净流出>150亿
  nb3s=None
  if nb3 is not None:
    nb3s,_=nb3
    up_total+=1
    c4=nb3s is not None and nb3s<-150
    if c4:up_trig+=1
    print("  {} 北向3日>150亿? {:.0f}亿= {}".format(YN(c4),nb3s if nb3s else 0,"出逃" if c4 else "未达"))
  else:print("  ⬜ 北向3日>150亿? 暂无缓存")
  # 主力出逃>150亿
  if mn is not None:
    up_total+=1
    c5=mn<-150
    if c5:up_trig+=1
    print("  {} 主力出逃>150亿? {:.0f}亿= {}".format(YN(c5),mn,"出逃" if c5 else "未达"))
  else:print("  ⬜ 主力出逃>150亿? 暂无数据")
  # 中国10Y>2.0%
  if c10 is not None:
    up_total+=1
    c6=c10>2.0
    if c6:up_trig+=1
    print("  {} 10Y国债>2.0%? {:.2f}%= {}".format(YN(c6),c10,"收紧" if c6 else "正常"))
  else:print("  ⬜ 10Y国债>2.0%? 暂无数据")
  print("  升级: {}/{} 满足  (>=3→高风险)".format(up_trig,up_total))
  # 降级条件
  print("\n  -- 降级条件(当前检测) --")
  dn_trig=0;dn_total=0
  if cyk and cy_last is not None and cy20 is not None and total and total>0 and brd["up"]>0:
    dn_total+=1
    d1=cy_last>=cy20 and brd["dn"]<brd["up"]*2
    if d1:dn_trig+=1
    print("  {} 创业板站回20MA+涨跌<2:1? 现{} MA{} 涨跌1:{:.1f}= {}".format(
      YN(d1),cy_last,cy20,ratio,"缓解" if d1 else "未满足"))
  else:print("  ⬜ 创业板+涨跌<2:1? 暂无数据")
  if nb is not None and abs(nb)>0.1:
    dn_total+=1
    d2=nb>100
    if d2:dn_trig+=1
    print("  {} 北向流入>100亿? {:+.1f}亿= {}".format(YN(d2),nb,"降级" if d2 else "未达"))
  else:print("  ⬜ 北向流入>100亿? 暂无数据")
  if c10 is not None:
    dn_total+=1
    d3=c10<1.5
    if d3:dn_trig+=1
    print("  {} 10Y国债<1.5%? {:.2f}%= {}".format(YN(d3),c10,"宽松" if d3 else "未达"))
  else:print("  ⬜ 10Y国债<1.5%? 暂无数据")
  print("  降级: {}/{} 满足".format(dn_trig,dn_total))
  # --- 存档 ---
  cv=(q.get(A["CY"]) or {}).get("chg")
  if cv is not None:
    if cv>0.2:auto="[涨]"
    elif cv<-0.2:auto="[跌]"
    else:auto="[平]"
  else:auto=""
  # 已有笔记 → 直接复用
  today_note=get_today_note()
  if today_note:
    note=today_note
    if not is_trading():
      print("  📝 今日已存笔记: {}".format(today_note[:60]))
  else:
    # 无笔记且休市 → 弹提示
    if not is_trading():
      try:
        n_in=input("  💡 我的笔记 {}: ".format(auto))
        note=(auto+" "+n_in.strip()).strip() if n_in.strip() else auto
      except:note=auto
    else:note=auto
  # pct/lvl 已在判定块中算出
  # --- 复盘存档扩展字段 ---
  # 收集升级条件
  up_conds=[]
  for cond_name,cond_var,val_expr in [
    ("创业板破20MA","c1","\"{:.0f} vs {:.0f}\".format(cy_last,cy20) if cy_last is not None and cy20 is not None else None"),
    ("涨跌比>5:1","c2","\"1:{:.1f}\".format(ratio) if ratio else None"),
    ("成交量<0.8x","c3","\"量比{:.2f}x\".format(vol_ratio) if vol_ratio else None"),
    ("北向3日>150亿","c4","\"{:.0f}亿\".format(nb3s) if 'nb3s' in dir() and nb3s else None"),
    ("主力出逃>150亿","c5","\"{:.0f}亿\".format(mn) if mn is not None else None"),
    ("10Y国债>2.0%","c6","\"{:.2f}%\".format(c10) if c10 is not None else None"),
  ]:
    v=locals().get(cond_var)
    ev=eval(val_expr) if v is not None else None
    up_conds.append({"name":cond_name,"triggered":bool(v) if v is not None else None,"val":ev})
  dn_conds=[]
  if locals().get("d1") is not None:
    dn_conds.append({"name":"创业板站回20MA+涨跌<2:1","triggered":d1,
      "val":"现{:.0f} MA{:.0f} 1:{:.1f}".format(cy_last,cy20,ratio) if cy_last and cy20 and ratio else None})
  # 板块轮动
  sectors={}
  for k in ["b_tech","s_t","l_v","m_t"]:
    if k in locals() and locals()[k] is not None:
      sectors[k]=round(locals()[k],2)
  # SS交叉校验(sina实时 vs K线收盘, 防5/21式数据错误)
  _ss_sina=(q.get(A["SS"]) or {}).get("p")
  if _ss_sina is not None and syk and syk.get("c"):
    _ss_k=syk["c"][-1]
    if abs(_ss_sina-_ss_k)/_ss_k>0.01:
      if not is_trading():
        print("  ⚠️ SS数据源偏差: sina实时{:.2f} vs K线收盘{:.2f}, 存档用K线值".format(_ss_sina,_ss_k))
        _ss_sina=_ss_k
  save_daily_review({"mode":"a","score":round(eff,1),"max":A_TOTAL_MAX,"level":lvl,
    "key":{"ss":_ss_sina,"cy":locals().get("cy_last"),
      "cy20":locals().get("cy20"),"cy_rsi":locals().get("cy_r"),
      "rsi_pct":locals().get("rp_pct"),"v_ratio":vol_ratio,
      "ud_ratio":ratio,"main_flow":mn,
      "nb_flow":nb,"c10y":c10,"trend":ts,"extreme":es,"star_pct":style_pct},
    "analysis":a_ok[:2]+a_warn[:2] if a_ok or a_warn else [],
    "observe":top,"note":note,
    "up_conds":up_conds,"dn_conds":dn_conds,
    "triggers":risk[:10] if risk else [],
    "sectors":sectors,"yesterday_observe":yesterday_observe})
  print("\n  "+"\u2550"*50)
  print("  \U0001f9d1 双击 compass.bat 看历史趋势")
  print("  "+"\u2550"*50)

# --- 复盘模式 ---
def draw_trend(vals,h=5,fm=None):
  if not vals:return ""
  lo=min(vals);hi=fm if fm else max(vals)
  if hi==lo:hi=lo+1
  lines=[]
  for y in range(h,-1,-1):
    lb=int(lo+y*(hi-lo)/h)
    sg="".join("●" if int((v-lo)/(hi-lo)*h)==y else " " for v in vals)
    lines.append("{:3d}|{}".format(lb,sg))
  lines.append("   +"+"-"*len(vals))
  return "\n".join(lines)

def detect_windows(sc,th=3):
  ws=[];cur=None
  for i in range(1,len(sc)):
    d=sc[i]-sc[i-1]
    if d>=1:
      if cur and cur["t"]=="up":cur["e"]=i;cur["d"]+=1
      else:
        if cur:ws.append(cur)
        cur={"t":"up","s":i-1,"e":i,"d":2}
    elif d<=-1:
      if cur and cur["t"]=="down":cur["e"]=i;cur["d"]+=1
      else:
        if cur:ws.append(cur)
        cur={"t":"down","s":i-1,"e":i,"d":2}
    else:
      if cur:ws.append(cur);cur=None
  if cur:ws.append(cur)
  return [w for w in ws if w["d"]>=th]

def calc_accuracy(rev, dates, forward_days=1):
  """T日信号 → T+1日结果验证（四象限 + 分等级）
     forward_days: T→T+1 (默认) / T→T+N"""
  danger=["高风险调整窗口","警戒区"]
  safe=["安全区","安全","中性"]
  observe=["注意风险"]
  h_safe=m_alarm=m_omit=h_danger=o_safe=o_danger=neutral=total=0
  by_level={}  # 按信号等级分桶: {level: {"up":N, "dn":N}}
  for i in range(len(dates)-forward_days):
    today=dates[i]
    try:
      tomorrow=dates[i+forward_days]
    except IndexError: break
    lv=rev[today].get("level","")
    nn=rev[tomorrow].get("note","")
    if "[涨]" not in nn and "[跌]" not in nn:
      if "[平]" in nn: neutral+=1
      continue
    total+=1
    is_danger=lv in danger; is_safe=lv in safe; is_observe=lv in observe
    is_up="[涨]" in nn; is_down="[跌]" in nn
    # 四象限 + 观察档
    if is_safe and is_up:     h_safe+=1
    elif is_safe and is_down: m_omit+=1
    elif is_danger and is_down: h_danger+=1
    elif is_danger and is_up: m_alarm+=1
    elif is_observe and is_up: o_safe+=1
    elif is_observe and is_down: o_danger+=1
    # 按等级分桶
    by_level.setdefault(lv,{"up":0,"dn":0})
    if is_up: by_level[lv]["up"]+=1
    else: by_level[lv]["dn"]+=1
  return {
    "h_safe":h_safe,"m_alarm":m_alarm,"m_omit":m_omit,"h_danger":h_danger,
    "o_safe":o_safe,"o_danger":o_danger,
    "neutral":neutral,"total":total,
    "false_alarm_rate":round(m_alarm/(h_danger+m_alarm)*100,1) if (h_danger+m_alarm)>0 else None,
    "miss_rate":round(m_omit/(h_safe+m_omit)*100,1) if (h_safe+m_omit)>0 else None,
    "by_level":by_level,
    "paired":len(dates)-forward_days  # 有效配对天数
  }

def run_review():
  import datetime as dt,json,os
  hdr("Hermes Signal Compass - Review Mode - "+now())
  rev={}
  for i in range(30):
    d=(dt.datetime.now()-dt.timedelta(days=i)).strftime("%Y%m%d")
    mk=(dt.datetime.now()-dt.timedelta(days=i)).strftime("%Y%m")
    fp=os.path.join(REVIEW_DIR,mk+".json")
    if os.path.exists(fp):
      try:
        with open(fp,"r",encoding="utf-8") as f:r=json.load(f)
        if d in r:rev[d]=r[d]
      except:pass
  if not rev:
    print("  还没有复盘数据，先跑一次 compass.py 或 python compass.py a")
    return
  dates=sorted(rev.keys());mx=rev[dates[-1]].get("max",15)
  sc=[rev[d]["score"] for d in dates]
  print("  【得分趋势】(近{}天, 满分{})".format(len(sc),mx))
  print(draw_trend(sc,h=5,fm=mx))
  ws=detect_windows(sc,th=3)
  if ws:
    print("\n  【异常窗口】")
    for w in ws:
      d1=dates[w["s"]];d2=dates[w["e"]]
      lb="连续升级" if w["t"]=="up" else "连续降级"
      print("    {} [{} -> {}] {}天".format(lb,d1,d2,w["d"]))
  notes=[(d,rev[d].get("note","")) for d in dates if rev[d].get("note")]
  if notes:
    print("\n  【笔记回顾】")
    for d,n in notes:print("    {}: {}".format(d,n))
  # F7: 风格成交量趋势
  style_trend=[]
  try:
    style_cache_data=load_style_cache(10)
    for d,v in style_cache_data:
      sd=d[-5:] if len(d)==10 else d  # YYYY-MM-DD → MM-DD
      style_trend.append((sd,v["pct"]))
  except:pass
  if not style_trend and rev:
    # fallback: 从复盘数据读 star_pct
    try:
      for d in sorted(rev.keys()):
        sp=rev[d].get("key",{}).get("star_pct")
        if sp is not None:
          sd=d[4:] if len(d)==8 else d
          style_trend.append((sd,sp))
    except:pass
  if len(style_trend)>=2:
    dirs=[]
    for i in range(1,len(style_trend)):
      diff=style_trend[i][1]-style_trend[i-1][1]
      if diff>1:dirs.append("↑")
      elif diff<-1:dirs.append("↓")
      else:dirs.append("→")
    line="  【风格成交量趋势】\n   "
    for i,(sd,pct) in enumerate(style_trend):
      line+="{} {}%".format(sd,int(round(pct,0)))
      if i<len(dirs):line+="{} ".format(dirs[i])
    print(line)
  # --- 条件追踪（近3天的升级条件状态） ---
  ndays=min(5,len(dates))
  recent=dates[-ndays:]
  # 对比每个条件的触发状态
  cond_names=["创业板破20MA","涨跌比>5:1","成交量<0.8x","北向3日>150亿","主力出逃>150亿","10Y国债>2.0%"]
  # CJK感知对齐
  try:
    from wcwidth import wcswidth
  except ImportError:
    wcswidth=lambda s:len(s)
  def pad_cn(s,w):return s+' '*(w-wcswidth(s))
  cw=max(wcswidth(n) for n in cond_names)+2
  for cname in cond_names:
    row=pad_cn(cname,cw);found=False
    for d in recent:
      cu=rev[d].get("up_conds",[])
      match=[x for x in cu if x.get("name")==cname]
      if match:
        found=True
        m=match[0]
        if m["triggered"] is True:row+="  ✅触发"
        elif m["triggered"] is False:row+="  ❌正常"
        else:row+="  ⬜暂无"
      else:
        row+="  ···"
    if found:print(row)
  # --- 昨日预判回溯 ---
  obs_pairs=[]
  for i,d in enumerate(dates):
    yo=rev[d].get("yesterday_observe")
    tod=rev[d].get("observe","")
    if i>0 and yo:
      obs_pairs.append((dates[i-1],yo,dates[i],tod))
    elif i>0:
      obs_pairs.append((dates[i-1],rev[dates[i-1]].get("observe",""),dates[i],tod))
  if obs_pairs:
    print("\n  【预判回看】")
    for yd,yo,td,to in obs_pairs[-3:]:
      if yo:
        print("    {} 预判: {}".format(yd[-5:],yo[:45]))
        # 对比今日 observe 判断方向变化
        print("    {} 新判: {}".format(td[-5:],to[:45]))
        print()
  # --- 信号准确率（T日信号→T+1日验证）---
  ac=calc_accuracy(rev,dates)
  if ac and ac["total"]>0:
    print("  【信号准确率】(T日信号→T+1日结果, {}配对/{}天)".format(ac["total"],ac["paired"]))
    print("               实际涨    实际跌")
    print("  信号安全    {:<6d}  {:<6d}      漏报率: {}".format(
      ac["h_safe"],ac["m_omit"],
      str(ac["miss_rate"])+"%" if ac["miss_rate"] is not None else "--%"))
    if ac["o_safe"]+ac["o_danger"]>0:
      print("  信号观察    {:<6d}  {:<6d}      (注意风险)".format(ac["o_safe"],ac["o_danger"]))
    print("  信号危险    {:<6d}  {:<6d}      假警率: {}".format(
      ac["m_alarm"],ac["h_danger"],
      str(ac["false_alarm_rate"])+"%" if ac["false_alarm_rate"] is not None else "--%"))
    print("  [平] {}/{}  总样本: {}".format(ac["neutral"],ac["total"],ac["total"]))
    # 分等级明细
    if ac.get("by_level"):
      bl=ac["by_level"]
      print("  分等级明细:")
      for lv in ["安全","中性","注意风险","警戒区","高风险调整窗口"]:
        if lv in bl:
          print("    {}: {}涨 {}跌".format(lv,bl[lv]["up"],bl[lv]["dn"]))
  else:
    print("\n  信号准确率: 无有效样本(T日→T+1日配对需要至少2天数据)")
  print("\n  "+"\u2550"*50)
  print("  标记方式: 在笔记中写 [涨]/[跌]/[平]")
  print("  "+"\u2550"*50)
# --- 三指标组合信号（分层过滤版） ---
def get_signal(kd):
  """分层过滤：MA定趋势→BIAS控风险→MACD/KDJ/量能精调
     返回 (emoji, 短评, 得分)  分层决定，非平铺加减"""
  import statistics
  c=kd.get("c",[]);h=kd.get("h",[]);l=kd.get("l",[]);v=kd.get("v",[])
  if not c or len(c)<26:return W,"数据不足",0
  p=c[-1]
  # --- 均线 ---
  def ma(n):return sum(c[-n:])/n if len(c)>=n else None
  ma5=ma(5);ma10=ma(10);ma20=ma(20);ma60=ma(60)
  # --- KDJ双参数 ---
  def kdj_n(n):
    if len(c)<n+2:return 50,50,50
    k=d=50
    for i in range(-n,0):
      hi=max(h[:i]) if i<0 else max(h[-n:]);lo=min(l[:i]) if i<0 else min(l[-n:])
      if hi==lo:r=50
      else:r=100*(c[i]-lo)/(hi-lo)
      k=2/3*k+1/3*r;d=2/3*d+1/3*k
    return k,d,3*k-2*d
  k9,d9,j9=kdj_n(9);k13,d13,j13=kdj_n(13)
  # --- MACD ---
  def ema(pv,n):
    if len(pv)<n:return None
    k=2/(n+1);v=pv[-n]
    for i in range(-n+1,0):v=pv[i]*k+v*(1-k)
    return v
  e12=ema(c,12);e26=ema(c,26)
  if e12 is None or e26 is None:return W,"数据不足",0
  dif=e12-e26;dea=0
  difs=[]
  for end in range(26,len(c)+1):
    e12i=ema(c[:end],12);e26i=ema(c[:end],26)
    if e12i is not None and e26i is not None:difs.append(e12i-e26i)
  if difs:dea=difs[-1] if len(difs)==1 else (ema(difs,9) if len(difs)>=9 else difs[-1])
  # --- 成交量+x市值分仓 ---
  avg5v=sum(v[-5:])/5 if len(v)>=5 else 1
  vr=v[-1]/avg5v if avg5v>0 else 1
  avg_p=sum(c[-20:])/20;avg_v=sum(v[-20:])/20 if len(v)>=20 else avg5v
  est_turnover=avg_p*avg_v  # 日均成交额（亿元近似）
  cap="大" if est_turnover>5e9 else ("小" if est_turnover<1e9 else "中")
  # --- BIAS(6) ---
  ma6=ma(6);bias6=(p-ma6)/ma6*100 if ma6 and ma6>0 else 99
  # --- 严重异动（两级检测） ---
  # 检测1: 交易所标准——连续3日收盘价涨幅偏离值累计>=20%（提示级）
  anomaly_3d=False
  if len(c)>=6:
    d1=(c[-3]-c[-4])/c[-4]*100 if c[-4]!=0 else 0
    d2=(c[-2]-c[-3])/c[-3]*100 if c[-3]!=0 else 0
    d3=(c[-1]-c[-2])/c[-2]*100 if c[-2]!=0 else 0
    anomaly_3d=(d1+d2+d3)>=20
  # 检测2: 极端涨幅——10日>=100%或30日>=200%（警报级，可触发停牌）
  high10=max(c[-10:]) if len(c)>=10 else p
  rise10=(high10-c[-10])/c[-10]*100 if len(c)>=10 and c[-10]>0 else 0
  high30=max(c[-30:]) if len(c)>=30 else p
  rise30=(high30-c[-30])/c[-30]*100 if len(c)>=30 and c[-30]>0 else 0
  extreme=rise10>=100 or rise30>=200
  
  # === Layer 1: MA趋势 ===
  if all(x is not None for x in [ma5,ma10,ma20,ma60]):
    if ma5>ma10>ma20>ma60:trend="强多头";b=3
    elif ma5<ma10<ma20<ma60:trend="强空头";b=-3
    elif ma5>ma20 and ma10>ma20:trend="偏多";b=2
    elif ma5<ma20 and ma10<ma20:trend="偏空";b=-2
    else:trend="震荡";b=0
  else:trend="震荡";b=0

  # === 按趋势分支决策（层2+3合一）===
  # 强多头
  if trend=="强多头":
    if extreme:return R,"异动预警",-2
    if anomaly_3d:return Y,"涨幅偏离",-1
    if bias6>15:return Y,"多头过热",1  # 不做空，但等回调
    if bias6>10:return Y,"多头超买",2
    if bias6<-8:return Y,"急跌回调",0   # 强多头中突跌>3%, 等稳再判断
    # 合理区间或微超买
    if dif>dea and vr>1.3 and j9<90:return G,"放量上攻",3
    if dif>dea:return Y,"多头",2
    if dif<dea:return Y,"多头微调",1
    return Y,"多头",2
  # 偏多
  elif trend=="偏多":
    if extreme:return R,"异动预警",-2
    if anomaly_3d:return Y,"涨幅偏离",-1
    if bias6>15:return Y,"超买过热",1
    if dif>dea and vr>1.3:return G,"放量突破",3
    if dif>dea:return Y,"偏多",2
    return Y,"偏多偏弱",1
  # 强空头
  elif trend=="强空头":
    if bias6<-15 and dif>dea:return Y,"超跌反弹",1
    return R,"空头回避",-3
  # 偏空
  elif trend=="偏空":
    if bias6<-15:return Y,"超跌观察",0
    return R,"偏空",-2
  # 震荡
  else:
    if extreme:return R,"严重异动",-2
    if anomaly_3d:return Y,"涨幅偏离",-1
    if dif>dea and vr>1.3 and j9<80:return Y,"放量突破",1
    if bias6<-15 and dif>dea:return Y,"超跌反弹",1
    if bias6>15 and dif<dea:return R,"过热死叉",-1
    if bias6<-8:return R,"急跌",-1         # 单日跌>3%, KDJ可能滞后
    # KDJ方向
    if j9>k9>d9:return Y,"震荡偏多",1
    if j9<k9<d9:return R,"震荡偏空",-1
    # MACD柱方向
    if dif>dea:return Y,"动能偏强",0
    if dif<dea:return R,"动能偏弱",0
    return W,"中性",0

# --- 防爬与限流 ---
_UAS=[
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
]
_DC_HDRS={"User-Agent":_UAS[0],"Referer":"https://data.eastmoney.com/"}
def _rh():
  """随机请求头（东财类）"""
  return {"User-Agent":random.choice(_UAS),"Referer":"https://data.eastmoney.com/"}
def _throttle():
  """API调用间随机延迟，防爬"""
  time.sleep(random.uniform(0.2, 0.5))
def count_anomaly_ann(code, months=3):
  """统计近N月异常波动公告次数"""
  raw=code[-6:] if len(code)>=6 else code
  try:
    _throttle()
    url=f'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=50&page_index=1&ann_type=A&stock_list={raw}&f_node=0&s_node=0'
    r=requests.get(url,headers=_rh(),timeout=8)
    if r.status_code==200:
      items=(r.json().get('data') or {}).get('list') or []
      now=datetime.datetime.now()
      cut=(now-datetime.timedelta(days=months*30)).strftime('%Y-%m-%d')
      cnt=0;titles=[]
      for item in items:
        d=(item.get('notice_date') or '')[:10]
        if d>=cut and '异常波动' in item.get('title',''):
          cnt+=1
          titles.append(item['title'][:20])
      return cnt
  except:pass
  return 0
# --- 个股事件多源交叉验证（东财直连，~1s/只） ---
EVT_CACHE={}
EVT_LONG_DETAILS={}
_DC_UA="Mozilla/5.0"
_DC_REF="https://data.eastmoney.com/"
def _make_event_tag(title, typ):
  """从公告标题提取短标签（≤6字），用于表格事件列"""
  if typ=="zc":
    if "解除" in title:return "解质"
    if "延期" in title:return "质押延期"
    return "质押"
  if typ=="qy":
    if "减持" in title:
      if any(k in title for k in ["完成","届满","终止"]):return "减持完毕"
      return "减持计划"
    if "诉讼" in title:return "诉讼"
    if "立案" in title:return "立案"
    if "冻结" in title:return "冻结"
    if "亏损" in title:return "预亏"
    return "利空"
  if typ=="ba":
    if "中标" in title:return "中标"
    if "增持" in title:return "增持"
    if "回购" in title:return "回购"
    if "预增" in title:return "预增"
    if "扭亏" in title:return "扭亏"
    return "利好"
  return ""

def check_events(code, name, days=30):
  """东财直连API获取个股事件，返回 (emoji, 纯emoji, 短标签, 长描述)"""
  import datetime, requests, json
  raw_code=code[-6:] if len(code)>=6 else code
  key=f"{raw_code}_{days}"
  if key in EVT_CACHE:return EVT_CACHE[key]
  today=datetime.date.today()
  begin=(today-datetime.timedelta(days=days)).strftime("%Y-%m-%d")
  ba=[];qy=[];zc=[]
  try:
    url=f"https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=30&page_index=1&ann_type=A&stock_list={raw_code}&f_node=0&s_node=0"
    r=requests.get(url, headers={"User-Agent":_DC_UA,"Referer":_DC_REF}, timeout=10)
    if r.status_code==200:
      data=r.json()
      items=(data.get("data") or {}).get("list") or []
      for item in items:
        d=(item.get("notice_date") or "")[:10]
        t=item.get("title","")
        if d>=begin:
          if "质押" in t:zc.append((d,t,"DC"))
          neg_kws=["减持","诉讼","立案","调查","冻结","处罚","违规","亏损"]
          is_neg=False
          for kw in neg_kws:
            idx=t.find(kw)
            if idx>=0:
              prefix=t[max(0,idx-2):idx]
              pretxt=t[:idx]
              if not any(n in pretxt for n in ["未","无","不"]):
                is_neg=True;break
          if is_neg:qy.append((d,t,"DC"))
          if any(k in t for k in ["增持","回购","中标","预增","扭亏"]):ba.append((d,t,"DC"))
  except:pass
  # 三版本: 纯emoji(表格) / 短标签(表格) / 长描述(提示区)
  short_parts=[]
  tag_parts=[]
  long_parts=[]
  for cat,emoj,typ in [(zc,"🔒","zc"),(qy,"👎","qy"),(ba,"👍","ba")]:
    if not cat:continue
    short_parts.append(emoj)
    latest=max(cat,key=lambda x:x[0]);d,t,s=latest
    tag_parts.append(f"{emoj}{_make_event_tag(t,typ)}")
    sub=t
    for rm in ["关于","公告","控股股东部分股份","实施情况","及提前终止"]:sub=sub.replace(rm,"")
    sub=sub.strip().rstrip("的,").strip()
    if ":" in sub:sub=sub.split(":",1)[-1].strip()
    # P4: 移除公司名前缀（过渡词前的内容）
    for tr in ["办理","收到","发布","披露","拟","召开","完成","解除","签署","部分","计划"]:
      idx=sub.find(tr)
      if 0<idx<8:
        sub=sub[idx:]
        break
    # P4: 优先在逗号/顿号处断句
    if len(sub)>45:
      for sep in [",","，","、",";","；"]:
        idx=sub.find(sep,10,45)
        if idx>0:sub=sub[:idx];break
      else:sub=sub[:42]+"..."
    long_parts.append(f"{emoj}{sub}")
  if not short_parts:
    EVT_CACHE[key]=(None,"","","")
    return (None,"","","")
  short_str="".join(short_parts)
  tag_str=" | ".join(tag_parts)
  long_str=" | ".join(long_parts)
  EVT_CACHE[key]=("⚡",short_str,tag_str,long_str)
  return ("⚡",short_str,tag_str,long_str)

def run_portfolio():
  """自选组合池：相对大盘强弱矩阵 + MACD+BOLL+KDJ组合信号"""
  import json,os
  hdr("Hermes Signal Compass - Portfolio - "+now())
  pf_path=os.path.join(_app_dir(),"portfolio.json")
  if not os.path.exists(pf_path):
    print("  还没有 portfolio.json")
    print("  在项目目录创建,格式:")
    print('  {"A":["sh600519","sz300750"],"US":["gb_nvda","gb_aapl"]}')
    return
  try:
    with open(pf_path,"r",encoding="utf-8") as f:pf=json.load(f)
  except:
    print("  portfolio.json 格式错误");return
  a_lst=pf.get("A",[]);us_lst=pf.get("US",[])
  if not a_lst and not us_lst:print("  portfolio.json 为空");return
  # 一次批量获取所有行情
  all_codes=a_lst+us_lst
  if len(all_codes)<=20:
    q=sina_q(all_codes)
  else:
    q=sina_q(all_codes[:20])
  # 基准指数
  ba=sina_q(["sh000001"]);bu=sina_q(["gb_spy"]);cy=sina_q(["sz399006"]);st50=sina_q(["sh000688"])
  etf=sina_q(["sh512800","sh512480","sh515000","sh510050","sh512010"])
  ba_chg=(ba.get("sh000001") or {}).get("chg",0)
  bu_chg=(bu.get("gb_spy") or {}).get("chg",0)
  cy_chg=(cy.get("sz399006") or {}).get("chg",0)
  star50_chg=(st50.get("sh000688") or {}).get("chg")  # 统一用sina_q实时
  rows=[]
  # A股（含组合信号）
  for code in a_lst:
    d=q.get(code)
    if not d or d.get("p") is None:continue
    p,chg=d["p"],d.get("chg",0)
    bm=_pick_benchmark(code,ba_chg,cy_chg,star50_chg)
    rel=chg-bm
    # P3: 绝对涨跌幅前缀
    abs_pfx=""
    if chg>5:abs_pfx="🔥"
    elif chg<-5:abs_pfx="⚠️"
    hint="抗跌" if rel>0.5 else "跟跌" if rel>-0.5 else "领跌"
    if rel>1:hint="⭐抗跌"
    hint=abs_pfx+hint
    col=G if rel>0 else R
    lbl=d.get("name","")[:4]
    # 获取K线算组合信号
    sig_emoji=sig_txt=evt_str=""
    anomaly_tag=""
    try:
      kd=sina_k(code,35)
      if kd:
        em,tx,_=get_signal(kd)
        sig_emoji=em;sig_txt=tx
        # 额外检查3日严重异动（交易所标准）
        c=kd.get("c",[])
        if len(c)>=6:
          d1=(c[-3]-c[-4])/c[-4]*100 if c[-4]!=0 else 0
          d2=(c[-2]-c[-3])/c[-3]*100 if c[-3]!=0 else 0
          d3=(c[-1]-c[-2])/c[-2]*100 if c[-2]!=0 else 0
          if d1+d2+d3>=20:anomaly_tag="3日偏离>20%"
    except:pass
    # 量比(5日均)
    vr=None
    try:
      if kd:
        v=kd.get("v",[])
        if len(v)>=5:
          avg5=sum(v[-5:])/5
          if avg5>0:vr=round(v[-1]/avg5,2)
    except:pass
    # 多源交叉验证事件
    try:
      em2,short_evt,tag_evt,long_evt=check_events(code,"",30)
      if tag_evt:
        evt_str=tag_evt
        if long_evt:EVT_LONG_DETAILS[lbl]=long_evt
    except:pass
    # 颜色覆盖逻辑: 严重信号时强制降级观察栏
    if sig_emoji==R and any(k in sig_txt for k in ["严重异动","预警","回避"]):
      col=Y
      hint=hint.replace("⭐","")
    # 新增: 异动公告次数
    anomaly_cnt=0
    try:
      anomaly_cnt=count_anomaly_ann(code,3)
    except:pass
    bm_label=_benchmark_label(code)
    rows.append((lbl,p,chg,vr,rel,hint,col,sig_emoji,sig_txt,evt_str,anomaly_tag,anomaly_cnt,bm_label))
  # 美股（无K线信号）
  for code in us_lst:
    d=q.get(code)
    if not d or d.get("p") is None:continue
    p,chg=d["p"],d.get("chg",0)
    rel=chg-bu_chg
    abs_pfx=""
    if chg>5:abs_pfx="🔥"
    elif chg<-5:abs_pfx="⚠️"
    hint="抗跌" if rel>0.5 else "跟跌" if rel>-0.5 else "领跌"
    if rel>1:hint="⭐抗跌"
    hint=abs_pfx+hint
    col=G if rel>0 else R
    lbl=code[3:].upper()  # gb_nvda→NVDA
    rows.append((lbl,p,chg,None,rel,hint,col,"","","","","",0,""))
  if not rows:print("  无可用数据");return
  # 表格输出（CJK感知对齐）
  from cjk_table import Table
  tbl=Table(["代码","价格","涨跌","量比","相对大盘","观察","信号","事件"])
  for lbl,p,chg,vr,rel,hint,col,se,st,evt,antag,ac,bm_label in rows:
    sig_cell="{} {}".format(se,st) if se else ""
    # 事件列: 标签化事件 + 🟡异常偏离
    evt_display=evt
    if antag:
      atag="🟡异常偏离"
      evt_display=(evt+" | "+atag) if evt else atag
    rel_color=G if rel>0 else R
    rel_str="{}{:>+.2f}%({})".format(rel_color,rel,bm_label) if bm_label else "{}{:>+.2f}%".format(rel_color,rel)
    vr_str="{:.2f}x".format(vr) if vr is not None else "-"
    tbl.add_row([lbl,"{:>8.2f}".format(p),"{:>+.2f}%".format(chg),
                 vr_str,rel_str,"{} {}".format(col,hint),sig_cell,evt_display])
  print(tbl)
  # P6: 信号分布统计
  g_cnt=sum(1 for _,_,_,_,_,_,_,se,_,_,_,_,_ in rows if se==G)
  y_cnt=sum(1 for _,_,_,_,_,_,_,se,_,_,_,_,_ in rows if se==Y)
  r_cnt=sum(1 for _,_,_,_,_,_,_,se,_,_,_,_,_ in rows if se==R)
  w_cnt=sum(1 for _,_,_,_,_,_,_,se,_,_,_,_,_ in rows if se==W)
  n_cnt=sum(1 for _,_,_,_,_,_,_,se,_,_,_,_,_ in rows if not se)
  evt_cnt=sum(1 for _,_,_,_,_,_,_,_,_,evt,_,_,_ in rows if evt)
  antag_cnt=sum(1 for _,_,_,_,_,_,_,_,_,_,antag,_,_ in rows if antag)
  parts=[]
  if g_cnt:parts.append("🟢{}中性/偏多".format(g_cnt))
  if y_cnt:parts.append("🟡{}关注".format(y_cnt))
  if r_cnt:parts.append("🔴{}预警".format(r_cnt))
  if w_cnt:parts.append("⬜{}中性".format(w_cnt))
  if n_cnt:parts.append("⚪{}无信号".format(n_cnt))
  summary="信号: "+" ".join(parts)
  if evt_cnt:summary+=" | {}有事件".format(evt_cnt)
  if antag_cnt:summary+=" | {}异常偏离".format(antag_cnt)
  print("  [健康度] "+summary)
  # 联动提示
  bench_line="  [基准] 上证 {:+.2f}%".format(ba_chg)
  if star50_chg is not None:
    bench_line+=" | 科创50 {:+.2f}%".format(star50_chg)
  bench_line+=" | SPY {:+.2f}%".format(bu_chg)
  print(bench_line)
  # 板块风格比率
  bank=etf.get("sh512800");tech=etf.get("sh515000");semi=etf.get("sh512480")
  sh50=etf.get("sh510050");med=etf.get("sh512010")
  sfx=[]
  if bank and tech and None not in (bank.get("chg"),tech.get("chg")):
    btd=bank["chg"]-tech["chg"]
    sfx.append("银行-科技{:+.2f}%".format(btd))
  if semi and tech and None not in (semi.get("chg"),tech.get("chg")):
    st=semi["chg"]-tech["chg"]
    sfx.append("半导体-科技{:+.2f}%".format(st))
  if sh50 and tech and None not in (sh50.get("chg"),tech.get("chg")):
    lv=sh50["chg"]-tech["chg"]
    sfx.append("上证50-科技{:+.2f}%".format(lv))
  if med and tech and None not in (med.get("chg"),tech.get("chg")):
    mt=med["chg"]-tech["chg"]
    sfx.append("医药-科技{:+.2f}%".format(mt))
  if sfx:print("  风格: "+" | ".join(sfx))
  # 组合池提示（按优先级排序 + 同股合并）
  raw_tips=[]  # (priority, nm, line)
  for lbl,p,chg,vr,rel,hint,col,se,st,evt,antag,ac,bm_label in rows:
    nm=lbl
    evt_detail=EVT_LONG_DETAILS.get(nm,"")
    is_severe=("回避" in st or "预警" in st or "偏空" in st or "急跌" in st or "异动" in st or "死叉" in st or ("偏多" in st and chg<-3))
    is_green=(se==G)
    # 无有效信号(⬜中性不算)/无事件/无异常偏离 → 跳过
    if (not se or se==W) and not evt and not antag:continue
    # 严重信号优先处理（含合并子备注）
    if is_severe:
      # 主风险线
      dd=abs(chg)  # 跌幅
      if "🔒" in evt:
        raw_tips.append((0,nm,f"🔴{st}+质押 → 双重风险, 强烈建议规避"))
      elif "👎" in evt:
        raw_tips.append((0,nm,f"🔴{st}+减持 → 趋势弱+利空, 强烈建议规避"))
      elif "偏多" in st and chg<-3:
        if dd>8:raw_tips.append((0,nm,f"⚠️偏多但暴跌{dd:.0f}% → MA可能即将破位, 建议止损"))
        elif dd>5:raw_tips.append((0,nm,f"⚠️偏多但重跌{dd:.0f}% → 建议减仓, 等MA确认方向"))
        else:raw_tips.append((0,nm,f"⚠️偏多但转弱{dd:.0f}% → 趋势可能逆转, 暂不建议加仓"))
      else:
        if dd>8:raw_tips.append((0,nm,f"🔴{st}暴跌{dd:.0f}% → 建议果断止损"))
        elif dd>5:raw_tips.append((0,nm,f"🔴{st}重跌{dd:.0f}% → 建议减仓观望"))
        else:raw_tips.append((0,nm,f"🔴{st} → 趋势偏弱, 注意风险"))
      # 辅助分析: 异动公告历史 + 板块关联
      sub=[]
      if ac:sub.append(f"近3月触{ac}次异动公告")
      if "领涨" in hint or "抗跌" in hint:
        if star50_chg is not None and star50_chg>1:
          sub.append(f"科创50涨{star50_chg:.1f}%板块推动")
        elif chg>0.5:
          if rel>3:
            sub.append(f"⚠️矛盾: 偏空({st})+强抗跌({rel:+.1f}%), 建议人工判断")
          else:
            sub.append(f"偏空却逆势上涨{chg:+.1f}%, 小心拉高出货")
        else:
          sub.append(f"偏空但抗跌({chg:+.1f}%), 观察能否守住")
      if antag:sub.append("异动公告已发")
      if sub:
        raw_tips.append((1,nm,f"  注: {' | '.join(sub)}"))
      # 事件详情（严重信号已表明方向，附事件增加透明度）
      if evt_detail:
        raw_tips.append((1,nm,f"  事件: {evt_detail}"))
      continue
    if antag:
      line="交易所要求发异动公告"
      if ac:line+=f" | 近3月触{ac}次"
      raw_tips.append((2,nm,line))
      if evt_detail:raw_tips.append((2,nm,f"  事件: {evt_detail}"))
      continue
    # 利好出尽: 有利好+领跌
    if "👍" in evt and "领跌" in hint:
      raw_tips.append((2,nm,"利好出尽? 有利好却领跌, 高位出货信号"))
      if evt_detail:raw_tips.append((2,nm,f"  事件: {evt_detail}"))
      continue
    # 仅事件无信号（利好类）
    if evt and (not se or se==W):
      if evt_detail:raw_tips.append((3,nm,f"事件: {evt_detail}"))
      else:raw_tips.append((3,nm,"事件关注"))
    # 其他弱信号
    raw_tips.append((4,nm,st or ""))
  # 按优先级(priority)排序，同优先级按名称
  if raw_tips:
    raw_tips.sort(key=lambda x:(x[0],x[1]))
    # 动态上限: 严重项(prio=0+其sub)不限量, 次要项限4条
    severe_names={x[1] for x in raw_tips if x[0]==0}
    severe=[x for x in raw_tips if x[1] in severe_names]
    others=[x for x in raw_tips if x[1] not in severe_names]
    shown=severe+others[:4]
    if len(shown)<len(raw_tips):
      shown.append((99,"",f"... 还有{len(raw_tips)-len(shown)}条隐藏"))
    print("  ── 组合池提示 ──")
    last_nm=None
    for _,nm,line in shown:
      if not nm:
        print(f"  {line}")
      elif nm!=last_nm:
        print(f"  {nm} {line}")
        last_nm=nm
      else:
        print(f"  {'':>4}{line}")
  print("  "+"\u2550"*50)

def edit_portfolio():
  """交互式编辑自选组合池"""
  import json
  pf_path=os.path.join(_app_dir(),"portfolio.json")
  pf={"A":[],"US":[]}
  if os.path.exists(pf_path):
    try:
      with open(pf_path,"r",encoding="utf-8") as f:pf=json.load(f)
    except:pass
  while True:
    hdr("编辑自选池")
    a_lst=list(pf.get("A",[]))
    us_lst=list(pf.get("US",[]))
    print("  当前持仓：")
    if a_lst:
      for i,c in enumerate(a_lst,1):print(f"  A{i}. {c}")
    else:print("  A股: (空)")
    if us_lst:
      for i,c in enumerate(us_lst,1):print(f"  U{i}. {c}")
    else:print("  美股: (空)")
    print("\n  [A]添加  [D]删除  [Q]返回")
    c=input("  选择: ").strip().upper()
    if c=="Q":break
    elif c=="A":
      raw=input("  输入代码 (如 600519/NVDA): ").strip()
      if not raw:continue
      raw=raw.lower()
      if raw.startswith("gb_") or raw.startswith("gb."):
        code=raw
      elif raw.startswith("sh") or raw.startswith("sz") or raw.startswith("bj"):
        code=raw
      elif raw.isdigit() and len(raw)==6:
        code=("sh" if raw.startswith("6") else "sz")+raw
      elif raw.isalpha() and len(raw)<=5:
        code="gb_"+raw
      else:
        print("  ❌ 无法识别格式，试试: 600519 / sh600519 / NVDA / gb_nvda")
        input("  按 Enter 继续...");continue
      if code in a_lst+us_lst:
        print(f"  ⚠️ {code} 已在池中");input("  按 Enter 继续...");continue
      if code.startswith("gb_"):us_lst.append(code)
      else:a_lst.append(code)
      pf["A"],pf["US"]=a_lst,us_lst
      with open(pf_path,"w",encoding="utf-8") as f:json.dump(pf,f,indent=2)
      print(f"  ✅ 已添加 {code}")
      input("  按 Enter 继续...")
    elif c=="D":
      raw=input("  输入序号 (如 A1 / U2): ").strip().upper()
      if len(raw)<2:continue
      prefix,idx=raw[0],raw[1:]
      try:idx=int(idx)-1
      except:print("  ❌ 格式: A1 / U2");input("  按 Enter 继续...");continue
      if prefix=="A" and 0<=idx<len(a_lst):
        rem=a_lst.pop(idx);pf["A"]=a_lst
        with open(pf_path,"w",encoding="utf-8") as f:json.dump(pf,f,indent=2)
        print(f"  ✅ 已删除 {rem}")
      elif prefix=="U" and 0<=idx<len(us_lst):
        rem=us_lst.pop(idx);pf["US"]=us_lst
        with open(pf_path,"w",encoding="utf-8") as f:json.dump(pf,f,indent=2)
        print(f"  ✅ 已删除 {rem}")
      else:print("  ❌ 序号无效")
      input("  按 Enter 继续...")

def main_menu():
  """交互式主菜单（双击exe/Python直接跑）"""
  while True:
    hdr("Hermes Signal Compass")
    print("  1. US 大盘模式")
    print("  2. A 股大盘模式")
    print("  3. 复盘趋势")
    print("  4. 自选组合池")
    print("  5. 编辑自选池")
    print("  0. 退出")
    print("  "+HR)
    try:c=input("  选择 [0-5]: ").strip()
    except(EOFError,KeyboardInterrupt):break
    if c=="1":run_us()
    elif c=="2":run_a()
    elif c=="3":run_review()
    elif c=="4":run_portfolio()
    elif c=="5":edit_portfolio()
    elif c in("0","q","exit"):break
    else:print("  无效输入");continue
    try:input("\n  按 Enter 返回菜单...")
    except(EOFError,KeyboardInterrupt):break

if __name__=="__main__":
  if len(sys.argv)>1:
    a=sys.argv[1][:2].lower()
    if a=="a":run_a()
    elif a in("us","-u"):run_us()
    elif a in("re","-r"):run_review()
    elif a in("pf","po","-p"):run_portfolio()
    else:run_us()
  else:
    main_menu()