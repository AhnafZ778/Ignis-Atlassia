"""OpenCV display callouts on supplied figures, never pixel-derived measurements."""
import base64
import math

def annotate(image,target):
    import cv2
    import numpy as np
    regions=image.get('regions',[])
    region=next((r for r in regions if r.get('target')==target),None)
    if region is None:raise ValueError('This target is not registered in the attached figure.')
    raw=base64.b64decode(image['data'],validate=True)
    pixels=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
    if pixels is None:raise ValueError('The PNG could not be decoded.')
    h,w=pixels.shape[:2];rect=region.get('rect',[])
    if len(rect)!=4 or not all(type(v) in (float,int) and math.isfinite(v) for v in rect):raise ValueError('Invalid figure region.')
    x,y,rw,rh=rect
    if not (0<=x<w and 0<=y<h and rw>0 and rh>0 and x+rw<=w and y+rh<=h):raise ValueError('Callout exceeds the attached figure.')
    label=str(region.get('label',target)).encode('ascii','replace').decode()[:75]
    cv2.rectangle(pixels,(round(x),round(y)),(round(x+rw),round(y+rh)),(144,201,169),3,cv2.LINE_AA)
    text_size=cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,.48,1)[0]
    tx=max(4,min(round(x),w-text_size[0]-12));ty=max(24,round(y)-8)
    cv2.rectangle(pixels,(tx-3,ty-19),(tx+text_size[0]+7,ty+5),(27,42,33),-1)
    cv2.putText(pixels,label,(tx,ty),cv2.FONT_HERSHEY_SIMPLEX,.48,(224,243,235),1,cv2.LINE_AA)
    ok,png=cv2.imencode('.png',pixels)
    if not ok:raise ValueError('The annotated figure could not be encoded.')
    return {'data':base64.b64encode(png).decode(),'mime':'image/png','caption':image['caption']+' · OpenCV callout: '+label,
        'regions':regions,'target':target,'kind':'visual annotation; no image-derived fire measurements'}
