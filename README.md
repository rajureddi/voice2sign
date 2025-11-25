

---

# 🧏‍♂️ Voice2Sign – AI-Powered Indian Sign Language Translator

### **Amplifying Silent Voices**

Voice2Sign is a real-time **Indian Sign Language (ISL) translation system** that converts spoken voice into animated ISL signs.
It is designed to help bridge communication between hearing individuals and people with hearing impairments.



* 🎤 Auto voice endpoint detection
* 🖼️ Real-time GIF-based ISL sign rendering
* 🔠 Alphabet fallback for unknown words
* 🔍 Fuzzy matching & mapping support
* 🔊 Manual microphone selection
* 📈 Live waveform visualization
* 🛠️ Mic tester & configuration panel
* 📁 Automatic GIF scanning
* ⚡ Smooth performance (no UI lag)

---

# 🚀 Features

### ✔ **1. Voice-to-ISL Translation**

* Uses real-time speech recognition
* Converts spoken sentences into normalized text
* Matches text to available ISL GIF signs
* If a sign exists → it plays the animated GIF
* If not → displays each letter as handshape images

---
## DEMO VIDEO

https://github.com/user-attachments/assets/1eab5f8c-80d0-498c-9ee5-3cdb1a2eb191
---
### ✔ **2. Auto Endpoint Detection**

No need to press but


tons while speaking.

* Detects when the user starts talking
* Detects silence
* Automatically triggers recognition
* Processes speech only once (no repeated triggers)

---

### ✔ **3. ISL GIF-Based Sign Display**

The system loads ISL signs from:

```
ISL_Gifs/
    hello.gif
    good morning.gif
    please wait for sometime.gif
    ...
```

* Auto scans all GIFs on startup
* Supports any number of custom signs
* Plays animated GIFs smoothly (non-blocking)

---

### ✔ **4. Fallback to Alphabet Signs**

If the system cannot find any matching sign, it displays:

```
letters/
    a.jpg
    b.jpg
    c.jpg
    ...
```

One letter at a time.

---

### ✔ **5. Fuzzy Matching & mapping.json**

Handles small spelling mistakes and variations automatically.

Supports:

* `"good morning"` ↔ `"goodmorning"`
* `"pls wait"` ↔ `"please wait for sometime"`
* `"whats your name"` ↔ `"what is your name"`

You can manually define mappings in:

```
mapping.json
```

Example:

```json
{
  "goodmorning": "good morning",
  "pls wait": "please wait for sometime"
}
```

---

### ✔ **6. Manual Microphone Selection + Mic Tester**

* Choose your input device manually
* Test microphone with a 4-second recording
* View RMS levels and waveform in real-time

---

### ✔ **7. Settings Panel**

You can fine-tune:

* RMS speech threshold
* Silence timeout
* Minimum speech duration

---

# 🎯 Project Structure

```
.
├── isl_app_final.py       # Main Application
├── ISL_Gifs/              # GIF ISL sign animations
│   ├── hello.gif
│   ├── good morning.gif
│   └── ...
├── letters/               # Alphabet fallback images
│   ├── a.jpg
│   ├── b.jpg
│   └── ...
├── mapping.json           # Optional text-to-sign mapping file
├── header.png             # Header logo for the GUI
└── README.md
```

---

# 📥 Adding Extra ISL Signs (Important)

You can easily **expand the sign vocabulary**.

### ✔ Option 1 — Download signs from **talkinghands**

Visit:

👉 [https://talkinghands.co.in/](https://talkinghands.co.in/)

Download ANY ISL sign GIF and place it inside:

```
ISL_Gifs/
```

Example:

```
ISL_Gifs/
    thank you.gif
    excuse me.gif
    how are you.gif
```

The system will **automatically detect** the new signs —
no code change needed.

---

### ✔ Option 2 — Create your own custom ISL signs

If you want to generate your own animations:

1. Create or record the sign as a GIF
2. Name it exactly as the phrase (lowercase recommended)
3. Save into:

```
ISL_Gifs/
```

Example:

```
welcome to my home.gif
```

The system will display it automatically.

---

### ✔ Option 3 — Improve phrase matching

If your GIF filename is:

```
please wait for sometime.gif
```

But you speak:

```
please wait
```

Just add mapping in `mapping.json`:

```json
{
  "please wait": "please wait for sometime"
}
```

---

# 🛠️ Installation

### 1. Install dependencies:

```
pip install sounddevice numpy matplotlib pillow speechrecognition rapidfuzz
```

(Optional) For offline STT:

```
pip install vosk
```

### 2. Run:

```
python main.py
```

---

# 💡 Requirements

* Python 3.8+
* Windows/Linux/Mac
* Working microphone

---

# 📌 Notes

* GIF names should be in lowercase for best results
* Avoid uppercase or extra spaces
* `mapping.json` is optional
* Letters folder is used only for fallback
* If header image fails to load, ensure `header.png` is in the project folder

---

# ❤️ Credits

Developed as an assistive technology tool to support communication with the deaf and hard-of-hearing community.

---

# 📞 Support

For issues, contact:

**Voice2Sign Development Team**
(📧rajubandam694@gmail.com)

Or create an issue on GitHub.

---

