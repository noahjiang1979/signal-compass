"""compass v2.4 100只回测 — Baostock数据源"""
import baostock as bs, sys, datetime

bs.login()
sys.path.insert(0, r"C:\Users\coolt\Desktop\signal_compass")
from compass import get_signal

def baostock_k(code, start='2025-01-01', end='2026-05-24'):
    raw = code[-6:] if len(code)>6 else code
    prefix = 'sz' if raw.startswith(('0','3','2')) else 'sh'
    symbol = f"{prefix}.{raw}"
    rs = bs.query_history_k_data_plus(symbol,
        "date,open,high,low,close,volume", 
        start_date=start, end_date=end, frequency="d", adjustflag="2")
    dates, c_arr, h_arr, l_arr, v_arr = [], [], [], [], []
    while rs.next():
        r = rs.get_row_data()
        if r[4] == '' or len(r[1])==0: continue
        dates.append(r[0]); c_arr.append(float(r[4]))
        h_arr.append(float(r[2])); l_arr.append(float(r[3]))
        v_arr.append(float(r[5]))
    return {'dates': dates, 'c': c_arr, 'h': h_arr, 'l': l_arr, 'v': v_arr}

def enhanced_rsc(kd_full, snapshot_date, baseline_rsc, vr, mkt=0):
    c = kd_full['c']; dates = kd_full['dates']
    rsc = baseline_rsc
    idx = dates.index(snapshot_date)
    snap_c = c[:idx+1]
    p = snap_c[-1]
    has_jz = has_cb = has_wl = False
    
    if len(snap_c) >= 21:
        chg_20d = (snap_c[-1] - snap_c[-21]) / snap_c[-21] * 100 if snap_c[-21] != 0 else 0
        ma20 = sum(snap_c[-20:]) / 20
        vs_ma20 = (p - ma20) / ma20 * 100 if ma20 > 0 else 0
        hi20 = max(snap_c[-20:])
        
        has_jz = chg_20d > 50
        has_cb = vs_ma20 > 25
        
        if p < hi20 * 0.95 and vs_ma20 > -5 and rsc >= 0:
            rsc = max(rsc - 1, -1)
            has_wl = True
        
        if vr is not None and vr < 0.7 and rsc >= 2:
            rsc -= 1
        
        if mkt >= 1 and rsc <= -1: rsc += 1
        elif mkt <= -1 and rsc >= 1: rsc -= 1
    
    return rsc, has_jz, has_cb, has_wl

# 股票池
stocks = [
    "sh600519","sz000858","sz300750","sh601318","sz000333","sh600036","sh600900",
    "sz002415","sh600276","sz000651","sh601012","sz002594","sz300059","sh600030",
    "sh601398","sz000001","sh600050","sz300124","sh688981","sz002475","sh600809",
    "sz000568","sh601888","sz002230","sh600585","sz000725","sh603259","sz300274",
    "sh600031","sz000063","sh688111","sz300760","sh600438","sz002714","sh601899",
    "sz300433","sh600104","sz000002","sh688036","sz300896","sh601857","sz002049",
    "sh600570","sz000538","sh688012","sz300142","sh600887","sz002129","sh688396",
    "sz300308","sh601088","sz000625","sh688008","sz300450","sh600690","sz002241",
    "sh600019","sz000977","sh688126","sz300782","sh600048","sz002352","sh688187",
    "sz300413","sh601225","sz002459","sh688599","sz300207","sh600309","sz000157",
    "sh600893","sz002850","sh688065","sz300724","sh601615","sz000776","sh688303",
    "sz300073","sh600703","sz002074","sh688390","sz300496","sh601006","sz000733",
    "sh600118","sz002032","sh688777","sz300014","sh601138","sz000988","sh688223",
    "sz300628","sh600998","sz002812","sh688256","sz300919","sh600941","sz001289",
]

eval_dates = ['2025-08-29','2025-11-28','2026-02-27']
results = []
errors = 0

for i, code in enumerate(stocks):
    try:
        kd = baostock_k(code, '2025-01-01', '2026-05-24')
        if len(kd['c']) < 120: continue
        
        for ed in eval_dates:
            if ed not in kd['dates']: continue
            idx = kd['dates'].index(ed)
            snap = {'c': kd['c'][:idx+1], 'h': kd['h'][:idx+1], 
                     'l': kd['l'][:idx+1], 'v': kd['v'][:idx+1]}
            em, tx, baseline = get_signal(snap)
            if baseline is None: continue
            
            # 量比
            sv = snap['v']
            vr = sv[-1] / (sum(sv[-5:])/5) if len(sv)>=5 and sum(sv[-5:])>0 else None
            
            enh, jz, cb, wl = enhanced_rsc(kd, ed, baseline, vr)
            
            # 前向63交易日 (~3月)
            fi = min(idx + 63, len(kd['c'])-1)
            fwd = (kd['c'][fi] - kd['c'][idx]) / kd['c'][idx] * 100
            
            results.append({
                'code':code,'date':ed,'base':baseline,'enh':enh,
                'jz':jz,'cb':cb,'wl':wl,'fwd':fwd
            })
    except Exception as e:
        errors += 1
        if errors <= 3: print(f"  {code}: {e}")
    
    if (i+1) % 20 == 0: print(f"  进度: {i+1}/{len(stocks)}")

bs.logout()

print(f"\n回测完成: {len(results)}点, {errors}错误")

# === 统计 ===
print("\n=== 胜率对比 ===")
for tag, cond in [("r>=2", lambda r:r>=2), ("r=0", lambda r:r==0), ("r<=-2", lambda r:r<=-2)]:
    b_list = [r for r in results if cond(r['base'])]
    e_list = [r for r in results if cond(r['enh'])]
    bw = sum(1 for r in b_list if r['fwd']>0)/len(b_list)*100 if b_list else 0
    ew = sum(1 for r in e_list if r['fwd']>0)/len(e_list)*100 if e_list else 0
    ba = sum(r['fwd'] for r in b_list)/len(b_list) if b_list else 0
    ea = sum(r['fwd'] for r in e_list)/len(e_list) if e_list else 0
    print(f"  {tag}: 基准 {bw:.0f}%({len(b_list)})→增强 {ew:.0f}%({len(e_list)}) | 均收益 {ba:+.1f}%→{ea:+.1f}%")

# 总体
btot = sum(1 for r in results if (r['base']>0 and r['fwd']>0) or (r['base']<0 and r['fwd']<0))
etot = sum(1 for r in results if (r['enh']>0 and r['fwd']>0) or (r['enh']<0 and r['fwd']<0))
print(f"  总体方向一致: 基准 {btot/len(results)*100:.0f}% → 增强 {etot/len(results)*100:.0f}%")

# 标签效果
jz = [r for r in results if r['jz']]
wl = [r for r in results if r['wl']]
cb = [r for r in results if r['cb']]
print(f"\n[急涨]{len(jz)}次 均收益{sum(r['fwd'] for r in jz)/len(jz):+.1f}%" if jz else "\n[急涨] 无触发")
print(f"[超拔]{len(cb)}次 均收益{sum(r['fwd'] for r in cb)/len(cb):+.1f}%" if cb else "[超拔] 无触发")
print(f"[无力]{len(wl)}次 均收益{sum(r['fwd'] for r in wl)/len(wl):+.1f}%" if wl else "[无力] 无触发")

# 信号迁移
up = sum(1 for r in results if r['enh'] > r['base'])
dn = sum(1 for r in results if r['enh'] < r['base'])
same = sum(1 for r in results if r['enh'] == r['base'])
print(f"\n信号迁移: ↑{up} ←{same} ↓{dn}  (增强vs基准)")
