import os
import re
import subprocess
import yt_dlp

def time_to_seconds(time_str):
    """Convert HH:MM:SS or MM:SS to seconds."""
    parts = list(map(int, time_str.split(':')))
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h = 0
        m, s = parts
    else:
        raise ValueError(f"Invalid timestamp: {time_str}")
    return h * 3600 + m * 60 + s

def extract_chapters(description):
    """Extract (title, start_time) from description."""
    chapters = []
    pattern = re.compile(r'(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—]\s*(.+)')
    for line in description.splitlines():
        match = pattern.search(line)
        if match:
            ts, title = match.groups()
            chapters.append((title.strip(), time_to_seconds(ts)))
    return chapters

def download_youtube_video(url, output_folder="downloads"):
    os.makedirs(output_folder, exist_ok=True)
    # Step 1: Download video + get description
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(output_folder, "%(title)s.%(ext)s"),
        "writesubtitles": True,
        "writeautomaticsub": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_path = ydl.prepare_filename(info)
        description = info.get("description", "")
    
    # Step 2: Extract chapters from description
    chapters = extract_chapters(description)
    if not chapters:
        print("No chapters found in description. Video saved as a single file.")
        return
    
    # Step 3: Split video using ffmpeg
    chapters_folder = os.path.join(output_folder, "chapters")
    os.makedirs(chapters_folder, exist_ok=True)
    for i, (title, start_time) in enumerate(chapters):
        if i < len(chapters) - 1:
            duration = chapters[i+1][1] - start_time
        else:
            duration = None  # last chapter goes till end
        output_file = os.path.join(chapters_folder, f"{i+1:02d} - {title}.mp4")
        cmd = ["ffmpeg", "-i", video_path, "-ss", str(start_time)]
        if duration:
            cmd += ["-t", str(duration)]
        cmd += ["-c", "copy", output_file]
        subprocess.run(cmd)
    print(f"Chapters saved in folder: {chapters_folder}")


if __name__ == "__main__":
    url = input("Enter YouTube URL: ").strip()
    download_youtube_video(url)
    
