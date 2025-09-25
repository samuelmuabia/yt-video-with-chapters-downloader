import os
import re
import subprocess
import yt_dlp
import tempfile
import shutil
import streamlit as st
from pathlib import Path
import time
import random

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
        return False, "ffmpeg not found in PATH"
    except Exception as e:
        return False, str(e)

def get_ydl_opts_safe(tmpdir, ffmpeg_available=False):
    """Get yt-dlp options that work around 403 errors."""
    
    # User agents to rotate through
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]
    
    base_opts = {
        'outtmpl': os.path.join(tmpdir, "%(title)s.%(ext)s"),
        'user_agent': random.choice(user_agents),
        'extractor_retries': 3,
        'fragment_retries': 3,
        'http_chunk_size': 10485760,  # 10MB chunks
        'sleep_interval': 1,
        'max_sleep_interval': 5,
        'ignoreerrors': False,
        'no_warnings': False,
    }
    
    if ffmpeg_available:
        # High quality with merging if ffmpeg is available
        base_opts.update({
            'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
            'merge_output_format': 'mp4',
        })
    else:
        # Single file format to avoid needing ffmpeg
        base_opts['format'] = 'best[ext=mp4][height<=720]/best[height<=720]/best'
    
    return base_opts

def fetch_info(url):
    """Fetch metadata only (no video download)."""
    ydl_opts = {
        "quiet": True, 
        "skip_download": True,
        "user_agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

@st.cache_resource
def download_video(url):
    """Download full video with improved error handling."""
    tmpdir = tempfile.mkdtemp()
    
    # Check if ffmpeg is available
    ffmpeg_available, ffmpeg_path = check_ffmpeg()
    
    # Get appropriate options
    ydl_opts = get_ydl_opts_safe(tmpdir, ffmpeg_available)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                st.info(f"Download attempt {attempt + 1}/{max_retries}...")
                info = ydl.extract_info(url, download=True)
                
                # Find the downloaded file
                expected_path = ydl.prepare_filename(info)
                
                if os.path.exists(expected_path):
                    return expected_path, info
                
                # Look for any video file in the directory
                for file in os.listdir(tmpdir):
                    if file.endswith(('.mp4', '.mkv', '.webm', '.avi')):
                        actual_path = os.path.join(tmpdir, file)
                        return actual_path, info
                
                raise FileNotFoundError("Downloaded file not found")
                
        except Exception as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Video download failed after {max_retries} attempts: {e}")
            else:
                st.warning(f"Attempt {attempt + 1} failed: {str(e)[:100]}... Retrying...")
                time.sleep(2 ** attempt)  # Exponential backoff
    
    raise RuntimeError("All download attempts failed")

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
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:50]  # Limit filename length
        output_file = os.path.join(chapters_folder, f"{i+1:02d} - {safe_title}.mp4")

        cmd = ["ffmpeg", "-i", video_path, "-ss", str(start)]
        if end:
            cmd += ["-t", str(end - start)]
        cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero", "-y", output_file]
        
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
    st.success(f"✅ ffmpeg is available")
else:
    st.error(f"❌ ffmpeg not found")
    st.warning("Chapter splitting will be disabled. Only full video downloads will work.")
    st.info("💡 To enable chapter splitting, make sure 'ffmpeg' is in your packages.txt file in the root directory.")

# Show yt-dlp version
try:
    import yt_dlp
    st.info(f"yt-dlp version: {yt_dlp.version.__version__}")
except:
    st.warning("Could not determine yt-dlp version")

url = st.text_input("Enter YouTube URL", placeholder="https://www.youtube.com/watch?v=...")

if url:
    if not url.startswith(('https://www.youtube.com/', 'https://youtu.be/')):
        st.error("Please enter a valid YouTube URL")
        st.stop()
    
    with st.spinner("Fetching video info..."):
        try:
            info = fetch_info(url)
        except Exception as e:
            st.error(f"Failed to fetch video info: {e}")
            st.info("This might be due to YouTube restrictions. Try a different video or check if the URL is correct.")
            st.stop()

    st.success(f"✅ Video found: {info['title']}")
    
    # Show video duration
    duration = info.get('duration', 0)
    if duration:
        duration_str = f"{duration // 3600:02d}:{(duration % 3600) // 60:02d}:{duration % 60:02d}"
        st.info(f"Duration: {duration_str}")
    
    description = info.get("description", "")
    chapters = extract_chapters(description)

    # ---- Full Video ----
    st.subheader("📥 Full Video Download")
    
    if st.button("⬇️ Download Full Video", type="primary"):
        with st.spinner("Downloading video... This may take a few minutes for longer videos."):
            try:
                video_path, info_dl = download_video(url)
                
                # Check if file exists and get its size
                if os.path.exists(video_path):
                    file_size = os.path.getsize(video_path)
                    st.success(f"✅ Video downloaded! Size: {file_size / (1024*1024):.1f} MB")
                    
                    with open(video_path, "rb") as f:
                        st.download_button(
                            label="💾 Save Video to Your Device",
                            data=f,
                            file_name=f"{info_dl['title']}.mp4",
                            mime="video/mp4",
                            use_container_width=True
                        )
                else:
                    st.error("Video file not found after download")
                    
            except Exception as e:
                st.error(f"❌ Download failed: {e}")
                if "403" in str(e):
                    st.info("💡 This is likely due to YouTube restrictions. Try:")
                    st.info("- Using a different video")  
                    st.info("- Checking if the video is region-locked")
                    st.info("- Trying again later")

    # ---- Chapters ----
    if chapters:
        st.subheader("📖 Chapters Found")
        
        # Show chapters list in a nice format
        for i, (title, start) in enumerate(chapters):
            minutes, seconds = divmod(start, 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                time_str = f"{minutes}:{seconds:02d}"
            st.write(f"**{i+1}.** `{time_str}` - {title}")
        
        if ffmpeg_available:
            st.info("🎬 With ffmpeg available, you can download individual chapters!")
            
            if st.button("⬇️ Download All Chapters as ZIP", type="secondary"):
                with st.spinner("Processing chapters... This will take several minutes."):
                    try:
                        video_path, _ = download_video(url)
                        zip_path = split_all_chapters(video_path, chapters)
                        st.session_state["chapters_zip"] = zip_path
                        st.success("✅ All chapters processed successfully!")
                    except Exception as e:
                        st.error(f"❌ Chapter processing failed: {e}")

            # Show download button only if zip ready
            if "chapters_zip" in st.session_state:
                with open(st.session_state["chapters_zip"], "rb") as f:
                    st.download_button(
                        label="💾 Save All Chapters ZIP",
                        data=f,
                        file_name=f"{info['title']}_chapters.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
        else:
            st.warning("❌ Chapter downloading requires ffmpeg installation.")

    else:
        st.info("📄 No chapters found in video description. Only full video download available.")

# Debug section
with st.expander("🔧 Debug Information"):
    st.write("**System Info:**")
    st.write(f"- ffmpeg available: {ffmpeg_available}")
    st.write(f"- ffmpeg info: {ffmpeg_info}")
    
    # Check if packages.txt exists
    packages_txt_paths = ["packages.txt", "../packages.txt", "../../packages.txt"]
    packages_found = False
    
    for path in packages_txt_paths:
        if os.path.exists(path):
            st.write(f"- packages.txt found at {path} ✅")
            with open(path, "r") as f:
                content = f.read().strip()
                st.write(f"- packages.txt content: `{content}`")
            packages_found = True
            break
    
    if not packages_found:
        st.write("- packages.txt NOT found ❌")
        st.write("- **SOLUTION:** Create a `packages.txt` file in your repository root with content: `ffmpeg`")
    
    # Show current working directory
    st.write(f"- Current working directory: {os.getcwd()}")
    st.write(f"- Files in current directory: {os.listdir('.')}")
    
    # Show environment info
    st.write("**Environment:**")
    st.write(f"- PATH contains /usr/bin: {'/usr/bin' in os.environ.get('PATH', '')}")