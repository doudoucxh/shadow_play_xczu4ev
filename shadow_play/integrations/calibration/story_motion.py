"""Fixed 67.105669-second rehearsal candidate, NOT calibrated Cartesian motion.

H anchors: AG attended trial. T anchors: AT/AU attended tiger trials.
New combined timing, idle blends, recoil and collapse are rehearsal candidates.
No runtime-supplied targets. Audience/Sony left and right are the stage convention.
"""
import bisect
import hashlib
import json
import math

DURATION = 2959360 / 44100
H = [
 [1537,1212,1537,1514,1508,1740],
 [1537,1392,1537,1514,1508,1740],
 [1717,1302,1537,1514,1508,1740],
 [1637,1282,1547,1519,1468,1640],
 # AG punch pitch raised by 20 us to remain inside the 10-degree inset.
 [1737,1212,1557,1524,1468,1640],
 [1637,1282,1547,1519,1568,1580],
 [1537,1372,1537,1514,1528,1660],
 [1457,1292,1537,1514,1508,1700]]
T = [[1730,1275,1730,1500],[1730,1275,1740,1600],
     [1620,1455,1740,1600],[1560,1455,1660,1470],
     [1510,1300,1600,1470],[1540,1300,1580,1540],
     [1640,1290,1660,1540],[1730,1275,1730,1500]]
BASE = H[0]+T[0]
HITS = [46.38,47.78,50.21,51.68,53.35,54.56,56.82,57.44]


def blend(a,b,u): return [round(x+(y-x)*u) for x,y in zip(a,b)]


def make_tracks():
    human=[];tiger=[]
    def h(t,p,label): human.append((t,list(p),label))
    def g(t,p,label): tiger.append((t,list(p),label))
    h(0,H[0],'待场');h(10,H[0],'入场准备');h(10.8,H[1],'举手亮相')
    h(12.8,H[2],'转向虎');h(14.5,H[3],'身前格挡');h(17,H[3],'对白')
    for t,p in [(17.7,4),(18.6,3),(19.5,5),(20.4,3),(21.2,4),(22,3)]:h(t,H[p],'对白手势')
    h(23,H[3],'行进戒备')
    for t in [24,26,28]:
        q=H[3][:];q[0]-=10;q[2]-=10;q[4]-=10
        h(t,q,'身体与两手同向');h(t+.7,H[3],'回稳')
    h(29,H[3],'护胸');dodge=H[3][:]
    for i in [0,2,4]:dodge[i]-=15
    dodge[3]-=5
    h(29.9,dodge,'随扑势让身');h(31.8,H[3],'回正盯虎');h(35,H[3],'对峙')
    for t,p in [(36.2,4),(36.8,3),(38.6,5),(39.3,3),(41.82,4),(42.5,3),(43.5,5),(44,3)]:h(t,H[p],'试探与格挡反击')
    h(45,H[3],'站姿压制准备')
    for i,t in enumerate(HITS):
        p=H[4 if i%2==0 else 5]
        h(t-.30,H[3],'蓄力格挡');h(t-.16,H[3],'开始出拳')
        h(t,p,'P%02d视觉击中候选'%(i+1));h(t+.06,p,'短停')
        h(t+.30,H[3],'收拳格挡')
    h(58,H[3],'结束重拳');h(59.5,H[6],'放低双手');h(61,H[6],'抓尾意象')
    for t,delta in [(62.4,-12),(63,-5),(64.3,-18),(65,-10),(66.2,-22)]:
        p=H[6][:]
        for i in [0,2,4]:p[i]+=delta
        h(t,p,'低手牵引与身体后让')
    h(66.5,human[-1][1],'终场');h(DURATION,human[-1][1],'保持末姿')
    g(0,T[0],'虎现');g(1,T[0],'巡视')
    for t,p in [(2,blend(T[0],T[2],.18)),(2.5,T[0]),(3.5,blend(T[0],T[1],.5)),
                (4,blend(T[0],T[2],.25)),(5,T[0]),(5.35,blend(T[0],T[2],.4)),
                (6,T[0]),(7.5,blend(T[0],T[1],.3)),(9,T[0]),(10,T[1]),(28,T[1]),(28.8,T[0])]:g(t,p,'巡视、威吓与低伏')
    for t,p in zip([29,29.48,29.99,30.34,30.68,31.06,31.56,31.90],T):g(t,p,'头先腾跃、后端跟随、下压扑咬')
    g(32,T[0],'对峙');g(33,T[1],'低伏');g(34,T[0],'蓄势');g(35,T[0],'试探')
    for t,p in [(36.2,blend(T[0],T[2],.4)),(36.8,T[0]),(38.6,blend(T[0],T[2],.65)),
                (39.4,T[0]),(41.82,blend(T[0],T[4],.35)),(42.4,T[0]),(43.5,blend(T[0],T[1],.4)),(44,T[0]),(45,T[0]),(45.8,T[6])]:g(t,p,'前探与后撤')
    for i,t in enumerate(HITS):
        rest=[1640,1290,1660,1540+5*i];scale=1-.07*i
        head=rest[:];head[0]+=round(45*scale);head[1]+=round(50*scale)
        rear=head[:];rear[2]+=round(30*scale);rear[3]-=round(20*scale)
        g(t-.30,rest,'受击前位');g(t+.06,head,'头先受击');g(t+.14,rear,'后端迟随');g(t+.24,rest,'衰弱收势')
    g(58,[1640,1290,1660,1580],'最后收势')
    g(58.36,[1580,1275,1640,1580],'头部先沉')
    fall=[1580,1275,1620,1640]
    g(59.2,fall,'后端降低');g(61,fall,'倒伏')
    for t,delta in [(62.4,-25),(63,-25),(64.3,-50),(65,-50),(66.2,-70)]:
        p=fall[:];p[0]+=delta;p[2]+=delta;g(t,p,'低位拖虎意象')
    g(66.5,tiger[-1][1],'终场');g(DURATION,tiger[-1][1],'保持末姿')
    for track in [human,tiger]:
        assert all(a[0]<b[0] for a,b in zip(track,track[1:])), 'Overlapping phase times'
    return human,tiger


HUMAN,TIGER=make_tracks()


def sample_track(track,t):
    if t<=track[0][0]:return track[0][1][:]
    if t>=track[-1][0]:return track[-1][1][:]
    i=bisect.bisect_right([x[0] for x in track],t)-1
    a,b=track[i:i+2];u=(t-a[0])/(b[0]-a[0]);u=.5-.5*math.cos(math.pi*u)
    return blend(a[1],b[1],u)


def sample(t):return sample_track(HUMAN,t)+sample_track(TIGER,t)


def route_digest():
    return hashlib.sha256(json.dumps([HUMAN,TIGER],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def check_envelope():
    # Bare-gimbal limits with 10-degree inset; NOT proof of loaded clearance.
    lo=[10,95,10,50,70,50,50,100,70,50]
    hi=[260,260,260,170,260,170,190,190,200,170]
    rows=[sample(i*.02) for i in range(math.ceil(DURATION/.02)+1)]
    for q in rows:
        for v,a,b in zip(q,lo,hi):
            if not 500+a*2000/270<=v<=500+b*2000/270:raise ValueError('Outside inset command envelope')
    peak=max(abs(a-b) for x,y in zip(rows,rows[1:]) for a,b in zip(x,y))
    if peak>22:raise ValueError('Offline sampled step exceeds 22 us')
    return dict(duration_s=DURATION,samples=len(rows),peak_20ms_step_us=peak,
                route_sha256=route_digest(),loaded_clearance_proven=False)


if __name__=='__main__':print(json.dumps(check_envelope()))
