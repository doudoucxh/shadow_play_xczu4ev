"""Fixed-position full rehearsal; new combinations remain visual candidates.
No BE crossing/downstroke, rail motion, or runtime-supplied poses.
"""
import bisect
import hashlib
import json
import math
DURATION=2959360/44100
BASE=[1515,1372,1515,1514,1506,1660,1510,1275,1550,1640]
REST=BASE[:6]
LOW=[1515,1252,1515,1594,1506,1720]
UP=[1515,1372,1515,1554,1506,1500]
DROP=[1515,1212,1535,1594,1546,1660]
GUARD=[1575,1272,1535,1574,1486,1650]
COUNTER=[1515,1252,1535,1574,1586,1580]
H=[REST,UP,DROP,GUARD,COUNTER]
T=[[1510,1275,1550,1640],[1510,1455,1550,1640],
   [1510,1535,1550,1600],[1510,1615,1550,1520],[1510,1695,1550,1440]]
HITS=[46.38,47.78,50.21,51.68,53.35,54.56,56.82,57.44]
def blend(a,b,u):return [round(x+(y-x)*u) for x,y in zip(a,b)]

def make_tracks():
    human=[];tiger=[]
    def h(t,p,label):human.append((t,list(p),label))
    def g(t,p,label):tiger.append((t,list(p),label))
    h(0,REST,'待场');h(10,REST,'亮相准备');h(10.8,UP,'双手举起亮相')
    h(12,LOW,'沉身');h(13,GUARD,'护身');h(14,UP,'举手示意');h(15,DROP,'双手落下');h(17,GUARD,'对白')
    for t,p in [(18,COUNTER),(18.8,GUARD),(20,LOW),(21,UP),(22,GUARD)]:h(t,p,'对白手势与身体配合')
    h(23,GUARD,'原地戒备，走位待丝杆')
    for t,p in [(24,LOW),(25,REST),(26,LOW),(27,REST),(28,GUARD)]:h(t,p,'身体起伏')
    h(29,GUARD,'迎虎');h(29.7,UP,'双手上格挡');h(30.4,LOW,'沉身避扑');h(31.2,COUNTER,'反击');h(32,GUARD,'收护')
    h(35,GUARD,'对峙')
    for t,p,label in [(36.2,UP,'双举'),(36.7,DROP,'双砸'),(37.2,GUARD,'收护'),(38.6,COUNTER,'出拳'),
                       (39.2,GUARD,'收拳'),(40.7,LOW,'沉身'),(41.5,UP,'挺身双举'),(42,DROP,'双砸'),
                       (42.6,GUARD,'格挡'),(43.5,COUNTER,'反击'),(44,GUARD,'收护'),(45,GUARD,'连击准备')]:h(t,p,label)
    for i,t in enumerate(HITS):
        prep,hit=(UP,DROP) if i in [0,2,4,6] else (GUARD,COUNTER)
        h(t-.25,prep,'双砸蓄势' if prep==UP else '身前格挡')
        h(t,hit,'P%02d连击候选'%(i+1));h(t+.08,hit,'短停');h(t+.25,GUARD,'收护')
    for t,p,label in [(58,GUARD,'结束连击'),(59.2,LOW,'沉身收势'),(60.2,GUARD,'喘息'),(61,LOW,'低手抓尾意象'),
                       (62.4,GUARD,'原地拉拽'),(63,LOW,'放松'),(64.3,GUARD,'再次拉拽'),(65,LOW,'收势'),
                       (66.5,REST,'终场'),(DURATION,REST,'保持')]:h(t,p,label)
    for t,p in [(0,T[0]),(1,T[0]),(2,blend(T[0],T[1],.4)),(2.8,T[0]),(3.5,blend(T[0],T[1],.2))]:g(t,p,'巡视')
    for t,i in [(0,0),(.15,0),(.47,1),(.65,2),(.83,3),(1.01,4),(1.14,4),(1.32,3),(1.50,2),(1.68,1),(2.14,0),(3,0)]:g(4+t,T[i],'离幕影子咆哮')
    g(9,T[0],'潜伏');g(10,T[0],'等待武松');g(28,T[0],'低伏蓄势')
    for t,i in [(29,0),(29.32,1),(29.52,2),(29.72,3),(29.92,4),(30.05,4)]:g(t,T[i],'头先抬、后端迟随')
    g(30.7,[1510,1275,1550,1440],'头先下压扑咬');g(31.1,T[0],'后端落下');g(32,T[0],'回稳')
    for t,p in [(33,T[1]),(34,T[0]),(35,T[0]),(36.2,T[2]),(36.8,T[0]),(38.6,T[2]),(39.4,T[0]),
                 (41.82,T[1]),(42.5,T[0]),(43.5,T[1]),(44,T[0]),(45,T[0])]:g(t,p,'前探威吓')
    for i,t in enumerate(HITS):
        scale=1-.07*i;head=[1510,1275+round(140*scale),1550,1640]
        rear=head[:];rear[3]-=round(60*scale)
        g(t-.20,T[0],'受击前位');g(t+.06,head,'头先受击');g(t+.2,rear,'后端迟随');g(t+.4,T[0],'衰弱低伏')
    for t,p,label in [(58,T[0],'衰弱'),(59.2,T[0],'低位倒伏意象待验证'),(61,T[0],'收伏'),
                       (62.4,blend(T[0],T[1],.15),'随拖拽微动'),(63,T[0],'落定'),
                       (64.3,blend(T[0],T[1],.1),'再次随动'),(65,T[0],'终场'),(DURATION,T[0],'保持')]:g(t,p,label)
    for track in [human,tiger]:assert all(a[0]<b[0] for a,b in zip(track,track[1:])), 'Overlapping times'
    return human,tiger
HUMAN,TIGER=make_tracks()

def sample_track(track,t):
    if t<=track[0][0]:return track[0][1][:]
    if t>=track[-1][0]:return track[-1][1][:]
    i=bisect.bisect_right([x[0] for x in track],t)-1
    a,b=track[i:i+2];u=(t-a[0])/(b[0]-a[0]);u=.5-.5*math.cos(math.pi*u)
    return blend(a[1],b[1],u)
def sample(t):return sample_track(HUMAN,t)+sample_track(TIGER,t)
def route_digest():return hashlib.sha256(json.dumps([HUMAN,TIGER],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def check_envelope():
    lo=[10,95,10,50,70,50,50,100,70,50];hi=[260,260,260,170,260,170,190,190,200,170]
    rows=[sample(i*.02) for i in range(math.ceil(DURATION/.02)+1)]
    for q in rows:
        for v,a,b in zip(q,lo,hi):
            if not 500+a*2000/270<=v<=500+b*2000/270:raise ValueError('Outside inset command envelope')
    peak=max(abs(a-b) for x,y in zip(rows,rows[1:]) for a,b in zip(x,y))
    if peak>22:raise ValueError('Offline sampled step exceeds 22 us: '+str(peak))
    return dict(duration_s=DURATION,samples=len(rows),peak_20ms_step_us=peak,route_sha256=route_digest(),loaded_clearance_proven=False)
if __name__=='__main__':print(json.dumps(check_envelope()))
