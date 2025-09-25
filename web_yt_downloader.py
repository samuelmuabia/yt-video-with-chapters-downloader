import os
import re
import subprocess
import yt_dlp
import tempfile
import shutil
import streamlit as st

# ---------- Helpers ----------
def time_to_seconds(time_str):
    parts = list(map(int, time_str.split(':')))
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0, *parts
    else:
        raise ValueError(f"Invalid timestamp: {time_str}")
    return h * 3600 + m * 60 + s

def extract_chapters(description):
    chapters = []
    pattern = re.compile(r'(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—]\s*(.+)')
    for line in description.splitlines():
        match = pattern.search(line)
        if match:
            ts, title = match.groups()
            chapters.append((title.strip(), time_to_seconds(ts)))
    return chapters

def fetch_info(url):
    """Fetch metadata only (no video download)."""
    ydl_opts = {"quiet": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

@st.cache_resource
def download_video(url):
    """Download full video once per session, cache result."""
    tmpdir = tempfile.mkdtemp()
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_path = ydl.prepare_filename(info)
        return video_path, info

def split_all_chapters(video_path, chapters):
    tmpdir = tempfile.mkdtemp()
    chapters_folder = os.path.join(tmpdir, "chapters")
    os.makedirs(chapters_folder, exist_ok=True)

    for i, (title, start) in enumerate(chapters):
        end = chapters[i+1][1] if i+1 < len(chapters) else None
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
        output_file = os.path.join(chapters_folder, f"{i+1:02d} - {safe_title}.mp4")

        cmd = ["ffmpeg", "-i", video_path, "-ss", str(start)]
        if end:
            cmd += ["-t", str(end - start)]
        cmd += ["-c", "copy", output_file]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    zip_path = shutil.make_archive(os.path.join(tmpdir, "chapters"), "zip", chapters_folder)
    return zip_path


# ---------- Streamlit UI ----------
st.set_page_config(page_title="YouTube Downloader", page_icon="🎬", layout="centered")
st.title("🎬 YouTube Downloader with Chapters")

url = st.text_input("Enter YouTube URL")

if url:
    with st.spinner("Fetching video info..."):
        try:
            info = fetch_info(url)
        except Exception as e:
            st.error(f"Failed to fetch info: {e}")
            st.stop()

    st.success(f"✅ Video found: {info['title']}")
    description = info.get("description", "")
    chapters = extract_chapters(description)

    # ---- Full Video ----
    if st.button("⬇️ Download Full Video"):
        with st.spinner("Downloading full video..."):
            video_path, info_dl = download_video(url)
            with open(video_path, "rb") as f:
                st.download_button(
                    label="Save Full Video",
                    data=f,
                    file_name=f"{info_dl['title']}.mp4",
                    mime="video/mp4"
                )

    # ---- Chapters ----
    if chapters:
        st.subheader("📖 Chapters Found")

        # Store download result in session_state
        if st.button("⬇️ Process All Chapters (ZIP)"):
            with st.spinner("Splitting all chapters..."):
                video_path, _ = download_video(url)
                zip_path = split_all_chapters(video_path, chapters)
                st.session_state["chapters_zip"] = zip_path

        # Show download button only if zip ready
        if "chapters_zip" in st.session_state:
            with open(st.session_state["chapters_zip"], "rb") as f:
                st.download_button(
                    label="💾 Save All Chapters ZIP",
                    data=f,
                    file_name=f"{info['title']}_chapters.zip",
                    mime="application/zip"
                )

    else:
        st.info("No chapters found in description. Only full video available.")
