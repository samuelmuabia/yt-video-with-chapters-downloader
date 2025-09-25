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

def clear_yt_dlp_cache():
    """Clear yt-dlp cache to fix 403 errors."""
    try:
        # Method 1: Use yt-dlp API to clear cache
        ydl_opts = {'verbose': False}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.cache.remove()
        return True, "Cache cleared using yt-dlp API"
    except Exception as e1:
        try:
            # Method 2: Manual cache directory removal
            import tempfile
            cache_dir = os.path.join(tempfile.gettempdir(), 'yt-dlp')
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
                return True, f"Manual cache removal: {cache_dir}"
        except Exception as e2:
            try:
                # Method 3: Try common cache locations
                possible_cache_dirs = [
                    os.path.expanduser('~/.cache/yt-dlp'),
                    os.path.expanduser('~/.local/share/yt-dlp'),
                    '/tmp/yt-dlp',
                    '/var/tmp/yt-dlp'
                ]
                
                removed_dirs = []
                for cache_dir in possible_cache_dirs:
                    if os.path.exists(cache_dir):
                        shutil.rmtree(cache_dir)
                        removed_dirs.append(cache_dir)
                
                if removed_dirs:
                    return True, f"Removed cache directories: {', '.join(removed_dirs)}"
                else:
                    return False, f"No cache found. Errors: API={e1}, Manual={e2}"
                    
            except Exception as e3:
                return False, f"All methods failed: API={e1}, Manual={e2}, Common={e3}"

def get_ydl_opts_safe(tmpdir, ffmpeg_available=False):
    """Get yt-dlp options with anti-403 measures."""
    
    # Rotate through different user agents
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    ]
    
    base_opts = {
        'outtmpl': os.path.join(tmpdir, "%(title)s.%(ext)s"),
        'user_agent': random.choice(user_agents),
        'extractor_retries': 3,
        'fragment_retries': 5,
        'http_chunk_size': 10485760,  # 10MB chunks
        'sleep_interval': 1,
        'max_sleep_interval': 5,
        'ignoreerrors': False,
        'no_warnings': False,
        'cookiefile': None,  # Don't use cookies that might be stale
        'no_check_certificate': False,
        'geo_bypass': True,
        # Add headers to look more like a real browser
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
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
        "user_agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'geo_bypass': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

@st.cache_resource
def download_video(url, clear_cache_first=False):
    """Download full video with improved error handling and cache clearing."""
    if clear_cache_first:
        clear_success, clear_msg = clear_yt_dlp_cache()
        st.info(f"Cache clear attempt: {clear_msg}")
    
    tmpdir = tempfile.mkdtemp()
    
    # Check if ffmpeg is available
    ffmpeg_available, ffmpeg_path = check_ffmpeg()
    
    # Get appropriate options
    ydl_opts = get_ydl_opts_safe(tmpdir, ffmpeg_available)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Clear cache before each retry if it's not the first attempt
            if attempt > 0:
                clear_success, clear_msg = clear_yt_dlp_cache()
                st.info(f"Retry {attempt + 1}: Cleared cache - {clear_msg}")
                time.sleep(2)  # Wait a bit after clearing cache
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                st.info(f"Download attempt {attempt + 1}/{max_retries}...")
                info = ydl.extract_info(url, download=True)
                
                # Find the downloaded file
                expected_path = ydl.prepare_filename(info)
                
                if os.path.exists(expected_path):
                    return expected_path, info
                
                # Look for any video file in the directory
                for file in os.listdir(tmpdir):
                    if file.endswith(('.mp4', '.mkv', '.webm', '.avi', '.m4a')):
                        actual_path = os.path.join(tmpdir, file)
                        return actual_path, info
                
                raise FileNotFoundError("Downloaded file not found")
                
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg and attempt < max_retries - 1:
                st.warning(f"Attempt {attempt + 1} failed with 403 error. Clearing cache and retrying...")
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            elif attempt == max_retries - 1:
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

# Show yt-dlp version
try:
    import yt_dlp
    st.info(f"yt-dlp version: {yt_dlp.version.__version__}")
except:
    st.warning("Could not determine yt-dlp version")

# Add cache clear button
col1, col2 = st.columns([3, 1])
with col2:
    if st.button("🗑️ Clear Cache", help="Clear yt-dlp cache to fix 403 errors"):
        with st.spinner("Clearing cache..."):
            success, message = clear_yt_dlp_cache()
            if success:
                st.success(f"✅ {message}")
                # Clear the cached download function
                st.cache_resource.clear()
            else:
                st.error(f"❌ {message}")

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
            if "403" in str(e):
                st.info("💡 Try clicking the '🗑️ Clear Cache' button above and then retry.")
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
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        download_with_cache_clear = st.button("⬇️ Download Full Video", type="primary", use_container_width=True)
    
    with col2:
        download_after_clear = st.button("⬇️🗑️ Clear Cache & Download", help="Clear cache first, then download", use_container_width=True)
    
    if download_with_cache_clear or download_after_clear:
        clear_cache_first = download_after_clear
        
        with st.spinner("Downloading video... This may take a few minutes for longer videos."):
            try:
                video_path, info_dl = download_video(url, clear_cache_first=clear_cache_first)
                
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
                    st.info("💡 **How to fix 403 Forbidden errors:**")
                    st.info("1. Click the '🗑️ Clear Cache' button above")
                    st.info("2. Wait a few seconds, then try downloading again")
                    st.info("3. If that doesn't work, try the '⬇️🗑️ Clear Cache & Download' button")
                    st.info("4. Some videos may be region-locked or have download restrictions")

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
            
            col1, col2 = st.columns([3, 1])
            
            with col1:
                process_chapters = st.button("⬇️ Download All Chapters as ZIP", type="secondary", use_container_width=True)
            
            with col2:
                process_with_clear = st.button("⬇️🗑️ Clear & Process", help="Clear cache first, then process chapters", use_container_width=True)
            
            if process_chapters or process_with_clear:
                clear_first = process_with_clear
                
                with st.spinner("Processing chapters... This will take several minutes."):
                    try:
                        video_path, _ = download_video(url, clear_cache_first=clear_first)
                        zip_path = split_all_chapters(video_path, chapters)
                        st.session_state["chapters_zip"] = zip_path
                        st.success("✅ All chapters processed successfully!")
                    except Exception as e:
                        st.error(f"❌ Chapter processing failed: {e}")
                        if "403" in str(e):
                            st.info("💡 Try using the 'Clear Cache' button and retry.")

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
    
    # Show cache information
    st.write("**Cache Info:**")
    try:
        cache_dir = os.path.expanduser('~/.cache/yt-dlp')
        st.write(f"- Default cache dir exists: {os.path.exists(cache_dir)}")
        if os.path.exists(cache_dir):
            st.write(f"- Cache dir size: {sum(os.path.getsize(os.path.join(dirpath, filename)) for dirpath, dirnames, filenames in os.walk(cache_dir) for filename in filenames) / 1024:.1f} KB")
    except Exception as e:
        st.write(f"- Cache info error: {e}")
    
    # Show current working directory
    st.write(f"- Current working directory: {os.getcwd()}")
    
    # Test cache clear function
    if st.button("Test Cache Clear"):
        success, message = clear_yt_dlp_cache()
        st.write(f"Cache clear test: {'✅' if success else '❌'} {message}")