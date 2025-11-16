"""
ISL Assistant — Final upgraded version

Features:
- Manual mic selection (no auto-select)
- Auto GIF detection from ISL_Gifs/
- mapping.json support (optional)
- Fuzzy matching via rapidfuzz (medium threshold ~80)
- Endpoint detection (auto start/stop on voice)
- Background recognition threads (no UI blocking)
- Mic tester (record & test) without auto-scan overhead
- Lowered waveform redraw frequency and performance improvements
- Clean fallback to letters (letters/<a>.jpg ...)

Save as isl_app_final.py and run with:
pip install sounddevice numpy matplotlib pillow speechrecognition rapidfuzz
python isl_app_final.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
import sounddevice as sd
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from PIL import Image, ImageTk
import speech_recognition as sr
import threading
import queue
import time
import os
import json
from itertools import count
from rapidfuzz import process, fuzz

# -------------------------
# Configurable parameters
# -------------------------
SAMPLE_RATE = 16000
BLOCK_DURATION = 0.06   # seconds per block (slightly larger reduces UI churn)
BLOCKSIZE = int(SAMPLE_RATE * BLOCK_DURATION)

ISL_GIF_FOLDER = "ISL_Gifs"
LETTERS_FOLDER = "letters"
MAPPING_JSON = "mapping.json"

# Endpoint detection tuning (you can adjust via UI in the app)
RMS_SPEECH_THRESHOLD_DEFAULT = 750.0
SILENCE_TIMEOUT_DEFAULT = 0.8
MIN_SPEECH_DURATION_DEFAULT = 0.35

# Fuzzy threshold (medium)
FUZZY_THRESHOLD = 80  # percent (you chose medium)

# -------------------------
# Utility helpers
# -------------------------

def normalize_text(t: str) -> str:
    """Normalize recognized text to canonical lowercase with single spaces."""
    if t is None:
        return ""
    t = str(t).lower().strip()
    t = " ".join(t.split())
    return t

def load_mapping():
    if not os.path.exists(MAPPING_JSON):
        return {}
    try:
        with open(MAPPING_JSON, "r", encoding="utf-8") as f:
            m = json.load(f)
            # normalize keys & values
            return {normalize_text(k): normalize_text(v) for k, v in m.items()}
    except Exception:
        return {}

# -------------------------
# GIF Player (non-blocking)
# -------------------------
class GIFPlayer(tk.Label):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.frames = []
        self.index = 0
        self.delay = 80
        self.job = None
        self.current_ph = None

    def load(self, path):
        # load in main thread; caller should call this via event loop
        try:
            if not os.path.exists(path):
                self.unload()
                self.config(text=f"(GIF not found)\n{os.path.basename(path)}", image="", compound="center")
                return
            img = Image.open(path)
            frames = []
            try:
                for i in count(1):
                    frames.append(ImageTk.PhotoImage(img.copy()))
                    img.seek(i)
            except EOFError:
                pass
            if not frames:
                # static image fallback
                img2 = Image.open(path)
                frames = [ImageTk.PhotoImage(img2)]
            self.frames = frames
            self.index = 0
            self.delay = img.info.get("duration", 80) if hasattr(img, "info") else 80
            self.config(text="")
            self._play()
        except Exception as e:
            self.unload()
            self.config(text=f"(GIF load error)\n{e}", image="")

    def _play(self):
        if not self.frames:
            return
        # set current frame
        ph = self.frames[self.index]
        self.config(image=ph)
        self.current_ph = ph
        self.index = (self.index + 1) % len(self.frames)
        if self.job:
            try:
                self.after_cancel(self.job)
            except:
                pass
        self.job = self.after(self.delay if self.delay>0 else 100, self._play)

    def unload(self):
        if self.job:
            try:
                self.after_cancel(self.job)
            except:
                pass
            self.job = None
        self.config(image="", text="")
        self.frames = []
        self.index = 0
        self.current_ph = None

# -------------------------
# Main application
# -------------------------
class ISLApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ISL Assistant — Final")
        self.root.geometry("1180x720")

        # audio fields
        self.stream = None
        self.audio_q = queue.Queue(maxsize=400)  # from callback to main
        self.buffer = np.zeros(0, dtype="int16")
        self.running = False

        # endpoint state
        self.speech_active = False
        self.speech_start_time = None
        self.last_voice_time = None

        # recognition queue
        self.recognizing = False

        # config
        self.mapping = load_mapping()
        self.available_gifs = {}  # map normalized name -> path
        self.scan_gifs()

        self.rms_threshold = RMS_SPEECH_THRESHOLD_DEFAULT
        self.silence_timeout = SILENCE_TIMEOUT_DEFAULT
        self.min_speech = MIN_SPEECH_DURATION_DEFAULT

        # UI + persistent waveform
        self._build_ui()
        self._create_waveform()

        # schedule UI update
        self.root.after(int(BLOCK_DURATION*1000), self._ui_update)

        # cleanup handler
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # -------------------------
    # GIF scanning & fuzzy matching
    # -------------------------
    
        

        

    def scan_gifs(self):
        """Scan ISL_GIF_FOLDER for *.gif and create map."""
        self.available_gifs = {}
        if not os.path.isdir(ISL_GIF_FOLDER):
            return
        for fn in os.listdir(ISL_GIF_FOLDER):
            if fn.lower().endswith(".gif"):
                name = fn[:-4]
                key = normalize_text(name)
                self.available_gifs[key] = os.path.join(ISL_GIF_FOLDER, fn)

    def _best_gif_for_text(self, text):
        """
        Resolve text -> gif:
        1. mapping.json (exact)
        2. exact filename match
        3. fuzzy match against available_gifs keys with FUZZY_THRESHOLD
        Returns path or None.
        """
        if not text:
            return None
        t = normalize_text(text)
        # mapping
        if t in self.mapping:
            mapped = self.mapping[t]
            # mapped might be canonical name, check existence
            if mapped in self.available_gifs:
                return self.available_gifs[mapped]
        # direct exact
        if t in self.available_gifs:
            return self.available_gifs[t]
        # fuzzy match
        keys = list(self.available_gifs.keys())
        if not keys:
            return None
        # use rapidfuzz process.extractOne
        best = process.extractOne(t, keys, scorer=fuzz.ratio)
        if best:
            matched_key, score, _ = best
            if score >= FUZZY_THRESHOLD:
                return self.available_gifs.get(matched_key)
        return None

    # -------------------------
    # UI
    # -------------------------
    def _build_ui(self):
        container = tk.Frame(self.root)
        container.pack(fill="both", expand=True)

        sidebar = tk.Frame(container, width=220, bg="#222")
        sidebar.pack(side="left", fill="y")

        # Buttons
        btn_live = tk.Button(sidebar, text="Live Voice", bg="#333", fg="white", command=self._show_live)
        btn_live.pack(fill="x", padx=10, pady=8)
        btn_tester = tk.Button(sidebar, text="Mic Tester", bg="#333", fg="white", command=self._show_tester)
        btn_tester.pack(fill="x", padx=10, pady=4)
        btn_config = tk.Button(sidebar, text="Settings", bg="#333", fg="white", command=self._show_settings)
        btn_config.pack(fill="x", padx=10, pady=4)
        btn_refresh = tk.Button(sidebar, text="Rescan GIFs", bg="#333", fg="white", command=self._rescan_gifs)
        btn_refresh.pack(fill="x", padx=10, pady=4)
        btn_exit = tk.Button(sidebar, text="Exit", bg="#333", fg="white", command=self._on_close)
        btn_exit.pack(fill="x", padx=10, pady=4)

        # main area frames (persistent)
        self.main = tk.Frame(container, bg="white")
        self.main.pack(side="right", fill="both", expand=True)

        self.live_frame = tk.Frame(self.main, bg="white")
        self.tester_frame = tk.Frame(self.main, bg="white")
        self.settings_frame = tk.Frame(self.main, bg="white")
       

                
        for f in (self.live_frame, self.tester_frame, self.settings_frame):
            f.place(relx=0, rely=0, relwidth=1, relheight=1)

        # build live frame
        self._build_live_frame()
        # build tester frame
        self._build_tester_frame()
        # build settings
        self._build_settings_frame()

        self._show_live()

    def _build_live_frame(self):
        # ======================================================
        # TOP HEADER — LOGO + TEXT (Live Tab Only)
        # ======================================================
        header_frame = tk.Frame(self.live_frame, bg="white")
        header_frame.pack(fill="x", pady=(10, 20))

        # LEFT: Logo image
        try:
            img = Image.open("header.png")       # ensure this file exists
            img = img.resize((300, 100), Image.Resampling.LANCZOS)
            self.header_logo = ImageTk.PhotoImage(img)

            tk.Label(header_frame, image=self.header_logo, bg="white").pack(
                side="left", padx=20
            )
        except Exception as e:
            tk.Label(
                header_frame,
                text=f"Header image failed: {e}",
                fg="red",
                bg="white"
            ).pack(side="left", padx=20)

        # RIGHT: Title + Subtitle
        title_box = tk.Frame(header_frame, bg="white")
        title_box.pack(side="left", padx=10)

        tk.Label(
            title_box,
            text="Voice2Sign",
            font=("Arial", 34, "bold"),
            fg="#222",
            bg="white"
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text="Amplifying Silent Voices",
            font=("Arial", 18),
            fg="#555",
            bg="white"
        ).pack(anchor="w")


        # ---------------------------
        # GIF DISPLAY AREA
        # ---------------------------
        gif_area = tk.Frame(self.live_frame, height=360, bg="white")
        gif_area.pack(fill="x", padx=12, pady=6)

        self.gif_player = GIFPlayer(gif_area)
        self.gif_player.pack(expand=True)

        # ---------------------------
        # RECOGNIZED TEXT DISPLAY
        # ---------------------------
        self.text_var = tk.StringVar(value="Waiting for speech...")
        self.text_label = tk.Label(
            self.live_frame,
            textvariable=self.text_var,
            font=("Arial", 14),
            bg="white",
            fg="blue"
        )
        self.text_label.pack(pady=6)

        # ---------------------------
        # BOTTOM AREA (WAVEFORM + MIC STATUS)
        # ---------------------------
        bottom = tk.Frame(self.live_frame, bg="white")
        bottom.pack(fill="both", expand=True, padx=8, pady=6)

        # Waveform container
        self.wave_container = tk.Frame(bottom, bg="white")
        self.wave_container.pack(side="left", fill="both", expand=True)

        # Right panel (mic status)
        right = tk.Frame(bottom, width=260, bg="white")
        right.pack(side="right", fill="y", padx=8)

        tk.Label(right, text="Mic (choose in Tester)", bg="white").pack(anchor="nw")

        # Status text
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(right, textvariable=self.status_var, bg="white", fg="green").pack(anchor="nw", pady=(4, 8))

        # RMS meter label
        tk.Label(right, text="Mic Level (RMS)", bg="white").pack(anchor="nw")

        # RMS meter bar
        self.rms_var = tk.DoubleVar()
        self.meter = ttk.Progressbar(
            right,
            orient="horizontal",
            length=200,
            mode="determinate",
            maximum=1.0,
            variable=self.rms_var
        )
        self.meter.pack(pady=4)

        # RMS numeric display
        self.rms_label = tk.Label(right, text="0.0", bg="white")
        self.rms_label.pack(anchor="nw")

        # ---------------------------
        # START / STOP BUTTONS
        # ---------------------------
        btns = tk.Frame(right, bg="white")
        btns.pack(pady=10)

        self.btn_start = tk.Button(btns, text="Start Listening", command=self.start_stream)
        self.btn_start.pack(side="left", padx=6)

        self.btn_stop = tk.Button(btns, text="Stop", command=self.stop_stream, state="disabled")
        self.btn_stop.pack(side="left", padx=6)

    def _build_tester_frame(self):
        tk.Label(self.tester_frame, text="Mic Tester & Selection", font=("Arial", 16), bg="white").pack(pady=6)
        fr = tk.Frame(self.tester_frame, bg="white")
        fr.pack(fill="x", padx=8, pady=4)
        tk.Label(fr, text="Input Device:", bg="white").pack(side="left")
        devices = self._list_input_devices()
        self.dev_combo = ttk.Combobox(fr, values=devices, width=70)
        self.dev_combo.pack(side="left", padx=6)
        if devices:
            self.dev_combo.set(devices[0])
        tk.Button(fr, text="Refresh", command=self._refresh_devices).pack(side="left", padx=4)

        # Manual selection is used by Live mode when starting stream
        # Tester tools
        tk.Button(self.tester_frame, text="Record 4s & Recognize", command=self._tester_record).pack(pady=8)
        tk.Button(self.tester_frame, text="Choose mapping.json", command=self._choose_mapping_file).pack()
        self.tester_log = tk.Text(self.tester_frame, height=8)
        self.tester_log.pack(fill="x", padx=8, pady=6)
        self._log_tester("Ready. Choose device and press Start in Live tab to use selected mic.")

    def _build_settings_frame(self):
        tk.Label(self.settings_frame, text="Settings", font=("Arial", 16), bg="white").pack(pady=6)
        fr = tk.Frame(self.settings_frame, bg="white")
        fr.pack(padx=8, pady=6, fill="x")
        tk.Label(fr, text="RMS speech threshold:", bg="white").grid(row=0, column=0, sticky="w")
        self.s_rms = tk.DoubleVar(value=self.rms_threshold)
        tk.Entry(fr, textvariable=self.s_rms).grid(row=0, column=1, sticky="w")
        tk.Label(fr, text="Silence timeout (s):", bg="white").grid(row=1, column=0, sticky="w")
        self.s_silence = tk.DoubleVar(value=self.silence_timeout)
        tk.Entry(fr, textvariable=self.s_silence).grid(row=1, column=1, sticky="w")
        tk.Label(fr, text="Min speech duration (s):", bg="white").grid(row=2, column=0, sticky="w")
        self.s_min = tk.DoubleVar(value=self.min_speech)
        tk.Entry(fr, textvariable=self.s_min).grid(row=2, column=1, sticky="w")
        tk.Button(fr, text="Save settings", command=self._save_settings).grid(row=3, column=0, columnspan=2, pady=8)

    def _show_live(self):
        self.live_frame.tkraise()

    def _show_tester(self):
        self.tester_frame.tkraise()

    def _show_settings(self):
        self.settings_frame.tkraise()

    def _rescan_gifs(self):
        self.scan_gifs()
        messagebox.showinfo("Rescan", f"Found {len(self.available_gifs)} GIFs.")

    # -------------------------
    # Device helpers
    # -------------------------
    def _list_input_devices(self):
        out = []
        try:
            devs = sd.query_devices()
            for i, d in enumerate(devs):
                if d.get("max_input_channels", 0) > 0:
                    out.append(f"{i}: {d['name']} (ch={d['max_input_channels']})")
        except Exception:
            out = []
        return out

    def _refresh_devices(self):
        vals = self._list_input_devices()
        self.dev_combo['values'] = vals
        if vals:
            self.dev_combo.set(vals[0])
        self._log_tester("Device list refreshed.")

    def _choose_mapping_file(self):
        path = filedialog.askopenfilename(title="Select mapping.json", filetypes=[("JSON","*.json")])
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    m = json.load(f)
                # write to local mapping.json
                with open(MAPPING_JSON, "w", encoding="utf-8") as f:
                    json.dump(m, f, ensure_ascii=False, indent=2)
                self.mapping = load_mapping()
                messagebox.showinfo("Mapping loaded", "mapping.json saved and loaded.")
            except Exception as e:
                messagebox.showerror("Error", f"Could not load mapping: {e}")

    def _log_tester(self, *parts):
        try:
            ts = time.strftime("%H:%M:%S")
            self.tester_log.insert("end", f"[{ts}] " + " ".join(map(str, parts)) + "\n")
            self.tester_log.see("end")
        except Exception:
            pass

    # -------------------------
    # Waveform canvas (created once)
    # -------------------------
    def _create_waveform(self):
        self.fig, self.ax = plt.subplots(figsize=(8.6, 2.2))
        self.ax.set_ylim(-32768, 32767)
        self.ax.set_xlim(0, int(SAMPLE_RATE * 0.5))
        self.line, = self.ax.plot([], [])
        self.ax.set_yticks([])

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.wave_container)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)

    # -------------------------
    # Stream management (manual device selection)
    # -------------------------
    def start_stream(self):
        if self.running:
            return
        # determine selected device from combobox
        dev = None
        try:
            sel = self.dev_combo.get()
            if sel:
                dev = int(sel.split(":")[0])
        except Exception:
            dev = None

        if dev is None:
            messagebox.showerror("No device", "Please select input device in Mic Tester tab.")
            return

        # prepare
        self.buffer = np.zeros(0, dtype="int16")
        self.audio_q = queue.Queue(maxsize=400)
        self.speech_active = False
        self.speech_start_time = None
        self.last_voice_time = None
        self.running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_var.set("Listening")

        def callback(indata, frames, time_info, status):
            if status:
                self._log_tester("Stream status:", status)
            try:
                self.audio_q.put_nowait(indata[:, 0].copy())
            except queue.Full:
                # drop blocks if overwhelmed
                pass

        # close existing
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        except:
            pass

        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, blocksize=BLOCKSIZE,
                                     dtype="int16", channels=1, callback=callback, device=dev)
        try:
            self.stream.start()
            self._log_tester(f"Stream started on device {dev}.")
        except Exception as e:
            messagebox.showerror("Stream error", f"Could not start stream: {e}")
            self.running = False
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")
            self.status_var.set("Ready")
            return

    def stop_stream(self):
        if not self.running:
            return
        self.running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status_var.set("Stopped")
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
        except:
            pass
        self._log_tester("Stream stopped.")

    # -------------------------
    # Tester record (4s)
    # -------------------------
    def _tester_record(self):
        sel = self.dev_combo.get()
        dev = None
        if sel:
            try:
                dev = int(sel.split(":")[0])
            except:
                dev = None
        if dev is None:
            messagebox.showwarning("No device", "Select device first.")
            return
        self._log_tester("Recording 4s...")
        try:
            data = sd.rec(int(4*SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=dev)
            sd.wait()
            rms = np.sqrt(np.mean(data.astype(np.float32)**2))
            self._log_tester(f"RMS={rms:.1f}")
            audio = sr.AudioData(data.flatten().tobytes(), SAMPLE_RATE, 2)
            r = sr.Recognizer()
            try:
                txt = r.recognize_google(audio)
                self._log_tester("Recognized:", txt)
                messagebox.showinfo("Recognized", txt)
            except sr.UnknownValueError:
                self._log_tester("Could not understand.")
                messagebox.showwarning("Recognize", "Could not understand.")
            except sr.RequestError as e:
                self._log_tester("API error:", e)
                messagebox.showerror("Recognize API", str(e))
        except Exception as e:
            self._log_tester("Record error:", e)

    # -------------------------
    # UI update: process audio queue & endpoint detection
    # -------------------------
    def _ui_update(self):
        # process incoming audio blocks
        got = False
        blocks = []
        while True:
            try:
                b = self.audio_q.get_nowait()
                blocks.append(b)
                got = True
            except queue.Empty:
                break

        if got:
            block = np.concatenate(blocks)
            self.buffer = np.concatenate([self.buffer, block])
            # cap
            if len(self.buffer) > SAMPLE_RATE * 5:
                self.buffer = self.buffer[-SAMPLE_RATE*5:]

            # RMS on short window
            win = self.buffer[-int(0.12*SAMPLE_RATE):] if len(self.buffer) >= int(0.12*SAMPLE_RATE) else self.buffer
            rms = np.sqrt(np.mean(win.astype(np.float32)**2)) if len(win) > 0 else 0.0

            # update meter (normalized)
            self.rms_var.set(min(1.0, rms / 10000.0))
            self.rms_label.config(text=f"{rms:.1f}")

            # waveform update (light)
            try:
                show_len = int(0.5*SAMPLE_RATE)
                w = self.buffer[-show_len:] if len(self.buffer) >= show_len else np.concatenate([np.zeros(show_len - len(self.buffer), dtype='int16'), self.buffer])
                self.line.set_data(np.arange(len(w)), w)
                self.ax.set_xlim(0, len(w))
                self.canvas.draw_idle()
            except Exception:
                pass

            # endpoint logic
            now = time.time()
            if rms >= self.rms_threshold:
                if not self.speech_active:
                    self.speech_active = True
                    self.speech_start_time = now
                    self._set_status("Speech detected")
                self.last_voice_time = now
            else:
                if self.speech_active and self.last_voice_time:
                    if (now - self.last_voice_time) >= self.silence_timeout:
                        duration = (self.last_voice_time - self.speech_start_time) if (self.speech_start_time and self.last_voice_time) else 0
                        if duration >= self.min_speech:
                            # get chunk (last up to 3s)
                            chunk = self.buffer[-int(min(len(self.buffer), SAMPLE_RATE*3)) :].copy()
                            self.buffer = np.zeros(0, dtype='int16')
                            self.speech_active = False
                            self.speech_start_time = None
                            self.last_voice_time = None
                            self._set_status("Processing...")
                            self._enqueue_recognition(chunk)
                        else:
                            # too short
                            self.speech_active = False
                            self.speech_start_time = None
                            self.last_voice_time = None
                            self._set_status("Ready")
        # schedule next
        self.root.after(int(BLOCK_DURATION*1000), self._ui_update)

    def _set_status(self, s):
        self.status_var.set(s)

    # -------------------------
    # Recognition pipeline
    # -------------------------
    def _enqueue_recognition(self, chunk):
        # run STT in background thread
        threading.Thread(target=self._recognize_worker, args=(chunk,), daemon=True).start()

    def _recognize_worker(self, chunk):
        try:
            audio_data = sr.AudioData(chunk.tobytes(), SAMPLE_RATE, 2)
            r = sr.Recognizer()
            try:
                text = r.recognize_google(audio_data)
            except sr.UnknownValueError:
                text = ""
            except sr.RequestError as e:
                self._call_in_main_thread(self._log_tester, "Recognition API error:", e)
                self._call_in_main_thread(self._set_status, "Ready")
                return
            if text:
                clean = normalize_text(text)
                self._call_in_main_thread(self._on_recognition_result, clean)
            else:
                self._call_in_main_thread(self._set_status, "Ready")
        except Exception as e:
            self._call_in_main_thread(self._log_tester, "Recognition worker error:", e)
            self._call_in_main_thread(self._set_status, "Ready")

    def _call_in_main_thread(self, fn, *args, **kwargs):
        self.root.after(0, lambda: fn(*args, **kwargs))

    def _on_recognition_result(self, text):
        self.text_var.set(text if text else "(could not understand)")
        # find gif
        gif_path = self._best_gif_for_text(text)
        if gif_path:
            # load gif in main thread (but do it via after to avoid blocking)
            self._call_in_main_thread(self.gif_player.load, gif_path)
            self._call_in_main_thread(self._set_status, f"Showing: {os.path.basename(gif_path)}")
        else:
            # fallback to letters
            self._call_in_main_thread(self._set_status, "Showing letters")
            threading.Thread(target=self._display_letters_thread, args=(text,), daemon=True).start()

    def _display_letters_thread(self, text):
        # display letters sequentially (0.45s each)
        for ch in text:
            if ch in "abcdefghijklmnopqrstuvwxyz":
                path = os.path.join(LETTERS_FOLDER, f"{ch}.jpg")
                if not os.path.exists(path):
                    continue
                try:
                    img = Image.open(path)
                    ph = ImageTk.PhotoImage(img.resize((320, 320)))
                    # set image on main thread
                    self._call_in_main_thread(self._set_gif_image, ph)
                    time.sleep(0.45)
                except Exception:
                    continue
        self._call_in_main_thread(self._set_status, "Ready")

    def _set_gif_image(self, ph):
        self.gif_player.unload()
        self.gif_player.config(image=ph)
        self.gif_player.image = ph

    # -------------------------
    # Settings
    # -------------------------
    def _save_settings(self):
        try:
            self.rms_threshold = float(self.s_rms.get())
            self.silence_timeout = float(self.s_silence.get())
            self.min_speech = float(self.s_min.get())
            messagebox.showinfo("Settings", "Saved.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save settings: {e}")

    # -------------------------
    # Cleanup & exit
    # -------------------------
    def _on_close(self):
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        except:
            pass
        try:
            self.root.quit()
        except:
            os._exit(0)

# -------------------------
# Run app
# -------------------------
def main():
    root = tk.Tk()
    app = ISLApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
