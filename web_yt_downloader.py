import os
import re
import subprocess
import yt_dlp
import tempfile
import shutil
import streamlit as st
from pathlib import Path

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

def check_ffmpeg():
    """Check if ffmpeg is available and return path info."""
    try:
        result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
        if result.returncode == 0:
            ffmpeg_path = result.stdout.strip()
            # Test if it actually works
            test_result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
            if test_result.returncode == 0:
                return True, ffmpeg_path
        return False, None
    except Exception as e:
        return False, str(e)

def fetch_info(url):
    """Fetch metadata only (no video download)."""
    ydl_opts = {"quiet": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

@st.cache_resource
def download_video(url):
    """Download full video with improved format selection."""
    tmpdir = tempfile.mkdtemp()
    
    # Check if ffmpeg is available
    ffmpeg_available, ffmpeg_path = check_ffmpeg()
    
    if ffmpeg_available:
        # If ffmpeg is available, we can use the best quality with merging
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
        }
    else:
        # If ffmpeg is not available, use single-file formats only
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
        }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)
            
            # Handle case where extension changes
            if not os.path.exists(video_path):
                # Look for any file in the directory
                files = os.listdir(tmpdir)
                if files:
                    video_path = os.path.join(tmpdir, files[0])
                else:
                    raise FileNotFoundError("Downloaded file not found")
            
            return video_path, info
    except Exception as e:
        raise RuntimeError(f"Video download failed: {e}")

def split_all_chapters(video_path, chapters):
    """Split video into chapters using ffmpeg."""
    ffmpeg_available, ffmpeg_path = check_ffmpeg()
    
    if not ffmpeg_available:
        raise RuntimeError("ffmpeg is required for chapter splitting but is not available.")
    
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
        cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero", output_file]
        
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except subprocess.CalledProcessError as e:
            st.warning(f"Failed to split chapter '{title}': {e}")
            continue

    zip_path = shutil.make_archive(os.path.join(tmpdir, "chapters"), "zip", chapters_folder)
    return zip_path


# ---------- Streamlit UI ----------
st.set_page_config(page_title="YouTube Downloader", page_icon="🎬", layout="centered")
st.title("🎬 YouTube Downloader with Chapters")

# Debug information
ffmpeg_available, ffmpeg_info = check_ffmpeg()
if ffmpeg_available:
    st.success(f"✅ ffmpeg is available at: {ffmpeg_info}")
else:
    st.error(f"❌ ffmpeg not found: {ffmpeg_info}")
    st.warning("Chapter splitting will be disabled. Only full video downloads will work.")

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
            try:
                video_path, info_dl = download_video(url)
                
                # Check if file exists and get its size
                if os.path.exists(video_path):
                    file_size = os.path.getsize(video_path)
                    st.info(f"Video size: {file_size / (1024*1024):.1f} MB")
                    
                    with open(video_path, "rb") as f:
                        st.download_button(
                            label="💾 Save Full Video",
                            data=f,
                            file_name=f"{info_dl['title']}.mp4",
                            mime="video/mp4"
                        )
                    st.success("✅ Video downloaded successfully!")
                else:
                    st.error("Video file not found after download")
                    
            except Exception as e:
                st.error(f"Download failed: {e}")
                # Show debug info
                st.error("Debug info: If you see 'ffmpeg not found', the issue is with the deployment setup.")

    # ---- Chapters ----
    if chapters:
        st.subheader("📖 Chapters Found")
        
        # Show chapters list
        for i, (title, start) in enumerate(chapters):
            minutes, seconds = divmod(start, 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                time_str = f"{minutes}:{seconds:02d}"
            st.write(f"{i+1}. {time_str} - {title}")
        
        if ffmpeg_available:
            if st.button("⬇️ Process All Chapters (ZIP)"):
                with st.spinner("Downloading video and splitting chapters..."):
                    try:
                        video_path, _ = download_video(url)
                        zip_path = split_all_chapters(video_path, chapters)
                        st.session_state["chapters_zip"] = zip_path
                        st.success("✅ All chapters processed successfully!")
                    except Exception as e:
                        st.error(f"Chapter processing failed: {e}")

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
            st.error("❌ Chapter splitting requires ffmpeg. Please check your deployment setup.")
            st.info("Make sure you have 'ffmpeg' in your packages.txt file in the root directory of your repository.")

    else:
        st.info("No chapters found in description. Only full video available.")

# Debug section
with st.expander("🔧 Debug Information"):
    st.write("**System Info:**")
    st.write(f"- ffmpeg available: {ffmpeg_available}")
    st.write(f"- ffmpeg info: {ffmpeg_info}")
    
    # Check if packages.txt exists
    if os.path.exists("packages.txt"):
        st.write("- packages.txt found ✅")
        with open("packages.txt", "r") as f:
            st.write(f"- packages.txt content: {f.read()}")
    else:
        st.write("- packages.txt NOT found ❌")
    
    # Show environment variables
    st.write("**Environment:**")
    st.write(f"- PATH: {os.environ.get('PATH', 'Not found')[:200]}...")