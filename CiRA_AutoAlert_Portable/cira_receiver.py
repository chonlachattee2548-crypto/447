"""Local JSON receiver for testing CiRA CORE RestPutJson integration."""

from http.server import BaseHTTPRequestHandler
from datetime import datetime
import hashlib
import json
import os
from queue import Empty, Full, Queue
import shutil
import tempfile
import threading
import time
from collections import deque
from urllib.request import urlopen


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLED_AUDIO_DIR = os.path.join(PROJECT_DIR, "audio")
AUDIO_DIR = (
    BUNDLED_AUDIO_DIR
    if os.path.isdir(BUNDLED_AUDIO_DIR)
    else r"C:\Users\Chonlachat2005\Downloads\เสียงพูด 447"
)
TTS_MODEL_ID = "VIZINTZOR/VachanaTTS"
TTS_SPEED = 0.82
TTS_VOICE_CHOICES = {"th_f_1", "th_m_1", "th_f_2", "th_m_2"}
TTS_VOICE_FILE = os.path.join(PROJECT_DIR, "tts_voice.txt")


def configured_tts_voice():
    voice = os.environ.get("CIRA_TTS_VOICE", "").strip().lower()
    if not voice:
        try:
            with open(TTS_VOICE_FILE, "r", encoding="utf-8-sig") as voice_file:
                voice = voice_file.read().strip().lower()
        except OSError:
            voice = ""
    if voice not in TTS_VOICE_CHOICES:
        return "th_f_1"
    return voice


TTS_VOICE = configured_tts_voice()
TTS_BACKEND = "local_vachana"
TTS_CACHE_DIR = os.path.join(PROJECT_DIR, "cache", "tts")
TTS_MODEL_CACHE_DIR = os.path.join(PROJECT_DIR, "cache", "vachana", "voices")
MODEL_LABELS_FILE = os.path.join(PROJECT_DIR, "class_labels_th.json")
TTS_RETRY_SECONDS = 60.0
TTS_ATTEMPTS_PER_VOICE = 1
TTS_SESSION_MODE = "warming"
AUDIO_GAP_SECONDS = 3.0
REARM_SECONDS = 4.0
SEAT_REARM_SECONDS = 10.0
PERSON_REPEAT_SECONDS = 3.0
PERSON_INFO_REPEAT_SECONDS = 15.0
CROWD_REPEAT_SECONDS = 3.0
NORMAL_REPEAT_SECONDS = 3.0
APPROACH_REPEAT_SECONDS = 3.0
NEAR_REPEAT_SECONDS = 3.0
APPROACH_WINDOW_SECONDS = 2.5
APPROACH_GROWTH_RATIO = 2.0
MIN_APPROACH_EVIDENCE_SECONDS = 0.8
WALK_LANE_LEFT = 0.40
WALK_LANE_RIGHT = 0.60
WALK_PATH_ENTRY_Y = 0.76
# The narration lane is intentionally wider than the collision lane. A box can
# be worth mentioning without being close enough to tell the user to stop.
SPEECH_LANE_LEFT = 0.15
SPEECH_LANE_RIGHT = 0.85
SPEECH_MIN_CENTER_Y = 0.20
SPEECH_MIN_AREA = {
    # Keep distant/small detections audible as scene information. These values
    # do not affect the stricter collision/stop thresholds below.
    "person": 0.0004,
    "car": 0.0004,
    "bus": 0.0004,
    "truck": 0.0004,
    "motorbike": 0.0004,
    "chair": 0.0020,
    "bench": 0.0020,
    "diningtable": 0.0020,
    "bicycle": 0.0004,
    "umbrella": 0.0020,
    "backpack": 0.0020,
    "handbag": 0.0020,
    "suitcase": 0.0020,
    "bottle": 0.0015,
    "pottedplant": 0.0020,
}
TRACK_MAX_GAP_SECONDS = 1.25
TRACK_MATCH_DISTANCE = 0.18
TRACK_MIN_IOU = 0.05
# Side narration uses a center dead-zone and track-level hysteresis so boxes
# hovering around the image midpoint do not alternate left/right every frame.
SIDE_LEFT_ENTER = 0.40
SIDE_LEFT_EXIT = 0.48
SIDE_RIGHT_EXIT = 0.52
SIDE_RIGHT_ENTER = 0.60
TRACK_CENTER_EMA_ALPHA = 0.35
TRACK_RANGE_EMA_ALPHA = 0.35
DECISION_LOG_DEDUPE_SECONDS = 1.5
STREAM_STALE_SECONDS = 8.0
MAX_HTTP_BODY_BYTES = 2 * 1024 * 1024
AUDIO_RECOVERY_GRACE_SECONDS = 8.0
AUDIO_DEVICE_POLL_SECONDS = 5.0
NEAR_AREA_THRESHOLDS = {
    "person": 0.14,
    "car": 0.18,
    "bus": 0.18,
    "truck": 0.18,
    "motorbike": 0.18,
    "bicycle": 0.18,
    "chair": 0.12,
    "bench": 0.12,
    "diningtable": 0.12,
    "umbrella": 0.10,
    "backpack": 0.10,
    "handbag": 0.10,
    "suitcase": 0.12,
    "bottle": 0.10,
    "pottedplant": 0.12,
}
DEFAULT_CLASS_LABELS_TH = {
    "person": "คน", "car": "รถ", "bus": "รถบัส", "truck": "รถบรรทุก",
    "motorbike": "รถจักรยานยนต์", "motorcycle": "รถจักรยานยนต์",
    "bicycle": "จักรยาน", "chair": "เก้าอี้", "bench": "ม้านั่ง",
    "diningtable": "โต๊ะ", "table": "โต๊ะ", "lift": "ลิฟต์",
    "elevator": "ลิฟต์", "elevator door": "ประตูลิฟต์",
    "elevator_door": "ประตูลิฟต์", "door": "ประตู", "stairs": "บันได",
    "bathroom": "ห้องน้ำ", "restroom": "ห้องน้ำ", "toilet room": "ห้องน้ำ",
    "men restroom": "ห้องน้ำชาย", "mens restroom": "ห้องน้ำชาย",
    "male restroom": "ห้องน้ำชาย", "men's restroom": "ห้องน้ำชาย",
    "male bathroom": "ห้องน้ำชาย", "men toilet": "ห้องน้ำชาย",
    "women restroom": "ห้องน้ำหญิง", "womens restroom": "ห้องน้ำหญิง",
    "female restroom": "ห้องน้ำหญิง", "women's restroom": "ห้องน้ำหญิง",
    "female bathroom": "ห้องน้ำหญิง", "women toilet": "ห้องน้ำหญิง",
    "emergency exit": "ทางออกฉุกเฉิน", "fire exit": "ทางหนีไฟ",
    "exit sign": "ป้ายทางออกฉุกเฉิน", "classroom door": "ประตูห้องเรียน",
    "classroom entrance": "ประตูห้องเรียน", "classroom": "ห้องเรียน",
    "backpack": "กระเป๋าเป้", "handbag": "กระเป๋าถือ", "suitcase": "กระเป๋าเดินทาง",
    "umbrella": "ร่ม", "bottle": "ขวด", "pottedplant": "กระถางต้นไม้",
    "traffic light": "สัญญาณไฟจราจร", "stop sign": "ป้ายหยุด",
    "fire hydrant": "หัวจ่ายน้ำดับเพลิง", "parking meter": "ตู้จอดรถ",
    "train": "รถไฟ", "oven": "เตาอบ", "refrigerator": "ตู้เย็น",
    "tvmonitor": "จอโทรทัศน์", "tv monitor": "จอโทรทัศน์", "couch": "โซฟา",
    "bed": "เตียง", "toilet": "โถส้วม", "sink": "อ่างล้างมือ",
    "book": "หนังสือ", "clock": "นาฬิกา", "vase": "แจกัน",
}


def load_class_labels_th():
    labels = dict(DEFAULT_CLASS_LABELS_TH)
    try:
        with open(MODEL_LABELS_FILE, "r", encoding="utf-8-sig") as labels_file:
            custom = json.load(labels_file)
        if isinstance(custom, dict):
            for name, thai_name in custom.items():
                if isinstance(name, str) and isinstance(thai_name, str) and thai_name.strip():
                    labels[name.strip().lower()] = thai_name.strip()
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError) as exc:
        print(f"อ่าน class_labels_th.json ไม่สำเร็จ ใช้ชื่อพื้นฐาน: {exc}", flush=True)
    return labels


CLASS_LABELS_TH = load_class_labels_th()
CUSTOM_CLASS_NAMES = set()
try:
    with open(MODEL_LABELS_FILE, "r", encoding="utf-8-sig") as labels_file:
        custom_labels = json.load(labels_file)
    if isinstance(custom_labels, dict):
        CUSTOM_CLASS_NAMES = {
            str(name).strip().lower() for name, label in custom_labels.items()
            if isinstance(name, str) and isinstance(label, str) and label.strip()
        }
except (OSError, json.JSONDecodeError, AttributeError):
    pass
DEFAULT_SPEECH_MIN_AREA = 0.002
DEFAULT_NEAR_AREA_THRESHOLD = 1.0
PERSON_CLASSES = {"person"}
VEHICLE_CLASSES = {"car", "bus", "truck", "motorbike"}
SEAT_CLASSES = {"chair", "bench"}
TABLE_CLASSES = {"diningtable"}
last_audio_time = 0.0
alert_states = {}
area_histories = {}
audio_error_reported = False
last_status_log_time = 0.0
last_receive_log_time = 0.0
last_http_time = 0.0
stream_was_stale = False
stream_state_lock = threading.Lock()
frame_queue = Queue(maxsize=1)
frame_enqueue_lock = threading.Lock()
frames_dropped = 0
current_audio_level = 0
active_audio_deadline = 0.0
latest_chairs = []
chair_info_announced = set()
audio_lock = threading.RLock()
frame_lock = threading.RLock()
decision_log_lock = threading.Lock()
active_tracks = {}
next_track_number = 1
decision_log_recent = {}
last_filter_reasons = []
decision_log_error_reported = False
audio_device_snapshot = None
last_audio_device_check = 0.0
tts_queue = Queue()
tts_jobs = {}
tts_lock = threading.Lock()
tts_workers_started = False
tts_service_failure_until = 0.0
tts_model_lock = threading.Lock()
vachana_tts_module = None
LOG_DIR = os.path.join(PROJECT_DIR, "logs")
DECISION_LOG_PATH = os.path.join(LOG_DIR, "decision_log.jsonl")


def log_status(message):
    """Avoid flooding the terminal when CiRA sends video frames rapidly."""
    global last_status_log_time
    now = time.monotonic()
    if now - last_status_log_time >= 2:
        print(message, flush=True)
        last_status_log_time = now


def log_receive(message):
    """Show a live, flushed summary at most once per second, independently of status logs."""
    global last_receive_log_time
    now = time.monotonic()
    if now - last_receive_log_time >= 1.0:
        print(message, flush=True)
        last_receive_log_time = now


def spoken_text_from_filename(filename):
    """Use the existing Thai alert wording as the controlled TTS sentence."""
    return os.path.splitext(os.path.basename(filename))[0].strip()


def tts_cache_path(text, voice=None):
    normalized = " ".join(str(text).split())
    voice = voice or TTS_VOICE
    cache_key = f"{TTS_BACKEND}\n{TTS_MODEL_ID}\n{voice}\n{TTS_SPEED:.2f}\n{normalized}".encode("utf-8")
    digest = hashlib.sha256(cache_key).hexdigest()
    return os.path.join(TTS_CACHE_DIR, f"{digest}.wav")


def tts_voices():
    """Always use one configured voice so cached clips never change speaker."""
    return (TTS_VOICE,)


def find_cached_tts(text):
    for voice in tts_voices():
        cache_path = tts_cache_path(text, voice)
        if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 0:
            return cache_path, voice
    return None, None


def _load_vachana_tts_module():
    """Load Vachana's CPU voice model from a project-local cache."""
    global vachana_tts_module
    with tts_model_lock:
        if vachana_tts_module is not None:
            return vachana_tts_module
        os.makedirs(TTS_MODEL_CACHE_DIR, exist_ok=True)
        import importlib

        module = importlib.import_module("vachanatts.main")
        from vachanatts.voice import Voice

        def load_cached_voice(voice_name):
            model_path = os.path.join(TTS_MODEL_CACHE_DIR, f"{voice_name}.onnx")
            config_path = os.path.join(TTS_MODEL_CACHE_DIR, "speaker_config.json")
            base_url = f"https://huggingface.co/{TTS_MODEL_ID}/resolve/main"
            _download_model_file(f"{base_url}/voices/{voice_name}.onnx", model_path)
            _download_model_file(f"{base_url}/speaker_config.json", config_path)
            return Voice.load(model_path, config_path, use_cuda=False)

        # Vachana's wrapper stores models under the current working directory
        # and downloads without a timeout. Override its loader so paths stay in
        # this project and interrupted network requests fail into MP3 fallback.
        module.load_voice = load_cached_voice
        vachana_tts_module = module
        return module


def _download_model_file(url, target_path):
    minimum_size = 32 if os.path.basename(target_path) == "speaker_config.json" else 1024 * 1024
    if os.path.isfile(target_path) and os.path.getsize(target_path) > minimum_size:
        return target_path
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    file_descriptor, temporary_path = tempfile.mkstemp(
        prefix="voice-", suffix=".download", dir=os.path.dirname(target_path)
    )
    os.close(file_descriptor)
    try:
        print(f"กำลังดาวน์โหลดโมเดลเสียง {TTS_VOICE}: {os.path.basename(target_path)}", flush=True)
        with urlopen(url, timeout=30) as response, open(temporary_path, "wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        if os.path.getsize(temporary_path) <= minimum_size:
            raise RuntimeError("ไฟล์โมเดลเสียงที่ดาวน์โหลดมีขนาดไม่ถูกต้อง")
        os.replace(temporary_path, target_path)
        print(f"ดาวน์โหลดโมเดลเสียงเสร็จแล้ว: {os.path.basename(target_path)}", flush=True)
        return target_path
    finally:
        if os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass


def _save_local_tts_audio(text, target_path):
    """Generate a Thai WAV clip using the selected local Vachana voice."""
    module = _load_vachana_tts_module()
    module.TTS(
        text,
        voice=TTS_VOICE,
        output=target_path,
        volume=1.0,
        speed=TTS_SPEED,
        noise_w_scale=0.8,
    )
    if not os.path.isfile(target_path) or os.path.getsize(target_path) <= 44:
        raise RuntimeError("โมเดล Vachana สร้างไฟล์เสียงว่างหรือไม่สมบูรณ์")


def _generate_tts_cache(text):
    os.makedirs(TTS_CACHE_DIR, exist_ok=True)
    errors = []
    for voice in tts_voices():
        cache_path = tts_cache_path(text, voice)
        if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 0:
            return cache_path, voice
        for attempt in range(TTS_ATTEMPTS_PER_VOICE):
            file_descriptor, temporary_path = tempfile.mkstemp(
                prefix="tts-", suffix=".wav", dir=TTS_CACHE_DIR
            )
            os.close(file_descriptor)
            try:
                _save_local_tts_audio(text, temporary_path)
                if not os.path.isfile(temporary_path) or os.path.getsize(temporary_path) == 0:
                    raise RuntimeError("Local Thai TTS returned an empty audio file")
                os.replace(temporary_path, cache_path)
                return cache_path, voice
            except Exception as exc:
                errors.append((voice, exc))
                if attempt + 1 < TTS_ATTEMPTS_PER_VOICE:
                    time.sleep(1.0 + attempt)
            finally:
                if os.path.exists(temporary_path):
                    try:
                        os.remove(temporary_path)
                    except OSError:
                        pass
    attempted = ", ".join(tts_voices())
    last_voice, last_error = errors[-1]
    raise RuntimeError(
        f"โมเดล TTS ในเครื่องใช้ไม่ได้ ({attempted}); ล่าสุด {last_voice}: "
        f"{type(last_error).__name__}: {last_error}"
    ) from last_error


def _tts_job_finished(cache_path, text, job):
    global tts_service_failure_until, TTS_SESSION_MODE
    try:
        job["result"], job["voice"] = _generate_tts_cache(text)
    except Exception as exc:
        job["exception"] = exc
        with tts_lock:
            tts_service_failure_until = time.monotonic() + TTS_RETRY_SECONDS
            TTS_SESSION_MODE = "mp3"
            if tts_jobs.get(cache_path) is job:
                tts_jobs.pop(cache_path, None)
        record_decision(
            "error", "tts_generation_failed_using_mp3_fallback", dedupe=False,
            text=text, voices=tts_voices(),
            exception=f"{type(exc).__name__}: {exc}",
        )
        print(
            f"โมเดล TTS ในเครื่องสร้างเสียงไม่ได้; ใช้ MP3 สำรอง "
            f"และพักการสร้างเสียง {TTS_RETRY_SECONDS:.0f} วินาที: {exc}",
            flush=True,
        )
    else:
        with tts_lock:
            tts_service_failure_until = 0.0
            if tts_jobs.get(cache_path) is job:
                tts_jobs.pop(cache_path, None)
        record_decision(
            "tts_ready", "speech_cached_for_reuse", dedupe=False,
            text=text, voice=job["voice"], cache_path=job["result"],
        )
        if not job.get("prewarm"):
            print(
                f"เสียง TTS พร้อมใช้ ({TTS_BACKEND}, {job['voice']}) และบันทึก cache แล้ว: {text}",
                flush=True,
            )
    finally:
        job["event"].set()


def _tts_worker():
    """Daemon worker keeps model loading and synthesis off the HTTP frame path."""
    while True:
        cache_path, text, job = tts_queue.get()
        try:
            if TTS_SESSION_MODE == "mp3" and job.get("prewarm"):
                job["exception"] = RuntimeError(
                    "ยกเลิกการเตรียมประโยคที่เหลือ เพราะ TTS ประโยคก่อนหน้าล้มเหลว"
                )
                with tts_lock:
                    if tts_jobs.get(cache_path) is job:
                        tts_jobs.pop(cache_path, None)
                job["event"].set()
                continue
            _tts_job_finished(cache_path, text, job)
        finally:
            tts_queue.task_done()


def schedule_tts_generation(text, *, prewarm=False):
    """Generate speech off the HTTP request path; return its future if available."""
    normalized = " ".join(str(text).split())
    if not normalized or len(normalized) > 300:
        return None, None
    if TTS_SESSION_MODE == "mp3" and not prewarm:
        return None, None
    cached_path, _voice = find_cached_tts(normalized)
    if cached_path:
        return cached_path, None
    cache_path = tts_cache_path(normalized, TTS_VOICE)

    global tts_workers_started
    with tts_lock:
        if tts_service_failure_until > time.monotonic():
            return cache_path, None
        job = tts_jobs.get(cache_path)
        if job is None:
            if not tts_workers_started:
                threading.Thread(
                    target=_tts_worker,
                    name="cira-tts-worker",
                    daemon=True,
                ).start()
                tts_workers_started = True
            job = {
                "event": threading.Event(), "result": None,
                "exception": None, "voice": None, "prewarm": prewarm,
            }
            tts_jobs[cache_path] = job
            tts_queue.put((cache_path, normalized, job))
        elif prewarm:
            job["prewarm"] = True
    return cache_path, job


def choose_speech_audio(filename, text=None):
    """Use one fixed backend per run; fall back for the whole run on failure."""
    fallback_path = os.path.join(AUDIO_DIR, filename)
    text = text or spoken_text_from_filename(filename)
    if TTS_SESSION_MODE != "tts":
        backend = "mp3_warmup" if TTS_SESSION_MODE == "warming" else "mp3_session_fallback"
        return fallback_path, backend, text
    cache_path, future = schedule_tts_generation(text)
    if cache_path and os.path.isfile(cache_path):
        return cache_path, f"{TTS_BACKEND}_cached", text
    if future is not None and future["event"].is_set() and future.get("result"):
        return future["result"], f"{TTS_BACKEND}_cached", text
    if TTS_SESSION_MODE == "mp3":
        return fallback_path, "mp3_session_fallback", text
    return None, f"{TTS_BACKEND}_pending", text


def prewarm_tts_cache():
    """Warm every finite alert sentence before accepting CiRA frames."""
    global TTS_SESSION_MODE
    messages = sorted(all_supported_tts_messages())
    jobs = []
    for index, text in enumerate(messages, start=1):
        cache_path, future = schedule_tts_generation(text, prewarm=True)
        if cache_path and os.path.isfile(cache_path):
            continue
        if future is None:
            TTS_SESSION_MODE = "mp3"
            break
        jobs.append((index, text, future))
    print(
        f"กำลังเตรียมเสียง {len(messages)} ประโยคด้วยเสียง {TTS_VOICE}; "
        f"รอให้เสร็จก่อนเปิด Flow เพื่อให้ทั้งรอบใช้เสียง backend เดียวกัน",
        flush=True,
    )
    failed = TTS_SESSION_MODE == "mp3"
    completed = len(messages) - len(jobs)
    for index, text, job in jobs:
        job["event"].wait()
        completed += 1
        if job.get("exception") is not None or not job.get("result"):
            failed = True
        if completed % 10 == 0 or index == len(messages):
            print(f"เตรียมเสียงแล้ว {completed}/{len(messages)} ประโยค; ล่าสุด: {text}", flush=True)
    if failed:
        TTS_SESSION_MODE = "mp3"
        print("TTS เตรียมไม่ครบ รอบนี้จะใช้ MP3 สำรองตลอด ไม่สลับไป TTS กลางทาง; ตรวจ logs/decision_log.jsonl", flush=True)
    else:
        TTS_SESSION_MODE = "tts"
        print("TTS พร้อมแล้ว ใช้เสียงเดียวตลอดรอบนี้; ตอนนี้เปิด/รัน Flow ใน CiRA CORE ได้", flush=True)


def start_audio_clip(pygame, audio_path):
    """Try playback, resetting the mixer twice if its output device failed."""
    last_error = None
    for attempt in range(3):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.set_volume(1.0)
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()
            time.sleep(0.12)
            if pygame.mixer.music.get_busy():
                return
            last_error = RuntimeError("pygame รายงานว่าเสียงไม่เริ่มเล่น")
        except Exception as exc:
            last_error = exc
        if attempt < 2:
            print(
                f"ช่องเสียงเริ่มเล่นไม่ได้ กำลังกู้ mixer รอบ {attempt + 1}/2",
                flush=True,
            )
            try:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
            except Exception:
                pass
            time.sleep(0.25)
    raise RuntimeError(f"เปิดเสียงไม่สำเร็จหลังลอง 3 รอบ: {last_error}") from last_error


def read_audio_output_devices(pygame):
    try:
        from pygame._sdl2 import get_audio_device_names
        return tuple(get_audio_device_names(False))
    except Exception:
        return None


def audio_channel_watchdog():
    """Recover a lost mixer/device and clear or restart stuck playback state."""
    global current_audio_level, active_audio_deadline, audio_error_reported
    global audio_device_snapshot, last_audio_device_check
    while True:
        time.sleep(1.0)
        try:
            import pygame
            with audio_lock:
                now = time.monotonic()
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                    pygame.mixer.music.set_volume(1.0)
                    audio_device_snapshot = read_audio_output_devices(pygame)
                    current_audio_level = 0
                    active_audio_deadline = 0.0
                    audio_error_reported = False
                    print("กู้คืน audio mixer ที่หลุดการเชื่อมต่อแล้ว", flush=True)
                    record_decision("recover", "audio_mixer_was_not_initialized", dedupe=False)
                    continue

                if now - last_audio_device_check >= AUDIO_DEVICE_POLL_SECONDS:
                    last_audio_device_check = now
                    devices = read_audio_output_devices(pygame)
                    if devices is not None and audio_device_snapshot is not None and devices != audio_device_snapshot:
                        if pygame.mixer.music.get_busy() and active_audio_deadline and now <= active_audio_deadline:
                            # Finish the current clip before reopening SDL, then
                            # pick up the newly connected/default output device.
                            continue
                        if pygame.mixer.music.get_busy():
                            pygame.mixer.music.stop()
                        pygame.mixer.quit()
                        pygame.mixer.init()
                        pygame.mixer.music.set_volume(1.0)
                        audio_device_snapshot = read_audio_output_devices(pygame)
                        current_audio_level = 0
                        active_audio_deadline = 0.0
                        audio_error_reported = False
                        print("ตรวจพบอุปกรณ์เสียงเปลี่ยน; เชื่อมช่องเสียงกับอุปกรณ์ปัจจุบันใหม่แล้ว", flush=True)
                        record_decision("recover", "audio_output_device_list_changed", dedupe=False,
                                        audio_devices=audio_device_snapshot)
                        continue

                if not pygame.mixer.music.get_busy():
                    current_audio_level = 0
                    active_audio_deadline = 0.0
                elif active_audio_deadline and now > active_audio_deadline:
                    pygame.mixer.music.stop()
                    pygame.mixer.quit()
                    pygame.mixer.init()
                    pygame.mixer.music.set_volume(1.0)
                    current_audio_level = 0
                    active_audio_deadline = 0.0
                    audio_device_snapshot = read_audio_output_devices(pygame)
                    audio_error_reported = False
                    print("กู้คืนช่องเสียงที่ค้างเกินเวลาคลิปแล้ว", flush=True)
                    record_decision("recover", "audio_watchdog_stuck_channel", dedupe=False)
        except Exception as exc:
            if not audio_error_reported:
                print(f"ตรวจ/กู้คืนช่องเสียงไม่สำเร็จ: {type(exc).__name__}: {exc}", flush=True)
                audio_error_reported = True


def record_decision(event, reason, *, dedupe=True, **details):
    """Append a structured decision event; throttle repeated per-frame skips."""
    global decision_log_error_reported
    now = time.monotonic()
    signature = (
        event,
        reason,
        str(details.get("class", "")),
        str(details.get("track_id", "")),
        str(details.get("filename", "")),
        str(details.get("detected", "")),
    )
    with decision_log_lock:
        if dedupe and now - decision_log_recent.get(signature, 0.0) < DECISION_LOG_DEDUPE_SECONDS:
            return
        decision_log_recent[signature] = now
        if len(decision_log_recent) > 1000:
            decision_log_recent.clear()
        entry = {
            "time": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "event": event,
            "reason": reason,
            **details,
        }
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(DECISION_LOG_PATH, "a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            if not decision_log_error_reported:
                print(f"เขียน decision log ไม่ได้: {exc}", flush=True)
                decision_log_error_reported = True


def box_iou(first, second):
    """Intersection over union for normalized xyxy boxes."""
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def get_audio_group(class_name):
    if class_name in PERSON_CLASSES:
        return "person"
    if class_name in VEHICLE_CLASSES:
        return "vehicle"
    if class_name in SEAT_CLASSES:
        return "seat"
    if class_name in TABLE_CLASSES:
        return "table"
    return "obstacle"


def is_supported_class_name(class_name):
    return (
        class_name in NEAR_AREA_THRESHOLDS
        or class_name in CLASS_LABELS_TH
        or any("\u0e00" <= char <= "\u0e7f" for char in str(class_name))
    )


def thai_object_noun(audio_group, class_name=None):
    if class_name:
        mapped = CLASS_LABELS_TH.get(str(class_name).strip().lower())
        if mapped:
            return mapped
        label = str(class_name).strip()
        if any("\u0e00" <= char <= "\u0e7f" for char in label):
            return label
    return {
        "person": "คน",
        "person_info": "คน",
        "vehicle": "รถ",
        "seat": "เก้าอี้",
        "table": "โต๊ะ",
        "obstacle": "สิ่งกีดขวาง",
    }.get(audio_group, "สิ่งกีดขวาง")


def make_info_speech(audio_group, side, center_y, variant=0, class_name=None):
    noun = thai_object_noun(audio_group, class_name)
    variant = max(0, int(variant))
    if side == "front":
        phrases = (
            f"ด้านหน้ามี{noun}อยู่",
            f"ตรวจพบ{noun}อยู่ด้านหน้า",
            f"มี{noun}อยู่ด้านหน้า",
            f"ข้างหน้ามี{noun}",
            f"พบ{noun}อยู่ด้านหน้า",
        )
        return phrases[variant % len(phrases)]
    direction = "ซ้าย" if side == "left" else "ขวา"
    offset = " เยื้องไปทางด้านหน้า" if center_y >= 0.52 else ""
    phrases = (
        f"มี{noun}อยู่ทาง{direction}มือ{offset}",
        f"ทาง{direction}มือมี{noun}อยู่{offset}",
        f"ตรวจพบ{noun}ทาง{direction}มือ{offset}",
        f"พบ{noun}อยู่ด้าน{direction}{offset}",
        f"ด้าน{direction}มี{noun}{offset}",
    )
    return phrases[variant % len(phrases)]


def make_warning_speech(audio_group, level, class_name=None, image_range=None):
    noun = thai_object_noun(audio_group, class_name)
    if level >= 3:
        return f"หยุดก่อน มี{noun}อยู่ใกล้ด้านหน้า"
    if level == 2:
        return f"ด้านหน้ามี{noun}กำลังเข้าใกล้"
    if audio_group == "person" and image_range:
        distance = {
            "far": "ค่อนข้างไกล",
            "medium": "ระยะปานกลาง",
            "near": "ค่อนข้างใกล้",
        }.get(image_range, "")
        if distance:
            return f"ด้านหน้ามีคนอยู่ในแนวเดิน {distance}"
    return f"ด้านหน้ามี{noun}อยู่ในแนวเดิน"


def estimate_person_image_range(box_height, bottom, area_ratio, previous=None):
    """Coarse image-relative range for people; never a metric distance."""
    near = box_height >= 0.40 or area_ratio >= 0.14 or bottom >= 0.90
    far = box_height < 0.15 and area_ratio < 0.015 and bottom < 0.78
    if previous == "far":
        if near:
            return "near"
        return "far" if box_height < 0.18 and area_ratio < 0.022 and bottom < 0.82 else "medium"
    if previous == "near":
        if near:
            return "near"
        return "far" if far else "medium"
    if near:
        return "near"
    if previous == "medium":
        return "far" if far else "medium"
    return "far" if far else "medium"


def make_person_info_speech(side, image_range):
    distance = {
        "far": "ค่อนข้างไกล",
        "medium": "ระยะปานกลาง",
        "near": "ค่อนข้างใกล้",
    }.get(image_range, "")
    if side == "front":
        return f"ด้านหน้ามีคนอยู่{distance}" if distance else "ด้านหน้ามีคนอยู่"
    direction = "ซ้าย" if side == "left" else "ขวา"
    return f"มีคนอยู่ทาง{direction}มือ {distance}".strip()


def all_supported_tts_messages():
    """Build the finite alert vocabulary so one backend is used per session."""
    messages = {
        "ระบบเริ่มทำงาน",
        "ระบบขาดการเชื่อมต่อ",
        "ระบบกลับมาเชื่อมต่อแล้ว",
        "ระวัง มีคนหลายคนอยู่ในแนวทางเดินด้านหน้า",
        "มีที่นั่งหลายจุดอยู่ทางซ้ายมือ",
        "มีที่นั่งหลายจุดอยู่ทางขวามือ",
        "มีที่นั่งหลายจุดอยู่ทั้งสองข้าง",
        "ด้านหน้ามีที่นั่งหลายจุด",
        "มีที่นั่งหลายจุดอยู่ด้านหน้าและทางซ้ายมือ",
        "มีที่นั่งหลายจุดอยู่ด้านหน้าและทางขวามือ",
        "มีที่นั่งหลายจุดอยู่ด้านหน้าและทั้งสองข้าง",
    }
    classes = {
        "person", "car", "chair", "bench", "diningtable",
    }
    for class_name in classes:
        group = get_audio_group(class_name)
        for level in (1, 2, 3):
            messages.add(make_warning_speech(group, level, class_name))
        messages.add(make_info_speech(group, "front", 0.35, 0, class_name))
        if class_name not in {"obstacle"}:
            for side in ("left", "right"):
                for center_y in (0.35, 0.65):
                    messages.add(make_info_speech(group, side, center_y, 0, class_name))
    for side in ("front", "left", "right"):
        for image_range in ("far", "medium", "near"):
            messages.add(make_person_info_speech(side, image_range))
    for image_range in ("far", "medium", "near"):
        messages.add(make_warning_speech("person", 1, "person", image_range))
    # Warm only the planned scene classes. The mapping file also contains
    # spelling aliases; prewarming every alias would delay receiver startup.
    for class_name in (
        "bathroom", "men restroom", "women restroom", "emergency exit",
        "fire exit", "classroom door",
    ):
        messages.add(make_info_speech("obstacle", "front", 0.35, 0, class_name))
        for side in ("left", "right"):
            messages.add(make_info_speech("obstacle", side, 0.35, 0, class_name))
    return tuple(sorted(messages))


def stable_image_side(center_x, previous_side=None):
    """Return a stable image-relative side; central detections remain 'front'."""
    try:
        center_x = min(1.0, max(0.0, float(center_x)))
    except (TypeError, ValueError):
        return "front"
    if previous_side == "left":
        if center_x < SIDE_LEFT_EXIT:
            return "left"
        return "front" if center_x <= SIDE_RIGHT_ENTER else "right"
    if previous_side == "right":
        if center_x > SIDE_RIGHT_EXIT:
            return "right"
        return "front" if center_x >= SIDE_LEFT_ENTER else "left"
    if center_x < SIDE_LEFT_ENTER:
        return "left"
    if center_x > SIDE_RIGHT_ENTER:
        return "right"
    return "front"


def update_object_tracks(detection, objects, now):
    """Greedily associate same-class boxes across nearby frames using IoU/center distance."""
    global next_track_number
    roi = detection.get("roi") if isinstance(detection.get("roi"), dict) else {}
    image_width = float(detection.get("im_w") or detection.get("W") or roi.get("W") or roi.get("w") or 0)
    image_height = float(detection.get("im_h") or detection.get("H") or roi.get("h") or 0)
    if image_width <= 0 or image_height <= 0:
        return [obj for obj in objects if isinstance(obj, dict)]

    expired = [track_id for track_id, track in active_tracks.items()
               if now - track["last_seen"] > TRACK_MAX_GAP_SECONDS]
    for track_id in expired:
        track = active_tracks.pop(track_id)
        area_histories.pop(track_id, None)
        record_decision("track_end", "not_seen", dedupe=False,
                        track_id=track_id, **{"class": track["name"],
                        "duration_seconds": round(track["last_seen"] - track["first_seen"], 2)})

    valid = []
    for original in objects:
        if not isinstance(original, dict):
            continue
        name = str(original.get("name", "unknown")).strip().lower()
        if not is_supported_class_name(name):
            continue
        try:
            x = float(original.get("x") or 0) / image_width
            y = float(original.get("y") or 0) / image_height
            width = float(original.get("w") or 0) / image_width
            height = float(original.get("h") or 0) / image_height
        except (TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        box = (x - width / 2, y - height / 2, x + width / 2, y + height / 2)
        valid.append({"object": original, "name": name,
                      "box": box, "center": (x, y), "area": width * height,
                      "height": height, "bottom": box[3]})

    pairs = []
    for index, item in enumerate(valid):
        for track_id, track in active_tracks.items():
            if item["name"] != track["name"]:
                continue
            gap = now - track["last_seen"]
            if gap > TRACK_MAX_GAP_SECONDS:
                continue
            distance = ((item["center"][0] - track["center"][0]) ** 2 +
                        (item["center"][1] - track["center"][1]) ** 2) ** 0.5
            overlap = box_iou(item["box"], track["box"])
            if overlap >= TRACK_MIN_IOU or distance <= TRACK_MATCH_DISTANCE:
                pairs.append((overlap + max(0.0, 1.0 - distance / TRACK_MATCH_DISTANCE) * 0.15,
                              index, track_id))
    pairs.sort(reverse=True)
    used_detections = set()
    used_tracks = set()
    matches = {}
    for score, index, track_id in pairs:
        if index not in used_detections and track_id not in used_tracks:
            matches[index] = track_id
            used_detections.add(index)
            used_tracks.add(track_id)

    tracked_objects = [obj for obj in objects if isinstance(obj, dict)]
    for index, item in enumerate(valid):
        track_id = matches.get(index)
        if track_id is None:
            track_id = f"T{next_track_number:05d}"
            next_track_number += 1
            active_tracks[track_id] = {
                "name": item["name"], "box": item["box"], "center": item["center"],
                "area": item["area"], "first_seen": now, "last_seen": now,
                "center_x_smooth": item["center"][0], "image_side": "front",
                "height_smooth": item["height"], "bottom_smooth": item["bottom"],
            }
            record_decision("track_start", "new_detection", dedupe=False,
                            track_id=track_id, **{"class": item["name"]},
                            center=[round(item["center"][0], 3), round(item["center"][1], 3)])
        track = active_tracks[track_id]
        previous_area = track["area"]
        smooth_center_x = (
            TRACK_CENTER_EMA_ALPHA * item["center"][0]
            + (1.0 - TRACK_CENTER_EMA_ALPHA) * track.get("center_x_smooth", item["center"][0])
        )
        image_side = stable_image_side(smooth_center_x, track.get("image_side"))
        height_smooth = (
            TRACK_RANGE_EMA_ALPHA * item["height"]
            + (1.0 - TRACK_RANGE_EMA_ALPHA) * track.get("height_smooth", item["height"])
        )
        bottom_smooth = (
            TRACK_RANGE_EMA_ALPHA * item["bottom"]
            + (1.0 - TRACK_RANGE_EMA_ALPHA) * track.get("bottom_smooth", item["bottom"])
        )
        image_range = (
            estimate_person_image_range(height_smooth, bottom_smooth, item["area"], track.get("image_range"))
            if item["name"] == "person" else None
        )
        track.update({"box": item["box"], "center": item["center"],
                      "area": item["area"], "last_seen": now,
                      "center_x_smooth": smooth_center_x, "image_side": image_side,
                      "height_smooth": height_smooth, "bottom_smooth": bottom_smooth,
                      "image_range": image_range})
        tracked = dict(item["object"])
        tracked["_track_id"] = track_id
        tracked["_track_age"] = round(now - track["first_seen"], 2)
        tracked["_center_x_smooth"] = smooth_center_x
        tracked["_image_side"] = image_side
        tracked["_image_range"] = image_range
        tracked["_height_smooth"] = height_smooth
        tracked["_bottom_smooth"] = bottom_smooth
        tracked["_area_growth"] = round(item["area"] / previous_area, 3) if previous_area > 0 else 1.0
        for object_index, original in enumerate(tracked_objects):
            if original is item["object"]:
                tracked_objects[object_index] = tracked
                break
    return tracked_objects


def get_detection_objects(data):
    """Find DeepDetect results in CiRA JSON despite extra/case-varied wrappers."""
    if not isinstance(data, (dict, list)):
        return {}, []

    pending = deque([(data, 0)])
    empty_detection = None
    while pending:
        node, depth = pending.popleft()
        if depth > 10:
            continue
        if isinstance(node, dict):
            for key, value in node.items():
                normalized_key = "".join(char for char in str(key).lower() if char.isalnum())
                if normalized_key == "deepdetect" and isinstance(value, dict):
                    objects = value.get("objects", [])
                    if isinstance(objects, list):
                        if objects:
                            return value, objects
                        if empty_detection is None:
                            empty_detection = value
                if isinstance(value, (dict, list)):
                    pending.append((value, depth + 1))
        elif isinstance(node, list):
            pending.extend((value, depth + 1) for value in node if isinstance(value, (dict, list)))

    if empty_detection is not None:
        return empty_detection, []
    return {}, []


def get_candidates(detection, objects, now, filter_reasons=None):
    """Build object alerts and estimate approach from relative box growth.

    CiRA's x/y values are box centers. Box area is only a rough image-space
    proximity clue; it is not a measured physical distance.
    """
    roi = detection.get("roi") if isinstance(detection.get("roi"), dict) else {}
    image_width = float(detection.get("im_w") or detection.get("W") or roi.get("W") or roi.get("w") or 0)
    image_height = float(detection.get("im_h") or detection.get("H") or roi.get("h") or 0)
    image_area = image_width * image_height
    supported = []
    people_in_path = []
    chairs_seen = []
    filter_reasons = filter_reasons if filter_reasons is not None else []

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        name = str(obj.get("name", "")).strip().lower()
        if not is_supported_class_name(name):
            filter_reasons.append({"class": name or "unknown", "track_id": obj.get("_track_id"),
                                   "reason": "class_not_supported_for_audio"})
            continue
        try:
            x_center = float(obj.get("x") or 0)
            y_center = float(obj.get("y") or 0)
            width = float(obj.get("w") or 0)
            height = float(obj.get("h") or 0)
            confidence = float(obj.get("confidence") or 0)
        except (TypeError, ValueError):
            filter_reasons.append({"class": name, "track_id": obj.get("_track_id"),
                                   "reason": "invalid_box_values"})
            continue
        if width <= 0 or height <= 0 or image_width <= 0 or image_height <= 0:
            filter_reasons.append({"class": name, "track_id": obj.get("_track_id"),
                                   "reason": "box_or_image_dimensions_missing"})
            continue

        center = x_center / image_width
        side_center = center
        track_center = obj.get("_center_x_smooth")
        if track_center is not None:
            try:
                side_center = min(1.0, max(0.0, float(track_center)))
            except (TypeError, ValueError):
                pass
        left_edge = (x_center - width / 2) / image_width
        right_edge = (x_center + width / 2) / image_width
        bottom = (y_center + height / 2) / image_height
        area_ratio = width * height / image_area
        box_height_ratio = height / image_height
        image_range = obj.get("_image_range") if name == "person" else None
        if name == "person" and image_range not in {"far", "medium", "near"}:
            image_range = estimate_person_image_range(box_height_ratio, bottom, area_ratio)
        # Use the object's center and lower contact point. Merely touching the
        # corridor with a wide box is not enough to call it a collision risk.
        center_y = y_center / image_height
        reaches_walk_path = (
            WALK_LANE_LEFT <= center <= WALK_LANE_RIGHT
            and bottom >= WALK_PATH_ENTRY_Y
        )
        lane_overlap_ratio = max(0.0, min(right_edge, WALK_LANE_RIGHT) - max(left_edge, WALK_LANE_LEFT)) / max(right_edge - left_edge, 1e-6)
        # Keep track of reasonably visible people even when they are outside the
        # narrow collision corridor; otherwise a person at the edge of the scene
        # is detected by CiRA but Python stays completely silent.
        if name in SEAT_CLASSES:
            image_side = obj.get("_image_side") or stable_image_side(side_center)
            chairs_seen.append({
                "side": image_side,
                "in_path": reaches_walk_path,
                "lane_overlap": lane_overlap_ratio,
                "front": (y_center / image_height) < 0.75 if image_height > 0 else False,
                "bottom": bottom,
                "track_id": obj.get("_track_id"),
            })
        if not reaches_walk_path:
            audio_group = get_audio_group(name)
            # For furniture and custom named objects outside the collision
            # lane, report left/right from the image center. People/vehicles
            # can still be announced as being ahead across the wider scene area.
            image_side = obj.get("_image_side") or stable_image_side(side_center)
            # Use the stabilized three-zone image position for every class.
            # The wide speech lane is for deciding whether something is visible,
            # not a reason to label clearly lateral objects as "in front".
            side_object = image_side != "front"
            in_forward_lane = (
                not side_object
                and SPEECH_LANE_LEFT <= center <= SPEECH_LANE_RIGHT
                and center_y >= SPEECH_MIN_CENTER_Y
                and area_ratio >= SPEECH_MIN_AREA.get(name, DEFAULT_SPEECH_MIN_AREA)
            )
            if in_forward_lane:
                front_clips = {
                    "person": "มีคนอยู่ด้านหน้า.mp3",
                    "vehicle": "มีรถอยู่ด้านหน้า.mp3",
                    "seat": "ระวัง มีเก้าอี้อยู่ด้านหน้า.mp3",
                    "table": "มีสิ่งกีดขวางอยู่ด้านหน้า.mp3",
                    "obstacle": "มีสิ่งกีดขวางอยู่ด้านหน้า.mp3",
                }
                info_key = f"{name}_front_info"
                info_name = name
                info_side = "front"
                info_filename = front_clips[audio_group]
            elif (name in SEAT_CLASSES or name in TABLE_CLASSES or name in VEHICLE_CLASSES
                  or (name in CLASS_LABELS_TH and name not in PERSON_CLASSES)
                  or any("\u0e00" <= char <= "\u0e7f" for char in name)
                  or (name == "person"
                      and area_ratio >= SPEECH_MIN_AREA.get(name, DEFAULT_SPEECH_MIN_AREA)
                      and center_y >= SPEECH_MIN_CENTER_Y)):
                object_side = image_side
                if object_side == "front":
                    object_side = "front"
                audio_group = get_audio_group(name)
                if audio_group == "seat":
                    info_key = "chair_info"
                    info_filename = f"มีเก้าอี้อยู่ทาง{'ซ้าย' if object_side == 'left' else 'ขวา'}มือ.mp3"
                    info_name = "chair_info"
                elif audio_group == "table":
                    info_key = "table_info"
                    info_filename = f"มีโต๊ะอยู่ทาง{'ซ้าย' if object_side == 'left' else 'ขวา'}มือ.mp3"
                    info_name = "table_info"
                elif audio_group == "vehicle":
                    info_key = "vehicle_info"
                    info_filename = f"มีรถอยู่ทาง{'ซ้าย' if object_side == 'left' else 'ขวา'}มือ.mp3"
                    info_name = "vehicle_info"
                elif audio_group == "person":
                    info_key = "person_info"
                    info_filename = f"มีคนอยู่ทาง{'ซ้าย' if object_side == 'left' else 'ขวา'}มือ.mp3"
                    info_name = "person_info"
                else:
                    info_key = f"{name}_info"
                    info_filename = "มีสิ่งกีดขวางอยู่ด้านหน้า.mp3"
                    info_name = name
                info_side = object_side
            else:
                reason = "outside_speech_lane"
                if SPEECH_LANE_LEFT <= center <= SPEECH_LANE_RIGHT and center_y < SPEECH_MIN_CENTER_Y:
                    reason = "object_center_above_speech_zone"
                elif (SPEECH_LANE_LEFT <= center <= SPEECH_LANE_RIGHT and center_y >= SPEECH_MIN_CENTER_Y
                      and area_ratio < SPEECH_MIN_AREA.get(name, DEFAULT_SPEECH_MIN_AREA)):
                    reason = "box_below_minimum_speech_area"
                elif name == "person" and area_ratio < 0.002:
                    reason = "side_person_box_below_minimum_area"
                elif get_audio_group(name) == "obstacle":
                    reason = "no_side_audio_for_obstacle_class"
                filter_reasons.append({
                    "class": name, "track_id": obj.get("_track_id"), "reason": reason,
                    "center": [round(center, 3), round(center_y, 3)],
                    "area_ratio": round(area_ratio, 5), "bottom": round(bottom, 3),
                })
                continue
            if is_supported_class_name(name):
                supported.append({
                    "key": (info_key, info_side),
                    "name": info_name,
                    "audio_group": audio_group,
                    "model_class": name,
                    "side": info_side,
                    "filename": info_filename,
                    "speech_text": (
                        make_person_info_speech(info_side, image_range)
                        if name == "person"
                        else make_info_speech(audio_group, info_side, center_y, class_name=name)
                    ),
                    "center_y": center_y,
                    "center_x": center,
                    "bbox": [left_edge, (y_center - height / 2) / image_height, right_edge, bottom],
                    "level": 0,
                    "area": area_ratio,
                    "confidence": confidence,
                    "informational": True,
                    "track_id": obj.get("_track_id"),
                    "track_age": obj.get("_track_age", 0.0),
                    "area_growth": obj.get("_area_growth", 1.0),
                    "image_range": image_range,
                    "image_range_method": "person_bbox_height_area_bottom" if name == "person" else None,
                })
            continue

        # We only speak collision warnings for the user's forward walking corridor.
        # Peripheral objects can be handled later by the optional scene narration feature.
        side = "front"
        if name == "person":
            people_in_path.append(obj)

        audio_group = get_audio_group(name)
        filename = (
            "ระวัง มีคนขวางทางด้านหน้า.mp3"
            if audio_group == "person"
            else "ระวัง มีสิ่งกีดขวางขวางทาง.mp3"
        )

        candidate = {
            "key": (name, side),
            "name": name,
            "side": side,
            "base_filename": filename,
            "audio_group": audio_group,
            "model_class": name,
            "level": 1,
            "area": area_ratio,
            "bottom": bottom,
            "confidence": confidence,
            "track_id": obj.get("_track_id"),
            "track_age": obj.get("_track_age", 0.0),
            "area_growth": obj.get("_area_growth", 1.0),
            "image_range": image_range,
            "image_range_method": "person_bbox_height_area_bottom" if name == "person" else None,
            "box_height_ratio": box_height_ratio,
        }
        supported.append(candidate)

    # Merge all non-collision seat information into one stable scene cue.
    # Deduplicate cross-class boxes (for example chair/bench on the same seat)
    # using IoU before deciding whether to say "หลายจุด".
    seat_info = [
        candidate for candidate in supported
        if candidate.get("informational") and candidate.get("audio_group") == "seat"
    ]
    if seat_info:
        unique_seats = []
        for item in sorted(seat_info, key=lambda c: (c["confidence"], c["area"]), reverse=True):
            if any(box_iou(item["bbox"], kept["bbox"]) >= 0.55 for kept in unique_seats):
                continue
            unique_seats.append(item)

        zones = {item["side"] for item in unique_seats}
        has_front = "front" in zones
        has_left = "left" in zones
        has_right = "right" in zones
        if len(unique_seats) == 1:
            only_seat = unique_seats[0]
            seat_speech = make_info_speech(
                "seat", only_seat["side"], only_seat["center_y"],
                class_name=only_seat["model_class"],
            )
        elif has_front and has_left and has_right:
            seat_speech = "มีที่นั่งหลายจุดอยู่ด้านหน้าและทั้งสองข้าง"
        elif has_front and has_left:
            seat_speech = "มีที่นั่งหลายจุดอยู่ด้านหน้าและทางซ้ายมือ"
        elif has_front and has_right:
            seat_speech = "มีที่นั่งหลายจุดอยู่ด้านหน้าและทางขวามือ"
        elif has_front:
            seat_speech = "ด้านหน้ามีที่นั่งหลายจุด"
        elif has_left and has_right:
            seat_speech = "มีที่นั่งหลายจุดอยู่ทั้งสองข้าง"
        elif has_left:
            seat_speech = "มีที่นั่งหลายจุดอยู่ทางซ้ายมือ"
        else:
            seat_speech = "มีที่นั่งหลายจุดอยู่ทางขวามือ"

        strongest_seat = max(unique_seats, key=lambda c: (c["area"], c["confidence"]))
        # MP3 fallback has only single-seat recordings; choose the dominant
        # side's clip. The primary Vachana path speaks the grouped sentence.
        fallback_side = "left" if sum(s["area"] for s in unique_seats if s["side"] == "left") > sum(
            s["area"] for s in unique_seats if s["side"] == "right"
        ) else "right"
        fallback_filename = (
            "ระวัง มีเก้าอี้อยู่ด้านหน้า.mp3" if has_front and not (has_left or has_right)
            else f"มีเก้าอี้อยู่ทาง{'ซ้าย' if fallback_side == 'left' else 'ขวา'}มือ.mp3"
        )
        supported = [candidate for candidate in supported if candidate not in seat_info]
        supported.append({
            "key": ("seat_cluster", "all"),
            "name": "seat_cluster",
            "audio_group": "seat",
            "model_class": "seat_cluster",
            "side": "all",
            "filename": fallback_filename,
            "speech_text": seat_speech,
            "aggregate_speech_text": seat_speech,
            "center_y": sum(s["center_y"] for s in unique_seats) / len(unique_seats),
            "level": 0,
            "area": sum(s["area"] for s in unique_seats),
            "confidence": strongest_seat["confidence"],
            "informational": True,
            "cluster_count": len(unique_seats),
            "track_ids": [s.get("track_id") for s in unique_seats if s.get("track_id")],
        })

    # Keep the strongest box for each class and image region.
    by_key = {}
    for candidate in supported:
        current = by_key.get(candidate["key"])
        if current is None or (candidate["level"], candidate["area"], candidate["confidence"]) > (
            current["level"], current["area"], current["confidence"]
        ):
            by_key[candidate["key"]] = candidate
    candidates = list(by_key.values())
    for candidate in candidates:
        if candidate.get("informational"):
            continue
        history_key = candidate.get("track_id") or candidate["key"]
        history = area_histories.setdefault(history_key, deque())
        while history and now - history[0][0] > APPROACH_WINDOW_SECONDS:
            history.popleft()
        baseline = min((area for _, area in history), default=candidate["area"])
        growing = (
            len(history) >= 3
            and now - history[0][0] >= MIN_APPROACH_EVIDENCE_SECONDS
            and baseline > 0
            and candidate["area"] >= baseline * APPROACH_GROWTH_RATIO
        )
        history.append((now, candidate["area"]))

        # A large box alone cannot establish distance. Reserve the stop prompt
        # for a centered object at the bottom of frame that is also growing.
        close = (
            candidate["side"] == "front"
            and candidate["area"] >= NEAR_AREA_THRESHOLDS.get(
                candidate.get("model_class", candidate["name"]), DEFAULT_NEAR_AREA_THRESHOLD
            )
            and growing
            and candidate.get("bottom", 0.0) >= 0.90
        )
        approaching = candidate["side"] == "front" and growing and candidate["area"] >= 0.025
        candidate["level"] = 3 if close else 2 if approaching else 1
        audio_group = candidate.get("audio_group", get_audio_group(candidate["name"]))
        if candidate["level"] >= 3:
            candidate["filename"] = (
                "หยุดก่อน มีคนอยู่ใกล้ด้านหน้า.mp3"
                if audio_group == "person"
                else "หยุดก่อน มีสิ่งกีดขวางอยู่ใกล้ด้านหน้า.mp3"
            )
        elif candidate["level"] == 2:
            if audio_group == "person":
                candidate["filename"] = "ด้านหน้ามีคน ใกล้เข้ามา.mp3"
            elif audio_group == "vehicle":
                candidate["filename"] = "ด้านหน้ามีรถ ใกล้เข้ามา.mp3"
            else:
                candidate["filename"] = "ระวัง มีสิ่งกีดขวางอยู่ใกล้ด้านหน้า.mp3"
        else:
            candidate["filename"] = candidate.pop("base_filename")
        candidate["speech_text"] = make_warning_speech(
            audio_group, candidate["level"], candidate.get("model_class"),
            candidate.get("image_range"),
        )

    if len(people_in_path) >= 3:
        # Avoid describing every person in a crowd. Keep only a higher-risk warning,
        # otherwise give one calm summary at a limited interval.
        candidates = [c for c in candidates if c["name"] not in {"person", "person_info"} or c["level"] >= 2]
        candidates.append({
            "key": ("person_crowd", "front"),
            "name": "person_crowd",
            "side": "front",
            "filename": "ระวัง มีคนขวางทางด้านหน้า.mp3",
            "speech_text": "ระวัง มีคนหลายคนอยู่ในแนวทางเดินด้านหน้า",
            "level": 1,
            "area": max((c["area"] for c in candidates if c["name"] == "person"), default=0.0),
            "confidence": 1.0,
            "track_ids": [obj.get("_track_id") for obj in people_in_path if obj.get("_track_id")],
        })

    # Update the scene snapshot used by the simple text question interface.
    global latest_chairs
    latest_chairs = chairs_seen

    return candidates


def play_alert_if_detected(data):
    """Speak detections, escalate near/approaching center objects, and repeat periodically."""
    global last_audio_time, audio_error_reported, current_audio_level, active_audio_deadline

    global last_filter_reasons
    detection, objects = get_detection_objects(data)
    now = time.monotonic()
    tracked_objects = update_object_tracks(detection, objects, now)
    filter_reasons = []
    candidates = get_candidates(detection, tracked_objects, now, filter_reasons)
    last_filter_reasons = filter_reasons
    visible_keys = {c["key"] for c in candidates}
    for key, state in tuple(alert_states.items()):
        rearm_seconds = SEAT_REARM_SECONDS if key[0] == "seat_cluster" else REARM_SECONDS
        if key not in visible_keys and now - state["last_seen"] >= rearm_seconds:
            alert_states.pop(key, None)
    for candidate in candidates:
        state = alert_states.setdefault(candidate["key"], {"last_seen": now, "last_spoken": 0.0, "level": 0})
        rearm_seconds = SEAT_REARM_SECONDS if candidate["key"][0] == "seat_cluster" else REARM_SECONDS
        if now - state["last_seen"] >= rearm_seconds:
            state["last_spoken"] = 0.0
            state["level"] = 0
        state["last_seen"] = now

    if not candidates:
        detected_names = sorted({
            str(obj.get("name", "")).strip().lower()
            for obj in objects if isinstance(obj, dict) and obj.get("name")
        })
        if detected_names:
            log_status("ตรวจพบ " + ", ".join(detected_names) + " แต่ไม่มีรายการที่เข้าเงื่อนไขเสียงเตือนในเฟรมนี้")
            record_decision(
                "skip", "no_candidate_passed_filters", detected=detected_names,
                rejected=filter_reasons[:20],
                active_track_ids=sorted(active_tracks),
            )
        else:
            log_status("ได้รับ JSON แล้ว แต่ไม่พบ objects ใน payload.DeepDetect.objects")
            record_decision("skip", "no_objects_in_detection_payload", dedupe=True)
        return

    # Determine which candidates are due. When several classes are present,
    # prioritize risk first and then the least recently spoken one so a person
    # alert cannot starve a car alert (or vice versa).
    due_candidates = []
    for candidate in candidates:
        state = alert_states[candidate["key"]]
        if candidate.get("informational"):
            # Chairs are announced once per sighting. A person can remain in the
            # same side/region while the video continues, so repeat calmly to
            # avoid going silent for the rest of the clip.
            if candidate["side"] == "front":
                # Forward detections repeat at the requested 3-second cadence.
                due = (
                    state["last_spoken"] == 0.0
                    or now - state["last_spoken"] >= NORMAL_REPEAT_SECONDS
                )
            elif candidate["name"] in {"person_info", "vehicle_info"}:
                due = (
                    state["last_spoken"] == 0.0
                    or now - state["last_spoken"] >= PERSON_INFO_REPEAT_SECONDS
                )
            else:
                due = state["last_spoken"] == 0.0
            if due:
                due_candidates.append(candidate)
            continue
        if candidate["level"] >= 3:
            interval = NEAR_REPEAT_SECONDS
        elif candidate["level"] == 2:
            interval = APPROACH_REPEAT_SECONDS
        elif candidate["name"] == "person_crowd":
            interval = CROWD_REPEAT_SECONDS
        elif candidate["name"] == "person":
            # A person in the walking corridor must not become silent forever;
            # repeat at a calm interval while the corridor remains occupied.
            interval = PERSON_REPEAT_SECONDS
        else:
            interval = NORMAL_REPEAT_SECONDS
        escalated = candidate["level"] > state["level"]
        if escalated or now - state["last_spoken"] >= interval:
            due_candidates.append(candidate)
    due_candidates.sort(
        key=lambda c: (
            c["level"],
            -alert_states[c["key"]]["last_spoken"],
            c["area"],
            c["confidence"],
        ),
        reverse=True,
    )
    selection = due_candidates[0] if due_candidates else None
    if selection is None:
        if candidates:
            candidate = candidates[0]
            log_status(
                f"ยังรับข้อมูลต่อเนื่อง: {candidate['name']} อยู่ในฉาก; "
                "ยังไม่ถึงรอบเสียงเตือนซ้ำ"
            )
            record_decision(
                "skip", "repeat_interval_not_elapsed", **{
                    "class": candidate["name"], "track_id": candidate.get("track_id"),
                    "active_candidates": len(candidates),
                }
            )
        return

    if now - last_audio_time < AUDIO_GAP_SECONDS and selection["level"] == 0:
        remaining = AUDIO_GAP_SECONDS - (now - last_audio_time)
        log_status(f"ได้รับวัตถุ {selection['name']} แต่เว้นช่วงเสียงอีก {remaining:.1f} วินาที")
        record_decision(
            "skip", "global_audio_spacing", **{
                "class": selection["name"], "track_id": selection.get("track_id"),
                "remaining_seconds": round(remaining, 2),
            }
        )
        return
    name, side, filename = selection["name"], selection["side"], selection["filename"]
    audio_path = os.path.join(AUDIO_DIR, filename)
    if selection.get("informational"):
        # Keep the wording stable while a TTS clip is being generated. Advance
        # the variant only after playback actually starts, so per-frame CiRA
        # updates cannot create a stream of different cache requests.
        phrase_state = alert_states[selection["key"]]
        speech_text = selection.get("aggregate_speech_text")
        if not speech_text and selection.get("model_class") == "person" and selection.get("image_range"):
            speech_text = selection.get("speech_text")
        if not speech_text:
            speech_text = make_info_speech(
                selection.get("audio_group", get_audio_group(selection["name"])), side,
                selection.get("center_y", 0.0),
                variant=phrase_state.get("speech_variant_index", 0),
                class_name=selection.get("model_class"),
            )
    else:
        speech_text = selection.get("speech_text") or spoken_text_from_filename(filename)
    if not os.path.isfile(audio_path) and not speech_text:
        if selection.get("informational"):
            alert_states[selection["key"]]["last_spoken"] = now
            print(f"ยังไม่มีเสียงบอกเก้าอี้ด้านข้าง สร้างไฟล์นี้เพื่อเปิดใช้: {audio_path}", flush=True)
        else:
            print(f"ไม่พบไฟล์เสียง: {audio_path}", flush=True)
        record_decision(
            "skip", "audio_file_missing", **{
                "class": name, "track_id": selection.get("track_id"), "filename": filename,
            }
        )
        return
    audio_path, audio_backend, speech_text = choose_speech_audio(filename, speech_text)
    if audio_backend != f"{TTS_BACKEND}_cached" and not (
        audio_backend == "mp3_session_fallback" and audio_path and os.path.isfile(audio_path)
    ):
        log_status(f"กำลังเตรียมเสียง {audio_backend}: {speech_text}; จะพูดเมื่อ cache พร้อม")
        record_decision(
            "skip", "tts_pending_wait_for_cache", **{
                "class": name, "model_class": selection.get("model_class"),
                "track_id": selection.get("track_id"), "speech_text": speech_text,
            }
        )
        return

    audible_text = (
        speech_text
        if audio_backend == f"{TTS_BACKEND}_cached"
        else spoken_text_from_filename(filename)
    )

    try:
        import pygame

        with audio_lock:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.set_volume(1.0)
            if pygame.mixer.music.get_busy():
                if active_audio_deadline and now > active_audio_deadline:
                    # SDL can occasionally leave the music channel busy after
                    # a device hiccup. Recover instead of silencing alerts forever.
                    pygame.mixer.music.stop()
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.quit()
                        pygame.mixer.init()
                        pygame.mixer.music.set_volume(1.0)
                    print("กู้คืนช่องเสียงที่ค้างเกินเวลาคลิป แล้วจะลองเล่นเสียงเตือนใหม่", flush=True)
                    record_decision(
                        "recover", "audio_channel_exceeded_clip_deadline", dedupe=False,
                        active_level=current_audio_level, incoming_level=selection["level"],
                    )
                elif selection["level"] >= 2 and selection["level"] > current_audio_level:
                    interrupted_level = current_audio_level
                    pygame.mixer.music.stop()
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.quit()
                        pygame.mixer.init()
                        pygame.mixer.music.set_volume(1.0)
                    print(
                        f"เสียงเตือนเร่งด่วนระดับ {selection['level']} แทรกเสียงระดับ {interrupted_level}",
                        flush=True,
                    )
                    record_decision(
                        "preempt", "higher_priority_alert", dedupe=False,
                        interrupted_level=interrupted_level,
                        incoming_class=name, incoming_track_id=selection.get("track_id"),
                        incoming_filename=filename, incoming_backend=audio_backend,
                    )
                else:
                    # Keep clips serialized at the same/lower severity.
                    log_status("เสียงก่อนหน้ายังเล่นอยู่ รอให้จบก่อนแล้วค่อยเล่นเสียงถัดไป")
                    record_decision(
                        "skip", "audio_channel_busy", **{
                            "class": name, "track_id": selection.get("track_id"),
                            "filename": filename,
                        }
                    )
                    return
            start_audio_clip(pygame, audio_path)
            audio_error_reported = False
            current_audio_level = selection["level"]
            try:
                clip_seconds = pygame.mixer.Sound(audio_path).get_length()
            except Exception:
                clip_seconds = 0.0
            active_audio_deadline = now + max(AUDIO_RECOVERY_GRACE_SECONDS, clip_seconds + 4.0)
        last_audio_time = now
        state = alert_states[selection["key"]]
        state["last_spoken"] = now
        state["level"] = selection["level"]
        if selection.get("informational"):
            state["speech_variant_index"] = state.get("speech_variant_index", 0) + 1
        level_text = {0: "ข้อมูลทั่วไป", 1: "พบวัตถุ", 2: "กำลังเข้าใกล้", 3: "ใกล้มาก/ให้หยุด"}[selection["level"]]
        range_text = selection.get("image_range")
        range_log = f", ระยะภาพโดยประมาณ={range_text}" if range_text else ""
        print(
            f"เล่นเสียง: {audible_text} (backend={audio_backend}, คลาส={name}, "
            f"ตำแหน่งภาพ={side}{range_log}, ระดับ={level_text})",
            flush=True,
        )
        record_decision(
            "play", "candidate_selected_and_audio_started", dedupe=False,
            **{
                "class": name, "track_id": selection.get("track_id"),
                "track_age_seconds": selection.get("track_age"),
                "area_growth_ratio": selection.get("area_growth"),
                "image_range": selection.get("image_range"),
                "image_range_method": selection.get("image_range_method"),
                "side": side, "level": selection["level"], "filename": filename,
                "speech_text": speech_text, "audio_text": audible_text,
                "audio_backend": audio_backend,
                "played_path": audio_path,
                "candidate_count": len(candidates),
                "selection_rule": "highest alert level, then least recently spoken, then box area/confidence",
                "selection_pool": [
                    {"class": item["name"], "track_id": item.get("track_id"),
                     "level": item["level"], "area_ratio": round(item["area"], 5),
                     "confidence": round(item["confidence"], 3), "side": item["side"]}
                    for item in due_candidates
                ],
            }
        )
    except Exception as exc:
        record_decision(
            "error", "audio_playback_exception", dedupe=False,
            **{"class": selection["name"], "track_id": selection.get("track_id"),
               "filename": filename, "audio_backend": audio_backend,
               "exception": f"{type(exc).__name__}: {exc}"}
        )
        if not audio_error_reported:
            print("เล่น MP3 ไม่สำเร็จ; ติดตั้งตัวเล่นด้วยคำสั่ง: python -m pip install pygame", flush=True)
            print(f"รายละเอียด: {exc}", flush=True)
            audio_error_reported = True


def answer_chair_question(question):
    """Answer a simple typed chair-location question using the latest frame."""
    normalized = str(question).strip().lower()
    if not any(word in normalized for word in ("เก้าอี้", "นั่ง", "chair", "sit")):
        print("ตอนนี้ตอบได้เฉพาะคำถามเรื่องตำแหน่งเก้าอี้", flush=True)
        return
    fallback_clip = None
    visible = [chair for chair in latest_chairs]
    if not visible:
        answer = "ตอนนี้ไม่เห็นเก้าอี้ในภาพ"
    else:
        sides = {chair["side"] for chair in visible}
        if sides == {"left", "right"}:
            answer = "เห็นเก้าอี้ทั้งทางซ้ายมือและทางขวามือ"
        elif "left" in sides:
            answer = "เห็นเก้าอี้อยู่ทางซ้ายมือ"
        else:
            answer = "เห็นเก้าอี้อยู่ทางขวามือ"
        if any(chair["front"] for chair in visible):
            answer += " เยื้องไปด้านหน้า"
        if any(chair["in_path"] for chair in visible):
            answer += " มีเก้าอี้บางตัวอยู่ใกล้แนวเดินด้วย"
        # Object detection alone cannot reliably tell whether a seat is occupied.
        answer += " แต่ระบบยังบอกไม่ได้แน่ชัดว่ามีคนนั่งอยู่หรือไม่"
        # Use the closest matching recorded phrase only if TTS is unavailable.
        closest = max(visible, key=lambda chair: chair.get("bottom", 0.0))
        fallback_clip = f"มีเก้าอี้อยู่ทาง{'ซ้าย' if closest['side'] == 'left' else 'ขวา'}มือ.mp3"
    speak_question_answer(answer, fallback_clip)
    print("คำตอบ: " + answer, flush=True)


def speak_question_answer(text, fallback_filename=None, *, expected_stale=None):
    """Speak a manually requested dynamic answer; emergency alerts keep priority."""
    global current_audio_level, last_audio_time, active_audio_deadline, audio_error_reported
    try:
        import pygame

        with audio_lock:
            if pygame.mixer.get_init() and pygame.mixer.music.get_busy() and current_audio_level > 0:
                print("มีเสียงเตือนความเสี่ยงกำลังเล่น จึงไม่แทรกคำตอบ TTS", flush=True)
                return

        cache_path, job = schedule_tts_generation(text)
        speech_path = cache_path if cache_path and os.path.isfile(cache_path) else None
        backend = (
            f"{TTS_BACKEND}_cached" if speech_path
            else "mp3_session_fallback" if TTS_SESSION_MODE == "mp3"
            else f"{TTS_BACKEND}_pending"
        )
        if speech_path is None and job is not None:
            if job["event"].wait(timeout=12.0) and job["result"]:
                speech_path = job["result"]
                backend = TTS_BACKEND
            elif job["exception"] is not None:
                exc = job["exception"]
                print(f"TTS ตอบคำถามไม่พร้อม: {type(exc).__name__}: {exc}", flush=True)
            else:
                print("TTS ตอบคำถามใช้เวลานานเกินไป", flush=True)

        if speech_path is None and fallback_filename and TTS_SESSION_MODE == "mp3":
            candidate_path = os.path.join(AUDIO_DIR, fallback_filename)
            if os.path.isfile(candidate_path):
                speech_path = candidate_path
                backend = "mp3_fallback"
        if speech_path is None and job is None and TTS_SESSION_MODE == "tts":
            cache_path, job = schedule_tts_generation(text, prewarm=True)
        if speech_path is None and job is not None and TTS_SESSION_MODE == "tts":
            if job["event"].wait(timeout=30.0) and job.get("result"):
                speech_path = job["result"]
                backend = TTS_BACKEND
            elif job.get("exception") is not None:
                print(f"สร้างเสียง TTS คำตอบไม่ได้: {job['exception']}", flush=True)
            else:
                print("สร้างเสียง TTS คำตอบใช้เวลานานเกินไป; ไม่แทรกเสียง MP3 คนละโทน", flush=True)
        if speech_path is None:
            print("ไม่มีเสียง TTS ที่สร้างไว้และไม่มี MP3 สำรองสำหรับคำตอบนี้", flush=True)
            return

        if expected_stale is not None and stream_was_stale != expected_stale:
            record_decision(
                "skip", "stream_status_changed_before_audio", dedupe=False,
                speech_text=text, expected_stale=expected_stale,
            )
            return

        wait_until = time.monotonic() + 12.0
        while True:
            with audio_lock:
                busy = pygame.mixer.get_init() and pygame.mixer.music.get_busy()
                active_level = current_audio_level
            if not busy:
                break
            if active_level >= 2:
                print("มีเสียงเตือนเร่งด่วนกำลังเล่น จึงรอให้เสียงเตือนจบก่อน", flush=True)
                return
            if time.monotonic() >= wait_until:
                print("มีเสียงอื่นเล่นต่อเนื่อง จึงยกเลิกเสียงสถานะนี้เพื่อไม่ตัดประโยค", flush=True)
                return
            time.sleep(0.05)

        with audio_lock:
            if expected_stale is not None and stream_was_stale != expected_stale:
                record_decision(
                    "skip", "stream_status_changed_before_audio", dedupe=False,
                    speech_text=text, expected_stale=expected_stale,
                )
                return
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if pygame.mixer.music.get_busy() and current_audio_level > 0:
                print("มีเสียงเตือนความเสี่ยงกำลังเล่น จึงให้เสียงเตือนเล่นต่อก่อน", flush=True)
                return
            if pygame.mixer.music.get_busy():
                print("ช่องเสียงยังไม่ว่าง จึงไม่ตัดประโยคเดิม", flush=True)
                return
            pygame.mixer.music.set_volume(1.0)
            start_audio_clip(pygame, speech_path)
            audio_error_reported = False
            try:
                clip_seconds = pygame.mixer.Sound(speech_path).get_length()
            except Exception:
                clip_seconds = 0.0
            active_audio_deadline = time.monotonic() + max(
                AUDIO_RECOVERY_GRACE_SECONDS, clip_seconds + 4.0
            )
            current_audio_level = 0
            last_audio_time = time.monotonic()
        print(f"เล่นคำตอบด้วยเสียง ({backend}): {text}", flush=True)
        record_decision(
            "play", "spoken_chair_question_answer", dedupe=False,
            speech_text=text, audio_backend=backend, played_path=speech_path,
        )
    except Exception as exc:
        record_decision(
            "error", "chair_answer_speech_failed", dedupe=False,
            speech_text=text, exception=f"{type(exc).__name__}: {exc}",
        )
        print(f"เล่นเสียงคำตอบไม่ได้: {type(exc).__name__}: {exc}", flush=True)


def question_input_loop():
    """Allow typed questions in the same VS Code terminal while CiRA is running."""
    while True:
        try:
            question = input("พิมพ์ถามตำแหน่งเก้าอี้ หรือพิมพ์ 'ทดสอบเสียง' (q เพื่อออก): ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if question.lower() in {"q", "quit", "exit"}:
            return
        if question.lower() in {"ทดสอบเสียง", "test audio", "audio"}:
            run_audio_test()
            continue
        if question:
            answer_chair_question(question)


def run_audio_test():
    """Play a known short clip on demand without interrupting an active alert."""
    global active_audio_deadline, current_audio_level, last_audio_time
    try:
        import pygame
        with audio_lock:
            if pygame.mixer.music.get_busy():
                print("มีเสียงกำลังเล่นอยู่ รอให้จบแล้วพิมพ์ 'ทดสอบเสียง' อีกครั้ง", flush=True)
                return
            filename = "ระบบเริ่มทำงาน.mp3"
            path, backend, spoken_text = choose_speech_audio(filename)
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
            start_audio_clip(pygame, path)
            try:
                duration = pygame.mixer.Sound(path).get_length()
            except Exception:
                duration = 0.0
            active_audio_deadline = time.monotonic() + max(AUDIO_RECOVERY_GRACE_SECONDS, duration + 4.0)
            current_audio_level = 0
            last_audio_time = time.monotonic()
        print(
            f"ส่งเสียงทดสอบเข้าอุปกรณ์เสียงแล้ว: {spoken_text} (backend={backend}, "
            f"อุปกรณ์={audio_device_snapshot or 'ค่าเริ่มต้นของ Windows'}); "
            "ถ้าไม่ได้ยิน ให้ตรวจ Output ของ Windows/หูฟัง",
            flush=True,
        )
        record_decision(
            "play", "manual_audio_output_test_started", dedupe=False,
            audio_backend=backend, played_path=path,
            audio_devices=audio_device_snapshot,
        )
    except Exception as exc:
        print(f"ทดสอบเสียงไม่สำเร็จ: {type(exc).__name__}: {exc}", flush=True)
        record_decision(
            "error", "manual_audio_output_test_failed", dedupe=False,
            exception=f"{type(exc).__name__}: {exc}",
        )


def initialize_audio():
    """Initialize pygame and capture the current Windows output list."""
    global audio_device_snapshot
    import pygame

    if not pygame.mixer.get_init():
        pygame.mixer.init()
    pygame.mixer.music.set_volume(1.0)
    audio_device_snapshot = read_audio_output_devices(pygame)
    print(
        f"อุปกรณ์เสียงที่ pygame มองเห็น: {audio_device_snapshot or 'ใช้ค่าเริ่มต้นของ Windows'}",
        flush=True,
    )


def play_startup_cue():
    """Play the startup cue only after the session's audio backend is chosen."""
    global current_audio_level, last_audio_time, active_audio_deadline, audio_error_reported
    import pygame

    ready_filename = "ระบบเริ่มทำงาน.mp3"
    fallback_path = os.path.join(AUDIO_DIR, ready_filename)
    if not os.path.isfile(fallback_path):
        print(f"ไม่พบเสียงเริ่มทำงาน: {fallback_path}", flush=True)
        return
    ready_path, backend, spoken_text = choose_speech_audio(ready_filename)
    with audio_lock:
        start_audio_clip(pygame, ready_path)
        try:
            clip_seconds = pygame.mixer.Sound(ready_path).get_length()
        except Exception:
            clip_seconds = 0.0
        active_audio_deadline = time.monotonic() + max(AUDIO_RECOVERY_GRACE_SECONDS, clip_seconds + 4.0)
        current_audio_level = 0
        last_audio_time = time.monotonic()
        audio_error_reported = False
    print(
        f"เริ่มเล่นเสียงทดสอบ: {spoken_text} (backend={backend}); "
        f"busy={pygame.mixer.music.get_busy()}, volume={pygame.mixer.music.get_volume():.1f}",
        flush=True,
    )


def enqueue_latest_frame(command, raw, recovered):
    """Keep only the newest pending frame so slow speech never builds a backlog."""
    global frames_dropped
    request = {"command": command, "raw": raw, "recovered": recovered}
    dropped = False
    with frame_enqueue_lock:
        try:
            frame_queue.put_nowait(request)
        except Full:
            try:
                previous = frame_queue.get_nowait()
                frame_queue.task_done()
                request["recovered"] = request["recovered"] or previous["recovered"]
                frames_dropped += 1
                dropped = True
            except Empty:
                pass
            try:
                frame_queue.put_nowait(request)
            except Full:
                # A concurrent consumer/producer won the race; drop this frame
                # rather than blocking CiRA's HTTP request thread.
                frames_dropped += 1
                dropped = True
    if dropped and (frames_dropped == 1 or frames_dropped % 100 == 0):
        print(f"คิวประมวลผลเต็ม; ข้ามเฟรมเก่าเพื่อใช้เฟรมล่าสุด (สะสม {frames_dropped} เฟรม)", flush=True)


def process_frame_request(request):
    raw = request["raw"]
    command = request["command"]
    recovered = request["recovered"]
    try:
        data = json.loads(raw.decode("utf-8")) if raw else None
        if isinstance(data, dict):
            detection, objects = get_detection_objects(data)
            names = [str(obj.get("name", "?")) for obj in objects if isinstance(obj, dict)]
            dimensions = ""
            if detection:
                dimensions = f", ภาพ {detection.get('im_w', '?')}x{detection.get('im_h', '?')}"
            if names:
                log_receive(f"รับ HTTP {command} จาก CiRA: {', '.join(names)}{dimensions}")
            else:
                preview = json.dumps(data, ensure_ascii=False)[:500]
                log_receive(f"รับ HTTP {command} แต่ไม่มีวัตถุในผล DeepDetect; payload={preview}")
        else:
            print("ข้อมูลที่ได้รับไม่ใช่ JSON object: " + raw.decode("utf-8", errors="replace")[:2000], flush=True)
        with frame_lock:
            play_alert_if_detected(data)
        if recovered:
            print("ได้รับเฟรมจาก CiRA อีกครั้ง", flush=True)
            record_decision("recover", "cira_stream_resumed", dedupe=False)
            threading.Thread(
                target=speak_question_answer,
                args=("ระบบกลับมาเชื่อมต่อแล้ว", "ระบบกลับมาเชื่อมต่อแล้ว.mp3"),
                kwargs={"expected_stale": False},
                name="cira-stream-recovered-audio",
                daemon=True,
            ).start()
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"แปลง JSON ไม่สำเร็จ: {exc}", flush=True)
        print(raw.decode("utf-8", errors="replace")[:2000], flush=True)
    except Exception as exc:
        print(f"ผิดพลาดระหว่างประมวลผลข้อมูล: {type(exc).__name__}: {exc}", flush=True)


def frame_processing_worker():
    """Process detections off the HTTP thread; CiRA receives prompt responses."""
    while True:
        request = frame_queue.get()
        try:
            process_frame_request(request)
        finally:
            frame_queue.task_done()


class Receiver(BaseHTTPRequestHandler):
    def do_GET(self):
        response = json.dumps(
            {"ok": True, "message": "Receiver is online; waiting for CiRA CORE PUT/POST data."}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_PUT(self):
        self._receive()

    def do_POST(self):
        self._receive()

    def _receive(self):
        global last_http_time, stream_was_stale
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            self.send_error(400, "JSON request body is required")
            return
        if length > MAX_HTTP_BODY_BYTES:
            self.send_error(413, "JSON request body is too large")
            return
        raw = self.rfile.read(length)
        if len(raw) != length:
            self.send_error(400, "Incomplete request body")
            return
        with stream_state_lock:
            recovered = stream_was_stale
            last_http_time = time.monotonic()
            stream_was_stale = False
        enqueue_latest_frame(self.command, raw, recovered)
        response = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    address = ("127.0.0.1", 8765)
    # Only report a stalled stream after CiRA has sent at least one request.
    last_http_time = 0.0
    print(f"ไฟล์บันทึกเหตุผล: {DECISION_LOG_PATH}", flush=True)
    print(
        f"ผู้ให้บริการ TTS: Vachana Thai ({TTS_MODEL_ID}), voice={TTS_VOICE}, speed={TTS_SPEED:.2f}x; "
        "ประมวลผลในเครื่องด้วย CPU ไม่ใช้ API key",
        flush=True,
    )
    try:
        initialize_audio()
    except Exception as exc:
        print(f"เริ่มระบบเสียงไม่สำเร็จ: {type(exc).__name__}: {exc}", flush=True)
    try:
        prewarm_tts_cache()
    except Exception as exc:
        print(f"เริ่มเตรียม cache เสียง TTS ไม่สำเร็จ; ใช้ MP3 สำรอง: {exc}", flush=True)
        TTS_SESSION_MODE = "mp3"
    try:
        play_startup_cue()
    except Exception as exc:
        print(f"เล่นเสียงยืนยันเริ่มระบบไม่ได้: {type(exc).__name__}: {exc}", flush=True)
    record_decision("session_start", "receiver_started", dedupe=False,
                    tracker="same_class_iou_and_center_distance",
                    track_gap_seconds=TRACK_MAX_GAP_SECONDS,
                    tts_session_mode=TTS_SESSION_MODE, tts_voice=TTS_VOICE,
                    tts_speed=TTS_SPEED)
    print(f"กำลังรอข้อมูลจาก CiRA CORE ที่ http://{address[0]}:{address[1]}/", flush=True)
    print("HTTP ตอบรับทันที; ประมวลผลเฟรมในคิวล่าสุดเพื่อไม่ให้ TTS บล็อก CiRA", flush=True)
    print("พิมพ์คำถามเรื่องเก้าอี้ใน Terminal ได้ (เช่น อยากนั่ง มีเก้าอี้ตรงไหน); หยุดด้วย Ctrl+C", flush=True)
    threading.Thread(target=audio_channel_watchdog, daemon=True).start()
    threading.Thread(target=question_input_loop, daemon=True).start()
    threading.Thread(target=frame_processing_worker, name="cira-frame-worker", daemon=True).start()

    def stream_watchdog():
        """Report a stopped CiRA stream without blocking HTTP processing."""
        global stream_was_stale
        while True:
            time.sleep(2.0)
            now = time.monotonic()
            with stream_state_lock:
                became_stale = (
                    last_http_time > 0
                    and now - last_http_time > STREAM_STALE_SECONDS
                    and not stream_was_stale
                )
                if became_stale:
                    stream_was_stale = True
            if became_stale:
                print(f"ไม่ได้รับเฟรมจาก CiRA ต่อเนื่อง {STREAM_STALE_SECONDS:.0f} วินาที; ตรวจว่า VideoFile ยังเล่นและ RestPutJson ยังส่งข้อมูล", flush=True)
                record_decision("error", "cira_stream_stale", dedupe=False,
                                stale_seconds=STREAM_STALE_SECONDS)
                threading.Thread(
                    target=speak_question_answer,
                    args=("ระบบขาดการเชื่อมต่อ", "ระบบขาดการเชื่อมต่อ.mp3"),
                    kwargs={"expected_stale": True},
                    name="cira-stream-stale-audio",
                    daemon=True,
                ).start()

    threading.Thread(target=stream_watchdog, daemon=True).start()
    from http.server import ThreadingHTTPServer
    ThreadingHTTPServer(address, Receiver).serve_forever()
