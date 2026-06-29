from flask import Flask, render_template, jsonify, request
import cv2, numpy as np, base64, math, threading, uuid, os, json
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Proctor global state
# ─────────────────────────────────────────────────────────────────────────────
violation_log = []
stats = {
    "session_start":"","total_frames":0,"no_face_count":0,
    "multiple_face_count":0,"tab_switch_count":0,"phone_count":0,
    "copy_paste_count":0,"audio_alert_count":0,"violation_score":0,
    "status":"idle","last_face_count":0,"phone_detected":False,
    "alert_active":False,"alert_message":"","yolo_available":False,
    "audio_volume":0.0,"audio_voices":0,"audio_suspicious":False,
    # Face recognition
    "face_recognition_available":False,
    "face_verified":False,
    "face_match_count":0,
    "face_mismatch_count":0,
    "identity_score":100,
    # Screen recording
    "screen_record_count":0,
}
log_lock = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
# Face Recognition setup
# ─────────────────────────────────────────────────────────────────────────────
face_rec_available = False
registered_encoding = None   # numpy array of registered face encoding

def load_face_recognition():
    global face_rec_available
    try:
        import face_recognition as fr
        face_rec_available = True
        stats["face_recognition_available"] = True
        print("✅ face_recognition loaded — ID verification ACTIVE")
    except Exception as e:
        print(f"⚠️  face_recognition not available: {e}. Install: pip install face-recognition")

threading.Thread(target=load_face_recognition, daemon=True).start()

def encode_face_from_image(img_array):
    """Extract face encoding from numpy BGR image. Returns encoding or None."""
    try:
        import face_recognition as fr
        rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        locs = fr.face_locations(rgb, model="hog")
        if not locs:
            return None
        encs = fr.face_encodings(rgb, locs)
        return encs[0] if encs else None
    except Exception as e:
        print(f"Face encoding error: {e}")
        return None

def verify_face(live_frame, registered_enc, tolerance=0.55):
    """
    Compare live frame face against registered encoding.
    Returns dict: {match, distance, confidence, face_found}
    """
    try:
        import face_recognition as fr
        rgb = cv2.cvtColor(live_frame, cv2.COLOR_BGR2RGB)
        locs = fr.face_locations(rgb, model="hog")
        if not locs:
            return {"match": False, "distance": 1.0, "confidence": 0, "face_found": False}
        encs = fr.face_encodings(rgb, locs)
        if not encs:
            return {"match": False, "distance": 1.0, "confidence": 0, "face_found": False}
        dist = float(fr.face_distance([registered_enc], encs[0])[0])
        match = dist < tolerance
        confidence = max(0, int((1 - dist) * 100))
        return {"match": match, "distance": round(dist, 3), "confidence": confidence, "face_found": True}
    except Exception as e:
        return {"match": False, "distance": 1.0, "confidence": 0, "face_found": False, "error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# Quiz data & sessions
# ─────────────────────────────────────────────────────────────────────────────
QUIZ_BANK = {
    "python":{
        "title":"Python Programming","icon":"🐍","duration":20,
        "questions":[
            {"id":1,"q":"What is the output of print(type([]))?","options":["<class 'list'>","<class 'array'>","<class 'tuple'>","<class 'dict'>"],"ans":0},
            {"id":2,"q":"Which keyword defines a function in Python?","options":["function","def","fun","define"],"ans":1},
            {"id":3,"q":"What does len('Hello') return?","options":["4","5","6","Error"],"ans":1},
            {"id":4,"q":"How do you create a dictionary?","options":["d = []","d = ()","d = {}","d = <>"],"ans":2},
            {"id":5,"q":"Which is a mutable data type?","options":["tuple","string","list","int"],"ans":2},
            {"id":6,"q":"What does 'pass' do in Python?","options":["Exits program","Does nothing (placeholder)","Skips iteration","Returns None"],"ans":1},
            {"id":7,"q":"How do you open a file for reading?","options":["open('f','w')","open('f','r')","open('f','a')","read('f')"],"ans":1},
            {"id":8,"q":"Which method adds an element to a list?","options":["add()","insert_end()","append()","push()"],"ans":2},
            {"id":9,"q":"What does the // operator do?","options":["Division","Floor division","Modulo","Power"],"ans":1},
            {"id":10,"q":"What is the output of bool('')?","options":["True","False","None","Error"],"ans":1},
        ]
    },
    "webdev":{
        "title":"Web Development","icon":"🌐","duration":20,
        "questions":[
            {"id":1,"q":"What does HTML stand for?","options":["Hyper Text Markup Language","High Tech Modern Language","Hyper Transfer Markup Language","Home Tool Markup Language"],"ans":0},
            {"id":2,"q":"Which CSS property controls text size?","options":["text-size","font-size","text-style","font-style"],"ans":1},
            {"id":3,"q":"What does DOM stand for?","options":["Document Object Model","Data Object Module","Document Oriented Method","Data Object Model"],"ans":0},
            {"id":4,"q":"Which HTTP method sends data to a server?","options":["GET","DELETE","POST","HEAD"],"ans":2},
            {"id":5,"q":"Which HTML tag creates a hyperlink?","options":["<link>","<a>","<href>","<url>"],"ans":1},
            {"id":6,"q":"Correct arrow function syntax in JS?","options":["function() =>","=> function()","() => {}","func => ()"],"ans":2},
            {"id":7,"q":"What does CSS stand for?","options":["Computer Style Sheets","Creative Style Syntax","Cascading Style Sheets","Colorful Style Sheets"],"ans":2},
            {"id":8,"q":"JS method to select element by ID?","options":["querySelector","getElementById","selectById","findElement"],"ans":1},
            {"id":9,"q":"Default display value of a div?","options":["inline","block","inline-block","flex"],"ans":1},
            {"id":10,"q":"HTTP status code for Not Found?","options":["200","301","404","500"],"ans":2},
        ]
    },
    "ai":{
        "title":"Artificial Intelligence","icon":"🤖","duration":25,
        "questions":[
            {"id":1,"q":"What does AI stand for?","options":["Automated Intelligence","Artificial Intelligence","Augmented Interface","Automated Interface"],"ans":1},
            {"id":2,"q":"Which algorithm is used for classification?","options":["K-Means","Linear Regression","Decision Tree","PCA"],"ans":2},
            {"id":3,"q":"What is overfitting?","options":["Model performs well on test data","Model memorises training data but fails on new data","Model underfits training data","Too few parameters"],"ans":1},
            {"id":4,"q":"Neural networks are inspired by?","options":["Computer circuits","Human brain neurons","Database structures","Math equations"],"ans":1},
            {"id":5,"q":"CNN stands for?","options":["Computer Neural Network","Convolutional Neural Network","Connected Node Network","Coded Neural Network"],"ans":1},
            {"id":6,"q":"Common Python library for ML?","options":["Django","Flask","scikit-learn","NumPy only"],"ans":2},
            {"id":7,"q":"Purpose of a training dataset?","options":["Test the model","Teach the model patterns","Validate the model","Deploy the model"],"ans":1},
            {"id":8,"q":"NLP stands for?","options":["Neural Learning Process","Natural Language Processing","Network Logic Programming","None of these"],"ans":1},
            {"id":9,"q":"Activation function outputting values 0-1?","options":["ReLU","Tanh","Sigmoid","Softmax"],"ans":2},
            {"id":10,"q":"Purpose of backpropagation?","options":["Forward pass prediction","Update weights to minimise loss","Load training data","Normalise inputs"],"ans":1},
        ]
    },
    "dbms":{
        "title":"Database Management","icon":"🗄️","duration":20,
        "questions":[
            {"id":1,"q":"SQL stands for?","options":["Structured Query Language","Simple Query Logic","Structured Question Language","System Query Language"],"ans":0},
            {"id":2,"q":"SQL command to retrieve data?","options":["INSERT","UPDATE","SELECT","DELETE"],"ans":2},
            {"id":3,"q":"What is a primary key?","options":["Foreign reference","Unique identifier for a row","Duplicate column","Index column"],"ans":1},
            {"id":4,"q":"JOIN returning all rows from both tables?","options":["INNER JOIN","LEFT JOIN","RIGHT JOIN","FULL OUTER JOIN"],"ans":3},
            {"id":5,"q":"ACID stands for?","options":["Atomicity Consistency Isolation Durability","Atomic Consistent Integrated Durable","All Commands in Database","Automated Consistent Input Data"],"ans":0},
            {"id":6,"q":"SQL clause to filter records?","options":["ORDER BY","GROUP BY","WHERE","HAVING"],"ans":2},
            {"id":7,"q":"Normalisation in databases means?","options":["Backing up data","Organising data to reduce redundancy","Encrypting tables","Adding indexes"],"ans":1},
            {"id":8,"q":"NoSQL database using documents?","options":["Redis","MongoDB","Cassandra","Neo4j"],"ans":1},
            {"id":9,"q":"DDL stands for?","options":["Data Definition Language","Data Deletion Logic","Dynamic Data Language","Database Deploy Logic"],"ans":0},
            {"id":10,"q":"Command that removes a table completely?","options":["DELETE","TRUNCATE","DROP","REMOVE"],"ans":2},
        ]
    }
}

quiz_sessions = {}
quiz_results  = []

# ─────────────────────────────────────────────────────────────────────────────
# Face detection (Haar)
# ─────────────────────────────────────────────────────────────────────────────
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

# ─────────────────────────────────────────────────────────────────────────────
# YOLOv8 phone detection
# ─────────────────────────────────────────────────────────────────────────────
yolo_model = None
PHONE_CLASS_ID = 67
PHONE_CONF     = 0.40

def load_yolo():
    global yolo_model
    try:
        from ultralytics import YOLO
        yolo_model = YOLO("yolov8n.pt")
        yolo_model(np.zeros((480,640,3),dtype=np.uint8), verbose=False)
        stats["yolo_available"] = True
        print("✅ YOLOv8 ready")
    except Exception as e:
        print(f"⚠️  YOLOv8 unavailable: {e}")

threading.Thread(target=load_yolo, daemon=True).start()

def detect_phone(frame):
    if yolo_model:
        results = yolo_model(frame, verbose=False, conf=PHONE_CONF, classes=[PHONE_CLASS_ID])
        phones = []
        for r in results:
            for b in r.boxes:
                if int(b.cls[0])==PHONE_CLASS_ID:
                    x1,y1,x2,y2 = map(int,b.xyxy[0])
                    phones.append((x1,y1,x2-x1,y2-y1,float(b.conf[0])))
        return phones
    h,w = frame.shape[:2]; fa=h*w
    gray = cv2.GaussianBlur(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(5,5),0)
    edges = cv2.dilate(cv2.Canny(gray,25,90),np.ones((3,3),np.uint8))
    cnts,_ = cv2.findContours(edges,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    phones=[]
    for c in cnts:
        area=cv2.contourArea(c)
        if not(fa*.008<area<fa*.28): continue
        x,y,cw,ch=cv2.boundingRect(c); asp=cw/ch if ch else 0
        if not(.35<=asp<=.75 or 1.3<=asp<=2.7): continue
        if cw*ch==0 or area/(cw*ch)<.5: continue
        if np.mean(gray[y:y+ch,x:x+cw])<55: continue
        phones.append((x,y,cw,ch,.5))
    return _nms(phones)

def _nms(boxes,thr=.35):
    if not boxes: return []
    boxes=sorted(boxes,key=lambda b:b[2]*b[3],reverse=True)
    keep=[]
    while boxes:
        c=boxes.pop(0); keep.append(c)
        boxes=[b for b in boxes if _iou(c,b)<thr]
    return keep

def _iou(a,b):
    ax,ay,aw,ah=a[:4]; bx,by,bw,bh=b[:4]
    ix=max(ax,bx); iy=max(ay,by)
    ix2=min(ax+aw,bx+bw); iy2=min(ay+ah,by+bh)
    inter=max(0,ix2-ix)*max(0,iy2-iy)
    u=aw*ah+bw*bh-inter
    return inter/u if u else 0

# ─────────────────────────────────────────────────────────────────────────────
# Audio analysis
# ─────────────────────────────────────────────────────────────────────────────
def analyze_audio(pcm_data, sample_rate=16000):
    if not pcm_data:
        return {"volume_db":-100,"is_silent":True,"is_loud":False,"suspected_voices":0,"suspicious":False}
    s=np.array(pcm_data,dtype=np.float32)
    rms=float(np.sqrt(np.mean(s**2)))
    db=20*math.log10(rms+1e-9)
    is_silent=db<-45; is_loud=db>-10
    voices=0
    if not is_silent and len(s)>=256:
        win=s[:min(len(s),4096)]*np.hanning(min(len(s),4096))
        mag=np.abs(np.fft.rfft(win))
        freqs=np.fft.rfftfreq(len(win),d=1.0/sample_rate)
        vm=mag[(freqs>=80)&(freqs<=3400)]
        if len(vm)>10:
            thr=np.mean(vm)*1.5
            peaks=sum(1 for i in range(1,len(vm)-1) if vm[i]>thr and vm[i]>vm[i-1] and vm[i]>vm[i+1])
            voices=1 if peaks<=3 else 2 if peaks<=8 else 3
    return {"volume_db":round(db,1),"is_silent":is_silent,"is_loud":is_loud,
            "suspected_voices":voices,"suspicious":voices>=2 or is_loud}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def add_violation(vtype, message, severity="warning"):
    with log_lock:
        violation_log.append({"id":len(violation_log)+1,
            "timestamp":datetime.now().strftime("%H:%M:%S"),
            "type":vtype,"message":message,"severity":severity})
        stats["violation_score"] += {"critical":10,"warning":5}.get(severity,2)
        stats["alert_active"]=True; stats["alert_message"]=message

def reset_proctor_state():
    global violation_log, registered_encoding
    registered_encoding = None
    with log_lock:
        violation_log=[]
        stats.update({"session_start":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_frames":0,"no_face_count":0,"multiple_face_count":0,
            "tab_switch_count":0,"phone_count":0,"copy_paste_count":0,
            "audio_alert_count":0,"violation_score":0,"status":"monitoring",
            "last_face_count":0,"phone_detected":False,"alert_active":False,
            "alert_message":"","audio_volume":0.0,"audio_voices":0,"audio_suspicious":False,
            "face_verified":False,"face_match_count":0,"face_mismatch_count":0,
            "identity_score":100,"screen_record_count":0})

def analyze_frame(frame_b64):
    try:
        _,enc=frame_b64.split(",",1)
        frame=cv2.imdecode(np.frombuffer(base64.b64decode(enc),np.uint8),cv2.IMREAD_COLOR)
        if frame is None: return {"error":"decode failed"}
        gray=cv2.equalizeHist(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY))
        faces=face_cascade.detectMultiScale(gray,1.1,5,minSize=(60,60),flags=cv2.CASCADE_SCALE_IMAGE)
        fc=len(faces)
        phones=detect_phone(frame); pd=len(phones)>0
        stats["total_frames"]+=1; stats["last_face_count"]=fc; stats["phone_detected"]=pd

        # ── Face Recognition / ID Verification ──────────────────────────────
        face_verify_result = None
        if registered_encoding is not None and face_rec_available and fc >= 1:
            face_verify_result = verify_face(frame, registered_encoding)
            if face_verify_result["face_found"]:
                if face_verify_result["match"]:
                    stats["face_match_count"] += 1
                    stats["face_verified"] = True
                else:
                    stats["face_mismatch_count"] += 1
                    stats["identity_score"] = max(0, stats["identity_score"] - 3)
                    if stats["face_mismatch_count"] % 4 == 1:
                        add_violation("IDENTITY_MISMATCH",
                            f"Face does not match registered ID (confidence {face_verify_result['confidence']}%)",
                            "critical")

        alert=None; sev="info"
        if pd:
            stats["phone_count"]+=1
            if stats["phone_count"]%4==1:
                add_violation("PHONE_DETECTED",f"Phone detected ({'YOLOv8' if stats['yolo_available'] else 'CV'}, conf={max(p[4] for p in phones):.0%})","critical")
            alert="📱 Mobile phone detected!"; sev="critical"
        elif fc==0:
            stats["no_face_count"]+=1
            if stats["no_face_count"]%10==1: add_violation("NO_FACE","Candidate not visible","critical")
            alert="⚠️ No face detected!"; sev="critical"
        elif fc>1:
            stats["multiple_face_count"]+=1
            if stats["multiple_face_count"]%5==1: add_violation("MULTIPLE_FACES",f"{fc} faces in frame","critical")
            alert=f"🚨 {fc} faces detected!"; sev="critical"
        elif face_verify_result and not face_verify_result["match"] and face_verify_result["face_found"]:
            alert=f"🔴 Identity mismatch! Confidence: {face_verify_result['confidence']}%"; sev="critical"
        else:
            stats["alert_active"]=False; stats["alert_message"]=""

        # Draw face boxes with ID verification colour
        for (x,y,w,h) in faces:
            if face_verify_result and face_verify_result["face_found"]:
                col = (0,255,0) if face_verify_result["match"] else (0,0,255)
                label = f"VERIFIED {face_verify_result['confidence']}%" if face_verify_result["match"] else f"MISMATCH {face_verify_result['confidence']}%"
            else:
                col=(0,255,0) if fc==1 else(0,0,255)
                label="Candidate" if fc==1 else "ALERT"
            cv2.rectangle(frame,(x,y),(x+w,y+h),col,2)
            cv2.putText(frame,label,(x,y-10),cv2.FONT_HERSHEY_SIMPLEX,.5,col,2)

        # Draw phone boxes
        for (x,y,w,h,conf) in phones:
            ov=frame.copy(); cv2.rectangle(ov,(x,y),(x+w,y+h),(80,0,220),-1)
            cv2.addWeighted(ov,.15,frame,.85,0,frame)
            cv2.rectangle(frame,(x,y),(x+w,y+h),(180,80,255),2)
            lbl=f"PHONE {conf:.0%}"
            (lw,lh),_=cv2.getTextSize(lbl,cv2.FONT_HERSHEY_SIMPLEX,.6,2)
            cv2.rectangle(frame,(x,y-lh-12),(x+lw+8,y),(180,80,255),-1)
            cv2.putText(frame,lbl,(x+4,y-5),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2)

        _,buf=cv2.imencode(".jpg",frame,[cv2.IMWRITE_JPEG_QUALITY,85])
        return {"face_count":fc,"phone_detected":pd,"phone_count_in_frame":len(phones),
                "alert":alert,"severity":sev,
                "processed_frame":"data:image/jpeg;base64,"+base64.b64encode(buf).decode(),
                "stats":stats.copy(),"violation_score":stats["violation_score"],
                "yolo_active":stats["yolo_available"],
                "face_verify":face_verify_result,
                "face_rec_active": registered_encoding is not None and face_rec_available}
    except Exception as e:
        return {"error":str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# Page routes
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/proctor")
def proctor_dashboard():
    return render_template("index.html")

@app.route("/quiz/register")
def quiz_register():
    return render_template("register.html")

@app.route("/quiz/<sid>")
def quiz_page(sid):
    if sid not in quiz_sessions:
        return render_template("404.html"), 404
    sess=quiz_sessions[sid]
    return render_template("quiz.html", session=sess, quiz=QUIZ_BANK[sess["subject"]], sid=sid)

@app.route("/quiz/<sid>/result")
def quiz_result(sid):
    if sid not in quiz_sessions:
        return render_template("404.html"), 404
    sess=quiz_sessions[sid]
    return render_template("result.html", session=sess, quiz=QUIZ_BANK[sess["subject"]],
                           violations=list(reversed(violation_log[-20:])),
                           violation_count=len(violation_log),
                           proctor_score=stats["violation_score"])

@app.route("/admin")
def admin_dashboard():
    return render_template("admin.html", results=list(reversed(quiz_results[-50:])), subjects=QUIZ_BANK)

# ─────────────────────────────────────────────────────────────────────────────
# Quiz API
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/quiz/start", methods=["POST"])
def quiz_start():
    global registered_encoding
    name    = request.form.get("name","").strip()
    email   = request.form.get("email","").strip()
    subject = request.form.get("subject","python")
    if not name or not email:
        return jsonify({"error":"Name and email required"}),400
    if subject not in QUIZ_BANK:
        return jsonify({"error":"Invalid subject"}),400

    sid = str(uuid.uuid4())[:8].upper()
    id_photo_path = None
    face_encoded  = False

    # Handle ID photo upload
    if "id_photo" in request.files:
        photo = request.files["id_photo"]
        if photo and photo.filename:
            filename = f"{sid}_id.jpg"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            photo.save(filepath)
            id_photo_path = filename
            # Encode face from uploaded photo
            if face_rec_available:
                img = cv2.imread(filepath)
                if img is not None:
                    enc = encode_face_from_image(img)
                    if enc is not None:
                        registered_encoding = enc
                        face_encoded = True
                        print(f"✅ Face encoded for session {sid}")
                    else:
                        print(f"⚠️  No face found in uploaded photo for {sid}")

    quiz_sessions[sid] = {
        "session_id":sid,"name":name,"email":email,"subject":subject,
        "start_time":datetime.now().isoformat(),"answers":{},"submitted":False,"score":None,
        "id_photo":id_photo_path,"face_encoded":face_encoded,
    }
    reset_proctor_state()
    if face_encoded:
        registered_encoding = registered_encoding  # keep it after reset

    return jsonify({"session_id":sid,"redirect":f"/quiz/{sid}",
                    "face_encoded":face_encoded,"face_rec_available":face_rec_available})

@app.route("/api/quiz/submit", methods=["POST"])
def quiz_submit():
    data=request.get_json() or {}
    sid=data.get("session_id")
    answers=data.get("answers",{})

    if sid not in quiz_sessions:
        return jsonify({"error":"Session not found"}),404

    sess=quiz_sessions[sid]
    qs=QUIZ_BANK[sess["subject"]]["questions"]

    correct=sum(1 for q in qs if str(q["id"]) in answers and answers[str(q["id"])]==q["ans"])
    total=len(qs)
    pct=round(correct/total*100)

    grade="A" if pct>=90 else "B" if pct>=75 else "C" if pct>=60 else "D" if pct>=40 else "F"

    sess.update({
    "answers":answers,
    "submitted":True,
    "score":correct,
    "percentage": pct,   # ✅ ADD THIS LINE
    "grade": grade,      # (good to add if not already)
    "total":total,
    "end_time":datetime.now().isoformat(),
    "proctor_score":stats["violation_score"],
    "violations":len(violation_log),
    "tab_switch_count":stats["tab_switch_count"],
    "phone_count":stats["phone_count"],
    "copy_paste_count":stats["copy_paste_count"],
    "audio_alert_count":stats["audio_alert_count"],
    "no_face_count":stats["no_face_count"],
    "face_mismatch_count":stats["face_mismatch_count"],
    "screen_record_count":stats["screen_record_count"],
    "identity_score":stats["identity_score"]
})


    quiz_results.append(sess.copy())

    # ✅ ADD HERE (INDENTED INSIDE FUNCTION)
    insert_result(
        sess["name"],
        len(violation_log),
        stats["violation_score"]
    )

    # ✅ THIS MUST ALSO BE INSIDE FUNCTION
    return jsonify({
        "score":correct,
        "total":total,
        "percentage":pct,
        "grade":grade,
        "redirect":f"/quiz/{sid}/result"
    })
# ─────────────────────────────────────────────────────────────────────────────
# Proctor API
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/analyze", methods=["POST"])
def analyze():
    data=request.get_json()
    if not data or "frame" not in data: return jsonify({"error":"No frame"}),400
    return jsonify(analyze_frame(data["frame"]))

@app.route("/api/tab_switch", methods=["POST"])
def tab_switch():
    stats["tab_switch_count"]+=1
    add_violation("TAB_SWITCH","Candidate switched tab/window","warning")
    return jsonify({"status":"logged","count":stats["tab_switch_count"]})

@app.route("/api/copy_paste", methods=["POST"])
def copy_paste():
    data=request.get_json() or {}; ev=data.get("event","copy"); ln=data.get("text_length",0)
    stats["copy_paste_count"]+=1
    sev="critical"if ev=="paste"else"warning"
    msgs={"paste":f"Paste detected — {ln} chars","copy":f"Copy detected — {ln} chars","cut":f"Cut detected — {ln} chars"}
    add_violation("COPY_PASTE",msgs.get(ev,"Copy/Paste detected"),sev)
    return jsonify({"status":"logged"})

@app.route("/api/audio", methods=["POST"])
def audio_route():
    data=request.get_json() or {}
    result=analyze_audio(data.get("samples",[]),data.get("sample_rate",16000))
    stats["audio_volume"]=result["volume_db"]; stats["audio_voices"]=result["suspected_voices"]
    stats["audio_suspicious"]=result["suspicious"]
    if result["suspicious"]:
        stats["audio_alert_count"]+=1
        if stats["audio_alert_count"]%6==1:
            if result["suspected_voices"]>=2:
                add_violation("AUDIO_MULTIPLE_VOICES",f"Multiple voices ({result['suspected_voices']}, {result['volume_db']:.0f}dB)","critical")
            elif result["is_loud"]:
                add_violation("AUDIO_LOUD",f"Loud audio ({result['volume_db']:.0f}dB)","warning")
    return jsonify({**result,"stats":stats.copy()})

@app.route("/api/screen_record", methods=["POST"])
def screen_record():
    """Called when browser detects screen recording / sharing attempt."""
    data=request.get_json() or {}
    event_type = data.get("event","screen_share")
    stats["screen_record_count"]+=1
    msgs = {
        "screen_share":   "Screen sharing/recording detected via getDisplayMedia",
        "devtools_open":  "Browser DevTools opened during exam",
        "print_screen":   "Print Screen key pressed",
        "context_menu":   "Right-click context menu attempted",
    }
    sev = "critical" if event_type in ("screen_share","devtools_open") else "warning"
    add_violation("SCREEN_RECORD", msgs.get(event_type, "Screen recording activity detected"), sev)
    return jsonify({"status":"logged","count":stats["screen_record_count"]})

@app.route("/api/stats")
def get_stats():
    with log_lock:
        return jsonify({"stats":stats.copy(),"violations":list(reversed(violation_log[-50:]))})

@app.route("/api/violations")
def get_violations():
    with log_lock:
        return jsonify(list(reversed(violation_log)))

@app.route("/api/reset", methods=["POST"])
def reset():
    reset_proctor_state()
    return jsonify({"status":"reset"})
from database import get_all_results

from database import get_all_results

@app.route("/results")
def show_results():
    data = get_all_results()
    return render_template("results.html", data=data)
# ─────────────────────────────────────────────────────────────────────────────
from database import create_table   # add this at top of file

if __name__ == "__main__":
    create_table()   # ✅ ADD THIS LINE (IMPORTANT)
    
    print("🚀 ProctorQuiz v4.0 — http://localhost:5000")
    print("   Features: Face·Phone·Audio·CopyPaste·TabSwitch·FaceRecognition·ScreenLock")
    
    app.run(debug=True, threaded=True)
