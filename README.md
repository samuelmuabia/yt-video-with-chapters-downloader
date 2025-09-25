# YouTube Downloader with Chapters

A simple Streamlit web app to download YouTube videos and automatically split them into chapters based on timestamps in the video description.

## Features
- Download the full YouTube video as an MP4 file.
- Automatically detect chapters from the video description (timestamps + titles).
- Split the video into separate chapter files using `ffmpeg`.
- Download all chapters as a single ZIP archive.
- Clean, user-friendly web interface.

## Requirements
- Python 3.7+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [ffmpeg](https://ffmpeg.org/)
- [streamlit](https://streamlit.io/)

## Installation
1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd yt-video-with-chapters-downloader
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   Or manually:
   ```bash
   pip install streamlit yt-dlp
   ```
3. **Install ffmpeg:**
   - macOS: `brew install ffmpeg`
   - Ubuntu: `sudo apt install ffmpeg`
   - Windows: [Download from ffmpeg.org](https://ffmpeg.org/download.html)

## Usage
1. **Start the app:**
   ```bash
   streamlit run web_yt_downloader.py
   ```
2. **Open the web interface:**
   - Go to the URL shown in your terminal (usually http://localhost:8501)
3. **Enter a YouTube URL** and follow the prompts to download the full video or split by chapters.

## Notes
- Chapters are detected from the video description using lines like `00:00 - Intro` or `1:23:45 – Chapter Title`.
- If no chapters are found, only the full video download is available.
- All processing is done locally; no data is sent to any server.

## License
MIT License
