"""BDDK Aylık Bülten -> raw/*.txt  (satır biçimi: GRUP+YYAA|v1;v2;...)
Kullanım:  python fetch_bddk.py [--start 2022-01] [--end 2026-08]
Sonra:     python rapor.py <pdf> ; python export_web.py ; python build_xlsx.py <xlsx>   (hepsini update.py çalıştırır)

Kaynak: BDDK Aylık Bülten "Temel Gösterim" servisi (BasitRaporGetir, POST, anahtar gerekmez).
Sertifika: BDDK sunucusu ara sertifikasını (GlobalSign RSA OV SSL CA 2018) göndermediğinden Python doğrulaması
başarısız olur; bddk_ca_bundle.pem = certifi paketi + o ara sertifika (verify= ile kullanılır).
"""
import requests, argparse, os, time, concurrent.futures as cf
URL='https://www.bddk.org.tr/BultenAylik/tr/Home/BasitRaporGetir'
BUNDLE=os.path.join(os.path.dirname(os.path.abspath(__file__)),'bddk_ca_bundle.pem')
HEADERS={'X-Requested-With':'XMLHttpRequest','User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'}
G={'Sektör':'S','Mevduat':'M','Mevduat-Yerli Özel':'YO','Mevduat-Kamu':'KA','Mevduat-Yabancı':'YA','Katılım':'KB','Kalkınma ve Yatırım':'KY'}
TARAF=['10001','10003','10002','10009','10008','10010','10004']
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),'raw')

def fetch(tab,y,m,pb='TL'):
    data=[('tabloNo',tab),('yil',y),('ay',m),('paraBirimi',pb)]+[('taraf',t) for t in TARAF]
    for deneme in range(3):
        try:
            r=requests.post(URL,data=data,timeout=60,headers=HEADERS,verify=BUNDLE); r.raise_for_status()
            j=r.json(); break
        except Exception:
            if deneme==2: raise
            time.sleep(3*(deneme+1))
    assert j['success'], j.get('error')
    by={}
    for x in j['Json']['data']['rows']:
        g=G.get(x['cell'][0]);
        if g: by.setdefault(g,{})[x['cell'][1]]=x['cell'][4:]
    return by

def ay_var_mi(y,m):
    """BDDK'da (y,m) dönemi için sektör bilançosu yayımlanmış mı? (toplam aktif > 0)"""
    try:
        b=fetch(1,y,m)
        return bool(b.get('S') and b['S'].get(26) and float(b['S'][26][2])>0)
    except Exception:
        return False

def latest_available(max_back=6):
    """Bugünden geriye giderek BDDK'da verisi olan ilk ayı 'YYYY-MM' olarak döndürür."""
    import datetime as dt
    d=dt.date.today().replace(day=1)
    for _ in range(max_back):
        d=(d-dt.timedelta(days=1)).replace(day=1)
        if ay_var_mi(d.year,d.month): return f"{d.year}-{d.month:02d}"
    raise SystemExit('BDDK verisine ulaşılamadı')

def months(a,b):
    y0,m0=map(int,a.split('-')); y1,m1=map(int,b.split('-')); out=[]
    y,m=y0,m0
    while (y,m)<=(y1,m1):
        out.append((y,m)); m+=1
        if m>12: y,m=y+1,1
    return out

SPEC={  # name: (tabloNo, para birimi, from, selector(rows)->list)
 'T1':(1,'TL',None,lambda r:[sum(r[i][0] for i in [1,2,3,4,7,8,9]),sum(r[i][1] for i in [1,2,3,4,7,8,9]),r[5][0]+r[6][0]+r[22][0],r[5][1]+r[6][1]+r[22][1],r[10][0],r[10][1],r[11][0],r[11][1],r[20][0],r[20][1],r[15][2],r[26][0],r[26][1],r[27][0],r[27][1],r[28][0],r[28][1],r[31][0]+r[33][0]+r[36][0],r[31][1]+r[33][1]+r[36][1],r[41][0]+r[41][1],r[55][2],r[13][2],r[14][2]]),
 'T2':(2,'TL',None,lambda q:[q[15][2]+q[28][2],q[23][2],q[29][2]+q[31][2],q[41][2],q[46][2]+q[47][2]+q[49][2],q[30][2]+q[32][2]+q[33][2]+q[48][2],q[35][2]+q[37][2],q[42][2]+q[43][2]+q[44][2],q[25][2]+q[36][2]+q[38][2]+q[39][2]+q[40][2],q[52][2],q[53][2],q[1][2]+q[6][2],q[9][2]+q[10][2]+q[11][2],q[7][2]+q[8][2]+q[12][2]+q[13][2]+q[14][2],q[16][2],q[17][2]+q[19][2]+q[20][2],q[18][2]+q[21][2]+q[22][2],q[25][2],q[36][2],q[6][2]]),
 'T4':(4,'TL',None,lambda r:[r[i][2] for i in [1,2,3,4,9,12,13,14,15]]),
 'T4B':(4,'TL',None,lambda r:[r[16][2],r[17][2],r[18][2]]),
 'T6':(6,'TL',None,lambda r:[r[1][0],r[1][1],r[1][2],r[1][5]]),
 'T10':(10,'TL','2023-01',lambda r:[r[1][0]+r[14][0],r[1][6]+r[14][6],r[5][0]+r[17][0],r[5][6]+r[17][6],r[9][0]+r[20][0],r[9][6]+r[20][6]]),
 'T12':(12,'TL','2023-01',lambda r:[r[i][0] for i in [1,2,5,6,7]]),
 'T16':(16,'TL','2023-01',lambda r:[r[i][0] for i in [2,3,6,7]]),
 'TX':(1,'TL',None,None),   # handled specially (needs T1+T2 rows)
 'TU':(1,'USD',None,lambda r:[r[26][2]]),
}

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--start',default='2022-01'); ap.add_argument('--end',required=True); a=ap.parse_args()
    os.makedirs(OUT,exist_ok=True)
    M=months(a.start,a.end)
    cache={}
    def get(tab,y,m,pb='TL'):
        k=(tab,y,m,pb)
        if k not in cache: cache[k]=fetch(tab,y,m,pb)
        return cache[k]
    with cf.ThreadPoolExecutor(6) as ex:
        jobs=[(t,y,m,pb) for (y,m) in M for t,pb in [(1,'TL'),(2,'TL'),(4,'TL'),(6,'TL'),(10,'TL'),(12,'TL'),(16,'TL'),(1,'USD')]]
        for k,v in zip(jobs,ex.map(lambda j:fetch(*j),jobs)): cache[k]=v
    for name,(tab,pb,frm,sel) in SPEC.items():
        lines=[]
        for (y,m) in M:
            if frm and (y,m)<tuple(map(int,frm.split('-'))): continue
            b=get(tab,y,m,pb)
            for g in sorted(b):
                if name=='TU' and g!='S': continue
                key=f"{g}{str(y)[2:]}{m:02d}"
                try:
                    if name=='TX':
                        r=b[g]; q=get(2,y,m)[g]
                        vals=[r[18][0],r[18][1],r[22][0],r[22][1],r[56][0],r[56][1],q[13][2],q[21][2],q[28][2]]
                    else: vals=sel(b[g])
                except Exception:
                    continue   # grup için tablo yoksa (örn. KY mevduat) atla
                lines.append(key+'|'+';'.join(str(int(round(v))) for v in vals))
        open(os.path.join(OUT,name+'.txt'),'w',encoding='utf-8').write('\n'.join(sorted(lines))+'\n')
        print(name,len(lines))
    # snapshot: full balance sheet TP;YP rows 1..62 for last month and same month previous year
    y1,m1=M[-1]; lines=[]
    for (y,m) in [(y1-1,m1),(y1,m1)]:
        b=get(1,y,m)
        for g in sorted(b):
            lines.append(f"{g}{str(y)[2:]}{m:02d}|"+';'.join(f"{int(round(b[g][i][0]))};{int(round(b[g][i][1]))}" for i in range(1,63)))
    open(os.path.join(OUT,'TS.txt'),'w',encoding='utf-8').write('\n'.join(sorted(lines))+'\n'); print('TS',len(lines))
