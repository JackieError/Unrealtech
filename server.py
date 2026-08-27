#!/usr/bin/env python3
"""Local OAuth/API server. Channel data stays on this machine."""
import json, os, re, secrets, time, urllib.parse, urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
ROOT=Path(__file__).parent; PORT=int(os.getenv('PORT','4174'))
CLIENT_ID=os.getenv('YOUTUBE_CLIENT_ID',''); CLIENT_SECRET=os.getenv('YOUTUBE_CLIENT_SECRET','')
for credential_file in (ROOT/'client_secret.json', ROOT/'credentials.json'):
    if credential_file.exists() and not CLIENT_ID:
        saved=json.loads(credential_file.read_text()); saved=saved.get('web',saved.get('installed',{}))
        CLIENT_ID=saved.get('client_id',''); CLIENT_SECRET=saved.get('client_secret','')
        break
REDIRECT=os.getenv('YOUTUBE_REDIRECT_URI',f'http://localhost:{PORT}/api/auth/callback')
SCOPES='https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly'
TOKEN_FILE=ROOT/'token.json'
try: saved_token=json.loads(TOKEN_FILE.read_text()) if TOKEN_FILE.exists() else None
except Exception: saved_token=None
session={'state':None,'token':saved_token};market_cache={};playlist_cache={'expires':0,'types':{}}
def save_token(value):
    TOKEN_FILE.write_text(json.dumps(value));os.chmod(TOKEN_FILE,0o600);session['token']=value
def request(url,access=None,data=None,json_data=None):
    headers={'Accept':'application/json'}
    if access:headers['Authorization']='Bearer '+access
    body=urllib.parse.urlencode(data).encode() if data else None
    if json_data is not None:body=json.dumps(json_data).encode();headers['Content-Type']='application/json'
    req=urllib.request.Request(url,data=body,headers=headers)
    with urllib.request.urlopen(req,timeout=30) as r:return json.loads(r.read())
def access_token():
    t=session.get('token') or {}
    if not t:return None
    if t.get('expires_at',0)>time.time()+60:return t.get('access_token')
    if not t.get('refresh_token'):return None
    n=request('https://oauth2.googleapis.com/token',data={'client_id':CLIENT_ID,'client_secret':CLIENT_SECRET,'refresh_token':t['refresh_token'],'grant_type':'refresh_token'})
    t.update(n);t['expires_at']=time.time()+n.get('expires_in',3600);save_token(t);return t.get('access_token')
def analytics(access,start,end):
    metrics='views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,likes,comments'
    q=urllib.parse.urlencode({'ids':'channel==MINE','startDate':start,'endDate':end,'metrics':metrics,'dimensions':'video','sort':'-views','maxResults':200})
    raw=request('https://youtubeanalytics.googleapis.com/v2/reports?'+q,access);heads=[h['name'] for h in raw.get('columnHeaders',[])]
    return {r[0]:dict(zip(heads,r)) for r in raw.get('rows',[])}
def analytics_report(access,start,end,dimensions,metrics,sort=None,max_results=200):
    params={'ids':'channel==MINE','startDate':start,'endDate':end,'metrics':metrics,'dimensions':dimensions,'maxResults':max_results}
    if sort:params['sort']=sort
    raw=request('https://youtubeanalytics.googleapis.com/v2/reports?'+urllib.parse.urlencode(params),access)
    heads=[h['name'] for h in raw.get('columnHeaders',[])]
    return [dict(zip(heads,row)) for row in raw.get('rows',[])]
def reporting_setup(access):
    existing=request('https://youtubereporting.googleapis.com/v1/jobs?pageSize=100',access).get('jobs',[])
    wanted={'channel_reach_basic_a1':'안될공학 reach 일별','channel_traffic_source_a3':'안될공학 traffic 일별','channel_device_os_a3':'안될공학 device 일별'}
    made=[]
    for report_type,name in wanted.items():
        if not any(j.get('reportTypeId')==report_type for j in existing):
            made.append(request('https://youtubereporting.googleapis.com/v1/jobs',access,json_data={'reportTypeId':report_type,'name':name}))
    return existing+made
def market_signal(access,topic):
    queries={'AI·컴퓨팅':'AI 엔비디아 인공지능','반도체·메모리':'반도체 HBM 메모리','우주·모빌리티':'SpaceX 우주 모빌리티','빅테크 전략':'애플 구글 메타','산업·에너지':'전력 에너지 산업','기술 인사이트':'기술 산업 전망'}
    query=queries.get(topic,topic)[:60]
    if topic in market_cache and market_cache[topic]['expires']>time.time():return market_cache[topic]['data']
    after=time.strftime('%Y-%m-%dT00:00:00Z',time.gmtime(time.time()-30*86400))
    params={'part':'snippet','q':query,'type':'video','regionCode':'KR','relevanceLanguage':'ko','publishedAfter':after,'order':'viewCount','maxResults':10}
    found=request('https://www.googleapis.com/youtube/v3/search?'+urllib.parse.urlencode(params),access)
    ids=[x.get('id',{}).get('videoId') for x in found.get('items',[]) if x.get('id',{}).get('videoId')];videos=[]
    if ids:
        raw=request('https://www.googleapis.com/youtube/v3/videos?'+urllib.parse.urlencode({'part':'snippet,statistics','id':','.join(ids)}),access)
        for v in raw.get('items',[]):videos.append({'title':v.get('snippet',{}).get('title',''),'channel':v.get('snippet',{}).get('channelTitle',''),'views':int(v.get('statistics',{}).get('viewCount',0))})
    ordered=sorted(videos,key=lambda x:x['views'],reverse=True);values=sorted(x['views'] for x in videos)
    result={'topic':topic,'query':query,'supply':found.get('pageInfo',{}).get('totalResults',0),'competitorMedian':values[len(values)//2] if values else 0,'leaders':ordered[:3]}
    market_cache[topic]={'expires':time.time()+21600,'data':result};return result
def playlist_types(access):
    if playlist_cache['expires']>time.time():return playlist_cache['types']
    raw=request('https://www.googleapis.com/youtube/v3/playlists?'+urllib.parse.urlencode({'part':'snippet','mine':'true','maxResults':50}),access);mapping={}
    for p in raw.get('items',[]):
        name=p.get('snippet',{}).get('title','');kind='오리지널' if '오리지널' in name else ('칼럼' if '칼럼' in name else None)
        if not kind:continue
        page=''
        while True:
            params={'part':'contentDetails','playlistId':p['id'],'maxResults':50}
            if page:params['pageToken']=page
            rows=request('https://www.googleapis.com/youtube/v3/playlistItems?'+urllib.parse.urlencode(params),access)
            for x in rows.get('items',[]):mapping[x.get('contentDetails',{}).get('videoId')]=kind
            page=rows.get('nextPageToken','')
            if not page:break
    playlist_cache.update({'expires':time.time()+21600,'types':mapping});return mapping
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def send_json(self,obj,status=200):
        body=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def redirect(self,url):self.send_response(302);self.send_header('Location',url);self.end_headers()
    def do_GET(self):
        path=urllib.parse.urlparse(self.path)
        try:
            if path.path=='/api/auth/status':return self.send_json({'configured':bool(CLIENT_ID and CLIENT_SECRET),'connected':bool(access_token())})
            if path.path=='/api/auth/start':
                if not CLIENT_ID:return self.send_json({'error':'OAuth client가 설정되지 않았습니다.'},503)
                session['state']=secrets.token_urlsafe(24);q=urllib.parse.urlencode({'client_id':CLIENT_ID,'redirect_uri':REDIRECT,'response_type':'code','scope':SCOPES,'access_type':'offline','prompt':'consent','state':session['state']})
                return self.redirect('https://accounts.google.com/o/oauth2/v2/auth?'+q)
            if path.path=='/api/auth/callback':
                q=urllib.parse.parse_qs(path.query)
                if q.get('state',[''])[0]!=session.get('state'):return self.send_json({'error':'OAuth state가 일치하지 않습니다.'},400)
                t=request('https://oauth2.googleapis.com/token',data={'code':q.get('code',[''])[0],'client_id':CLIENT_ID,'client_secret':CLIENT_SECRET,'redirect_uri':REDIRECT,'grant_type':'authorization_code'})
                t['expires_at']=time.time()+t.get('expires_in',3600);save_token(t);return self.redirect('/?connected=1')
            if path.path=='/api/youtube/data':
                access=access_token()
                if not access:return self.send_json({'error':'YouTube 계정 연결이 필요합니다.'},401)
                end=time.strftime('%Y-%m-%d');start=time.strftime('%Y-%m-%d',time.localtime(time.time()-90*86400));stats=analytics(access,start,end);ids=list(stats);items=[]
                try:playlist_map=playlist_types(access)
                except Exception:playlist_map={}
                for i in range(0,len(ids),50):
                    q=urllib.parse.urlencode({'part':'snippet,contentDetails,statistics','id':','.join(ids[i:i+50])})
                    for v in request('https://www.googleapis.com/youtube/v3/videos?'+q,access).get('items',[]):
                        a=stats[v['id']];s=v.get('statistics',{});sn=v.get('snippet',{})
                        title=sn.get('title','');description=sn.get('description','');format_text=title+' '+description[:500];duration=v.get('contentDetails',{}).get('duration','');parts=re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',duration);seconds=(int(parts.group(1) or 0)*3600+int(parts.group(2) or 0)*60+int(parts.group(3) or 0)) if parts else 0
                        content_type=playlist_map.get(v['id']) or ('오리지널' if '오리지널' in format_text else ('칼럼' if '칼럼' in format_text else ('쇼츠' if '#short' in format_text.lower() or (0<seconds<=180) else ('라이브' if '라이브' in format_text or 'live' in title.lower() else '일반 영상'))))
                        items.append({'id':v['id'],'title':title,'type':content_type,'date':sn.get('publishedAt','')[:10],'thumbnail':sn.get('thumbnails',{}).get('medium',{}).get('url',''),'duration':duration,'durationSeconds':seconds,'views':int(a.get('views',0)),'impressions':None,'ctr':None,'retention':float(a.get('averageViewPercentage',0)),'avgDuration':float(a.get('averageViewDuration',0)),'watchMinutes':float(a.get('estimatedMinutesWatched',0)),'subs':int(a.get('subscribersGained',0))-int(a.get('subscribersLost',0)),'likes':int(a.get('likes',s.get('likeCount',0))),'comments':int(a.get('comments',s.get('commentCount',0)))})
                extras={}
                for key,dim in [('traffic','insightTrafficSourceType'),('devices','deviceType'),('countries','country'),('subscribers','subscribedStatus')]:
                    try:extras[key]=analytics_report(access,start,end,dim,'views,estimatedMinutesWatched','-views',25)
                    except Exception:extras[key]=[]
                return self.send_json({'items':items,'breakdowns':extras,'period':{'start':start,'end':end}})
            if path.path=='/api/reporting/setup':
                access=access_token()
                if not access:return self.send_json({'error':'YouTube 계정 연결이 필요합니다.'},401)
                jobs=reporting_setup(access)
                return self.send_json({'jobs':[{'id':j.get('id'),'name':j.get('name'),'reportTypeId':j.get('reportTypeId'),'createTime':j.get('createTime')} for j in jobs]})
            if path.path=='/api/market/signals':
                access=access_token()
                if not access:return self.send_json({'error':'YouTube 계정 연결이 필요합니다.'},401)
                topics=urllib.parse.parse_qs(path.query).get('topic',[])[:6]
                return self.send_json({'signals':[market_signal(access,x) for x in topics]})
            return super().do_GET()
        except urllib.error.HTTPError as e:
            try:detail=json.loads(e.read()).get('error',{}).get('message',str(e))
            except Exception:detail=str(e)
            return self.send_json({'error':detail},e.code)
        except Exception as e:return self.send_json({'error':str(e)},500)
if __name__=='__main__':
    print(f'안될공학 Content Lab: http://localhost:{PORT}')
    if not CLIENT_ID:print('API 연결: YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET 미설정')
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
