import warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, re, os
RAW=os.path.join(os.path.dirname(os.path.abspath(__file__)),'raw')+os.sep
GROUPS=['S','KB','M','KA','YO','YA','KY']
DEPG=['S','KB','M','KA','YO','YA']  # mevduat kabul eden gruplar
GNAME={'S':'Bankacılık Sektörü','KB':'Katılım Bankaları','M':'Mevduat Bankaları','KA':'Kamu Mevduat Bankaları','YO':'Yerli Özel Mevduat Bankaları','YA':'Yabancı Mevduat Bankaları','KY':'Kalkınma ve Yatırım Bankaları'}
GSHORT={'S':'Sektör','KB':'Katılım','M':'Mevduat','KA':'Kamu Mevduat','YO':'Yerli Özel Mevduat','YA':'Yabancı Mevduat','KY':'Kalkınma-Yatırım'}

def load(name, cols):
    rows=[]
    for l in open(RAW+name+'.txt'):
        l=l.strip()
        if not l: continue
        k,v=l.split('|'); m=re.match(r'([A-Z]+)(\d{4})',k)
        g,ym=m.group(1),m.group(2)
        d=pd.Timestamp(2000+int(ym[:2]),int(ym[2:]),1)+pd.offsets.MonthEnd(0)
        rows.append([g,d]+[float(x) for x in v.split(';')])
    df=pd.DataFrame(rows,columns=['g','d']+cols)
    return df.set_index(['g','d']).sort_index()

T1=load('T1',['nakTP','nakYP','mkTP','mkYP','krTP','krYP','tkTP','tkYP','fkTP','fkYP','ozelKars','akTP','akYP','mvTP','mvYP','vdsTP','vdsYP','topTP','topYP','sermBz','ozk'])
T2=load('T2',['faizGel','faizGid','ucrGel','ucrGid','ticari','digGel','personel','digIsl','karsilik','vergi','netKar','krFaiz','mkFaiz','digFaizGel','mvFaiz','topFaiz','digFaizGid'])
T4=load('T4',['tuk','konut','tasit','ihtiyac','kk','tukKK','tkTuk','tkKonut','tkTasit'])
T4B=load('T4B',['tkIhtiyac','tkKK','tkTukKK'])
T6=load('T6',['kobiTP','kobiYP','kobi','tkKobi'])
T10=load('T10',['tlVds','tlTot','dthVds','dthTot','kmVds','kmTot'])
T12=load('T12',['anaSerm','katkiSerm','yasalOzk','cekirdek','rak'])
T16=load('T16',['subeYI','subeYD','persYI','persYD'])
TU=load('TU',['akUSD'])
TX=load('TX',['reeskTP','reeskYP','htmTP','htmYP','pasTP','pasYP','fkGel','fkGid','nakdiKom'])

D=T1.join(T2).join(T4).join(T4B).join(T6).join(T10).join(T12).join(T16).join(TX)
# USD/TRY rate from sector TL/USD total assets
rate=(T1.loc['S','akTP']+T1.loc['S','akYP'])/TU.loc['S','akUSD']
D=D.join(rate.rename('usd'),on='d')

# --- balance sheet aggregates (million TL) ---
D['aktif']=D.akTP+D.akYP
D['krediTP']=D.krTP+D.tkTP+D.fkTP; D['krediYP']=D.krYP+D.tkYP+D.fkYP   # gross loans incl NPL + leasing
D['canliTP']=D.krTP+D.fkTP; D['canliYP']=D.krYP+D.fkYP
D['canli']=D.canliTP+D.canliYP; D['kredi']=D.krediTP+D.krediYP
D['takip']=D.tkTP+D.tkYP; D['fk']=D.fkTP+D.fkYP
D['menkul']=D.mkTP+D.mkYP
D['mevduat']=D.mvTP+D.mvYP
D['km']=D.kmTot; D['ypFon']=D.mvYP-D.kmTot
D['vadeliTP']=D.mvTP-D.vdsTP; D['vadeliYP']=D.mvYP-D.vdsYP
D['ypVds_exKM']=D.vdsYP-D.kmVds; D['ypVdl_exKM']=D.vadeliYP-(D.kmTot-D.kmVds)
D['kmVdl']=D.kmTot-D.kmVds
D['vadesiz']=D.vdsTP+D.vdsYP; D['vadeli']=D.mevduat-D.vadesiz
D['toptan']=D.topTP+D.topYP
D['tuzel']=D.canli-D.tukKK
D['ticKur']=D.tuzel-D.kobi-D.fk
D['ticKurTP']=D.canliTP-D.tuk-D.kk-D.kobiTP-D.fkTP   # TP consumer ~ all consumer (YP negligible)
D['ticKurYP']=D.canliYP-D.kobiYP-D.fkYP
D['tkTicKur']=D.takip-D.tkTukKK-D.tkKobi
D['sube']=D.subeYI+D.subeYD; D['pers']=D.persYI+D.persYD
# USD amounts
for c in ['akYP','krediYP','canliYP','mvYP','mkYP','ypFon','vadeliYP','vdsYP']:
    D[c+'_usd']=D[c]/D.usd
D['pasifYP_usd']=D.akYP_usd

# --- helpers ---
def yoy(s): return s.groupby(level=0).transform(lambda x: x/x.shift(12)-1)*100
def ttm(s):
    # YTD -> trailing 12M : ytd(t) - ytd(t-12) + ytd(Dec of previous year)
    def f(x):
        x=x.copy(); dec=x[x.index.get_level_values(1).month==12]
        out=pd.Series(np.nan,index=x.index)
        for (g,d),v in x.items():
            prev=d-pd.DateOffset(years=1); prev=pd.Timestamp(prev)+pd.offsets.MonthEnd(0)
            decprev=pd.Timestamp(d.year-1,12,31)
            if (g,prev) in x.index and (g,decprev) in x.index:
                out[(g,d)]=v-x[(g,prev)]+x[(g,decprev)]
        return out
    return s.groupby(level=0,group_keys=False).apply(f)
def avg13(s): return s.groupby(level=0).transform(lambda x: x.rolling(13).mean())

for c in list(T2.columns)+['fkGel','fkGid','nakdiKom']: D[c+'_12']=ttm(D[c])
D['avgCanli']=avg13(D.canli)
D['avgMev']=avg13(D.mevduat)
D['avgAktif']=avg13(D.aktif); D['avgOzk']=avg13(D.ozk)
D['avgKredi']=avg13(D.kredi); D['avgVadeli']=avg13(D.vadeli); D['avgMenkul']=avg13(D.menkul)
D['avgToptan']=avg13(D.toptan+D.sermBz)

# --- derived income lines (YTD & 12M) ---
for suf in ['','_12']:
    D['netFaiz'+suf]=D['faizGel'+suf]-D['faizGid'+suf]
    D['netUcret'+suf]=D['ucrGel'+suf]-D['ucrGid'+suf]
    D['brutKar'+suf]=D['netFaiz'+suf]+D['netUcret'+suf]+D['ticari'+suf]+D['digGel'+suf]
    D['opex'+suf]=D['personel'+suf]+D['digIsl'+suf]
    D['vergiOncesi'+suf]=D['brutKar'+suf]-D['opex'+suf]-D['karsilik'+suf]

# --- ratios (%) ---
D['aktifTPag']=D.akTP/D.aktif*100
D['fonTPag']=D.mvTP/D.mevduat*100
D['tukCanli']=D.tukKK/D.canli*100
D['konutCanli']=D.konut/D.canli*100; D['tasitCanli']=D.tasit/D.canli*100
D['ihtiyacCanli']=D.ihtiyac/D.canli*100; D['kkCanli']=D.kk/D.canli*100
D['tuzelCanli']=D.tuzel/D.canli*100; D['ticCanli']=D.ticKur/D.canli*100
D['kobiCanli']=D.kobi/D.canli*100; D['fkCanli']=D.fk/D.canli*100
D['npl']=D.takip/D.kredi*100
D['ozelKarsOran']=D.ozelKars/D.takip*100
D['nplTuk']=D.tkTukKK/(D.tukKK+D.tkTukKK)*100
D['nplKobi']=D.tkKobi/(D.kobi+D.tkKobi)*100
D['nplTic']=D.tkTicKur/(D.ticKur+D.tkTicKur)*100
D['syr']=D.yasalOzk/D.rak*100; D['cekSyr']=D.cekirdek/D.rak*100; D['anaSyr']=D.anaSerm/D.rak*100
D['roa']=D.netKar_12/D.avgAktif*100; D['roe']=D.netKar_12/D.avgOzk*100
D['nim']=D.netFaiz_12/D.avgAktif*100
D['giderGelir']=D.opex_12/D.brutKar_12*100
D['opexAktif']=D.opex_12/D.avgAktif*100
D['krediGetiri']=(D.krFaiz_12+D.fkGel_12)/D.avgCanli*100
D['fonMaliyet']=D.mvFaiz_12/D.avgMev*100
D['tlKrediMev']=D.krediTP/D.mvTP*100; D['ypKrediMev']=D.krediYP/D.mvYP*100; D['krediMev']=D.kredi/D.mevduat*100
D['tlMkMev']=D.mkTP/D.mvTP*100; D['ypMkMev']=D.mkYP/D.mvYP*100; D['mkMev']=D.menkul/D.mevduat*100
D['mkTPak']=D.mkTP/D.akTP*100; D['mkYPak']=D.mkYP/D.akYP*100; D['mkAk']=D.menkul/D.aktif*100
D['subePers']=D.pers/D.sube
# income / avg assets decomposition (12M)
for c,n in [('netFaiz_12','roaNetFaiz'),('netUcret_12','roaUcret'),('ticari_12','roaTicari'),('digGel_12','roaDiger'),('opex_12','roaOpex'),('karsilik_12','roaKars'),('vergi_12','roaVergi'),('mkFaiz_12','mMenkul'),('mvFaiz_12','mFon'),('topFaiz_12','mToptan')]:
    D[n]=D[c]/D.avgAktif*100
D['mKredi']=(D.krFaiz_12+D.fkGel_12)/D.avgAktif*100
D['mDigGel']=(D.digFaizGel_12-D.fkGel_12)/D.avgAktif*100
D['mDigGid']=D.digFaizGid_12/D.avgAktif*100
D['ucrGelAk']=(D.ucrGel_12+D.nakdiKom_12)/D.avgAktif*100
D['netFaizBrut']=D.netFaiz_12/D.brutKar_12*100; D['netFaizOpex']=D.netFaiz_12/D.opex_12*100
D['ucrBrut']=(D.ucrGel_12+D.nakdiKom_12)/D.brutKar_12*100; D['ucrOpex']=(D.ucrGel_12+D.nakdiKom_12)/D.opex_12*100
# funds / total liabilities (liabilities = aktif - ozk)
D['yuk']=D.aktif
D['pasifTPag']=D.pasTP/D.aktif*100
D['pasYP_usd']=D.pasYP/D.usd
D['mkGr']=D.menkul-D.htmTP-D.htmYP+D.reeskTP+D.reeskYP
D['mkGrTP']=D.mkTP-D.htmTP+D.reeskTP; D['mkGrYP']=D.mkYP-D.htmYP+D.reeskYP; D['mkGrYP_usd']=D.mkGrYP/D.usd
D['tlVdlYuk']=D.vadeliTP/D.yuk*100; D['ypVdlYuk']=D.vadeliYP/D.yuk*100; D['vdlYuk']=D.vadeli/D.yuk*100
D['tlVdsYuk']=D.vdsTP/D.yuk*100; D['ypVdsYuk']=D.vdsYP/D.yuk*100; D['vdsYuk']=D.vadesiz/D.yuk*100
# growth series
GROW={'aktif':'aktif','akTP':'akTP','akYP_usd':'akYP_usd','canliTP':'canliTP','canliYP_usd':'canliYP_usd','canli':'canli',
      'mvTP':'mvTP','mvYP_usd':'mvYP_usd','pasTP':'pasTP','pasYP_usd':'pasYP_usd','mkGr':'mkGr','mkGrTP':'mkGrTP','mkGrYP':'mkGrYP','mkGrYP_usd':'mkGrYP_usd','vadeliYP_usd':'vadeliYP_usd','vdsYP_usd':'vdsYP_usd','mevduat':'mevduat','tukKK':'tukKK','konut':'konut','tasit':'tasit','ihtiyac':'ihtiyac','kk':'kk',
      'tuzel':'tuzel','ticKur':'ticKur','kobi':'kobi','fk':'fk','menkul':'menkul','mkTP':'mkTP','mkYP_usd':'mkYP_usd',
      'vadeliTP':'vadeliTP','vadeliYP':'vadeliYP','vadeli':'vadeli','vdsTP':'vdsTP','vdsYP':'vdsYP','vadesiz':'vadesiz',
      'sube':'sube','pers':'pers','ozk':'ozk','brutKar_12':'brutKar_12','netKar_12':'netKar_12','personel_12':'personel_12','digIsl_12':'digIsl_12','opex_12':'opex_12'}
for k,v in GROW.items(): D['g_'+k]=yoy(D[v])
# YTD growth (for income table): ytd vs ytd prev year same month
for c in ['faizGel','faizGid','netFaiz','ucrGel','ucrGid','netUcret','ticari','digGel','brutKar','personel','digIsl','opex','karsilik','vergiOncesi','vergi','netKar']:
    D['gy_'+c]=yoy(D[c])


def mdiff(s):
    def f(x):
        x=x.sort_index(); prev=x.shift(1)
        out=x-prev
        jan=x.index.get_level_values(1).month==1
        out[jan]=x[jan]
        return out
    return s.groupby(level=0,group_keys=False).apply(f)
D['netKar_m']=mdiff(D.netKar)
D['brutKar_m']=mdiff(D.brutKar)
def ann3(s): return s.groupby(level=0).transform(lambda x:((x/x.shift(3))**4-1)*100)
D['g3_canliTP']=ann3(D.canliTP); D['g3_mvTP']=ann3(D.mvTP); D['g3_aktifTP']=ann3(D.akTP)
D['g1_canliTP']=D.groupby(level=0).canliTP.transform(lambda x:(x/x.shift(1)-1)*100)
D['kaldirac']=D.aktif/D.ozk
D['ozkAktif']=D.ozk/D.aktif*100
D['ypGap']=(D.krediYP-D.mvYP)/D.aktif*100
D['roa_m']=D.netKar_m*12/D.aktif*100
_dep=['fonTPag','tlKrediMev','ypKrediMev','krediMev','tlMkMev','ypMkMev','mkMev','tlVdlYuk','ypVdlYuk','vdlYuk','tlVdsYuk','ypVdsYuk','vdsYuk','fonMaliyet','mFon','ypGap','g_mvTP','g_vadeliTP','g_vadeliYP','g_vadeli','g_vdsTP','g_vdsYP','g_vadesiz']
D=D.reset_index()
for c in _dep: D.loc[D.g=='KY',c]=np.nan
D=D.set_index(['g','d'])
D=D.reset_index()
LAST=D.d.max()
def at(g,d=None,col=None):
    d=d or LAST
    r=D[(D.g==g)&(D.d==d)]
    return r.iloc[0] if col is None else r.iloc[0][col]
def series(g,col,start='2023-01-31'):
    r=D[(D.g==g)&(D.d>=start)].set_index('d')[col]
    return r
