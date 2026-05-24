"""compass v2.4 100只回测 + 数据存档"""
import baostock as bs, sys, json, datetime

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
            
            sv = snap['v']
            vr = sv[-1] / (sum(sv[-5:])/5) if len(sv)>=5 and sum(sv[-5:])>0 else None
            
            enh, jz, cb, wl = enhanced_rsc(kd, ed, baseline, vr)
            
            fi = min(idx + 63, len(kd['c'])-1)
            fwd = (kd['c'][fi] - kd['c'][idx]) / kd['c'][idx] * 100
            
            results.append({
                'code':code, 'date':ed,
                'base_rsc':baseline, 'enh_rsc':enh,
                'jizhang':jz, 'chaoba':cb, 'wuli':wl,
                'fwd_3m':round(fwd,2),
                'price':round(kd['c'][idx],2),
                'price_fwd':round(kd['c'][fi],2)
            })
    except Exception as e:
        pass
    
    if (i+1) % 20 == 0: print(f"  {i+1}/{len(stocks)}")

bs.logout()

# 存档
out = {
    'meta': {
        'source': 'baostock', 'adjust': 'qfq',
        'eval_dates': eval_dates, 'fwd_days': 63,
        'total_points': len(results), 'stocks': len(stocks),
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    },
    'data': results
}

path = r"C:\Users\coolt\Desktop\signal_compass\backtest_results.json"
with open(path, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"已存: {path} ({len(results)}条)")
# 验证可读
with open(path, 'r', encoding='utf-8') as f:
    check = json.load(f)
print(f"验证: {len(check['data'])}条, 首条: {check['data'][0]}")
