# CNBC Awaaz Automated Market Call Parser (to Google Sheets)

An automated AI pipeline that ingests daily market broadcast streams from the **CNBC Awaaz YouTube channel**, extracts structured trading recommendations (Cash, Futures, Options, Index Levels) using **Gemini Multimodal LLM reasoning**, and synchronizes them in real time into **Google Sheets** adhering strictly to an 8-column schema.

---

## 📊 Google Sheets 8-Column Contract

Every extracted trade is logged with the following schema:

| Col # | Column Header | Data Type | Description / Values |
| :--- | :--- | :--- | :--- |
| **Col 1** | Current Date | Date | `YYYY-MM-DD` |
| **Col 2** | Call Type | Enum | `Spotlight Stocks`, `Chart GPT-1`, `Chart GPT-2`, `Pehla Sauda`, `Cash Calls`, `Sasta Option`, `Chart Ka Chamatkar`, `Trade Recommendation`, `BTST`, `STBT`, `Index Level` |
| **Col 3** | Stock Name | String | NSE Ticker / Option Identifier (e.g., `SAIL 185 CE Sep`, `GROWW`, `NIFTY 24500 CE`, `RELIANCE`) |
| **Col 4** | CMP | Float / String | Current Market / Recommended Entry Price (or `-` if not given) |
| **Col 5** | Target 1 | Float | Primary price objective |
| **Col 6** | Target 2 | Float / String | Secondary price objective (or `-`) |
| **Col 7** | Stop Loss | Float | Strict invalidation / risk price |
| **Col 8** | Instrument Type | Enum | `Cash`, `Futures`, `Options` |

---

## ⏰ IST Market Execution Schedule

The pipeline includes an automated daemon scheduler configured for Indian Standard Time (IST) market sessions (Monday–Friday):

* **09:00 AM IST** (trailing 25 mins): `Spotlight Stocks`, `Chart GPT-1`, `Index Levels`
* **09:20 AM IST** (trailing 20 mins): `Chart GPT-2`, `Pehla Sauda` (Opening market trades)
* **10:20 AM IST** (trailing 60 mins): `Cash Calls`, `Sasta Option`, `Chart Ka Chamatkar`
* **02:45 PM IST** (trailing 20 mins): `Trade Recommendations`
* **03:25 PM IST** (trailing 25 mins): `BTST`, `STBT` (Closing market calls)

---

## 🚀 How to Run

### 1. Test All Connections
Verify Google Sheets sync and Gemini API access:
```bash
python main.py --test-auth
```

### 2. Start Automated Market Daemon (Daily IST Triggers)
Run 24/7 in background to capture calls at scheduled show windows:
```bash
python main.py --schedule
```

### 3. On-Demand Live Extraction
Instantly capture the trailing N minutes of the live stream and parse calls:
```bash
python main.py --live --segment "Sasta Option" --duration 20
```

### 4. Process Recorded YouTube Broadcast / Replay
Pass any YouTube video URL to extract calls from that broadcast:
```bash
python main.py --url "https://www.youtube.com/watch?v=..." --segment "Pehla Sauda"
```

### 5. Process Local Audio File (Offline Testing)
```bash
python main.py --file "chunk.mp3" --segment "Chart Ka Chamatkar"
```

### 6. Dry Run Mode
Extract calls and print to terminal without modifying the Google Sheet:
```bash
python main.py --file "chunk.mp3" --dry-run
```

---

## ☁️ Deploying to DigitalOcean Droplet (24/7 Background Automation)

### Option A: Running with Systemd Daemon (Recommended)
1. Copy the project files to your Droplet (`/opt/cnbc-tracker`).
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   sudo apt-get install -y ffmpeg
   ```
3. Create a systemd service file: `/etc/systemd/system/cnbc-tracker.service`
   ```ini
   [Unit]
   Description=CNBC Awaaz Market Call Parser Daemon
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/opt/cnbc-tracker
   ExecStart=/usr/bin/python3 /opt/cnbc-tracker/main.py --schedule
   Restart=always
   RestartSec=30
   EnvironmentFile=/opt/cnbc-tracker/.env

   [Install]
   WantedBy=multi-user.target
   ```
4. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable cnbc-tracker
   sudo systemctl start cnbc-tracker
   ```
5. Check live logs anytime:
   ```bash
   journalctl -u cnbc-tracker -f
   ```

---

## 🛡️ Built with Karpathy's 3 Principles
* **Principle 1 (Data Understanding)**: Tailored extraction prompts handling Hindi/Hinglish market terminology, strike prices, CE/PE derivatives, stop loss, and targets.
* **Principle 2 (Minimal End-to-End Slice)**: Verified vertical slice connecting audio ingestion $\rightarrow$ Gemini Multimodal LLM $\rightarrow$ Google Sheets sync.
* **Principle 3 (Resilience & Hardening)**: Multi-tier model fallback (`gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.5-flash-lite`), automated duplicate filtering, and robust webhook / OAuth / service account support.
