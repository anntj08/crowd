import cv2
import time
try:
    import winsound
except:
    winsound = None
import math
import threading
from flask import Flask, Response, jsonify, request, render_template
from flask_cors import CORS
from ultralytics import YOLO
import serial

app = Flask(__name__)
# Enable CORS so the React app running on port 5173 can talk to this API on port 5000
CORS(app)  

# ==============================
# CONFIGURATION (MESS HALL)
# ==============================
MODEL_PATH = "yolov8m.pt"
CAMERA_INDEX = 0

MAX_CAPACITY = 25
CONFIDENCE = 0.15
HEAD_RATIO = 0.18
MIN_PERSON_AREA = 800
HEAD_MERGE_DISTANCE = 20

ALARM_FREQ = 1200
ALARM_DURATION = 1000
ALARM_INTERVAL = 3
HISTORY_SIZE = 5

# ==============================
# GLOBAL STATE
# ==============================
global_state = {
    "people_count": 10,
    "status_text": "NORMAL",
    "status_color": "green",  # Will map to CSS easily
    "door_state": "OPEN",
    "crowd_history": []
}
state_lock = threading.Lock()
frame_bytes = b''

# ==============================
# INITIALIZATION
# ==============================
arduino = None
try:
    # Try to connect to Arduino
    arduino = serial.Serial('COM5', 9600, timeout=1)  # change COM port
    time.sleep(2)
except Exception as e:
    print(f"Hardware Error: Could not connect to Arduino: {e}")

try:
    model = YOLO(MODEL_PATH)
except Exception as e:
    print(f"Model Error: Could not load YOLO: {e}")
    model = None

cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
if cap.isOpened():
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
else:
    print("Warning: Camera not accessible. The video feed will not work.")

# ==============================
# VIDEO PROCESSING THREAD
# ==============================
def video_loop():
    global frame_bytes
    last_alarm_time = 0
    count_history = []
    
    while True:
        if not cap.isOpened() or model is None:
            time.sleep(1)
            continue
            
        ret, frame = cap.read()
        if not ret:
            continue

        head_points = []
        current_time = time.time()

        # ------------------------------
        # PERSON DETECTION
        # ------------------------------
        results = model(frame, conf=CONFIDENCE)
        if results[0].boxes is not None:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                if int(boxes.cls[i]) != 0:
                    continue
                x1, y1, x2, y2 = map(int, boxes.xyxy[i])
                area = (x2 - x1) * (y2 - y1)
                if area < MIN_PERSON_AREA:
                    continue
                    
                # ------------------------------
                # IMPROVED HEAD ESTIMATION
                # ------------------------------
                hx = int(x1 + 0.5 * (x2 - x1))
                hy = int(y1 + (y2 - y1) * HEAD_RATIO)
                head_points.append((hx, hy))

        # ------------------------------
        # CLUSTER HEAD POINTS (DEDUP)
        # ------------------------------
        unique_heads = []
        for hx, hy in head_points:
            keep = True
            for ux, uy in unique_heads:
                if math.hypot(hx - ux, hy - uy) < HEAD_MERGE_DISTANCE:
                    keep = False
                    break
            if keep:
                unique_heads.append((hx, hy))

        # ------------------------------
        # TEMPORAL SMOOTHING
        # ------------------------------
        current_count = len(unique_heads)
        count_history.append(current_count)
        if len(count_history) > HISTORY_SIZE:
            count_history.pop(0)

        people_count = int(sum(count_history) / len(count_history)) if count_history else 0

        # ------------------------------
        # ALARM + DOOR CONTROL
        # ------------------------------
        status_text = "NORMAL"
        status_color_bgr = (0, 255, 0)
        status_color_name = "green"
        
        with state_lock:
            ds = global_state["door_state"]
        
        if people_count >= MAX_CAPACITY:
            status_text = "OVER CROWDED!"
            status_color_bgr = (0, 0, 255)
            status_color_name = "red"
            
            if ds != "CLOSE":
                if arduino: arduino.write(b"CLOSE\n")
                ds = "CLOSE"
                
            if current_time - last_alarm_time >= ALARM_INTERVAL:
    if winsound:
        threading.Thread(
            target=winsound.Beep,
            args=(ALARM_FREQ, ALARM_DURATION),
            daemon=True
        ).start()
    last_alarm_time = current_time
        else:
            status_text = "NORMAL"
            status_color_bgr = (0, 255, 0)
            status_color_name = "green"

            if ds != "OPEN" and ds != "UNKNOWN":
                if arduino: arduino.write(b"OPEN\n")
                ds = "OPEN"

        # ------------------------------
        # VISUALIZATION
        # ------------------------------
        for hx, hy in unique_heads:
            cv2.circle(frame, (hx, hy), 6, (0, 255, 0), -1)

        cv2.putText(frame, f"People Count: {people_count}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
        cv2.putText(frame, f"Status: {status_text}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color_bgr, 3)

        # ------------------------------
        # UPDATE STATE CONTROLLER
        # ------------------------------
        with state_lock:
            global_state["people_count"] = people_count
            global_state["status_text"] = status_text
            global_state["status_color"] = status_color_name
            global_state["door_state"] = ds
            
            # Record trend data every second broadly
            time_str = time.strftime("%H:%M:%S")
            if not global_state["crowd_history"] or global_state["crowd_history"][-1]["time"] != time_str:
                global_state["crowd_history"].append({"time": time_str, "count": people_count})
                if len(global_state["crowd_history"]) > 60: # Keep last 60 seconds roughly
                    global_state["crowd_history"].pop(0)

        # Encode frame to memory
        ret, buffer = cv2.imencode('.jpg', frame)
        if ret:
            frame_bytes = buffer.tobytes()

# Start background camera thread
threading.Thread(target=video_loop, daemon=True).start()

# ==============================
# FLASK ENDPOINTS
# ==============================
@app.route('/')
def index():
    return render_template('index.html')

def generate():
    global frame_bytes
    while True:
        if frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.05)

@app.route('/video_feed')
def video_feed():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/crowd_data')
def get_crowd_data():
    with state_lock:
        return jsonify({
            "people_count": global_state["people_count"],
            "status_text": global_state["status_text"],
            "status_color": global_state["status_color"],
            "door_state": global_state["door_state"]
        })

@app.route('/crowd_history')
def get_crowd_history():
    with state_lock:
        return jsonify(global_state["crowd_history"])

@app.route('/door_control', methods=['POST'])
def door_control():
    data = request.json
    cmd = data.get('command', '')
    
    with state_lock:
        if cmd == "OPEN":
            if arduino: arduino.write(b"OPEN\n")
            global_state["door_state"] = "OPEN"
        elif cmd == "CLOSE":
            if arduino: arduino.write(b"CLOSE\n")
            global_state["door_state"] = "CLOSE"
            
    return jsonify({"status": "success", "door_state": global_state["door_state"]})

if __name__ == '__main__':
    import webbrowser
    import threading
    print("\n" + "="*50)
    print("🌍 WEB DASHBOARD STARTING...")
    print("🌍 PLEASE OPEN YOUR BROWSER AND GO TO:")
    print("🌍 http://127.0.0.1:5000")
    print("="*50 + "\n")
    # Automatically open the browser after 1.5 seconds
    threading.Timer(1.5, lambda: webbrowser.open('http://127.0.0.1:5000')).start()
    app.run(host='0.0.0.0', port=5000, threaded=True)
