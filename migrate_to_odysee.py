import argparse
import datetime
import glob
import json
import os
import re
import subprocess  # For ffprobe/ffmpeg in is_vertical_short and audio normalization
import sys
import time
from typing import Dict, List, Optional

import requests
import yt_dlp

# Configuration Section - User Required Data
# Replace these values with your own
YOUTUBE_CHANNEL_URL: str = REPLACE  # Your YouTube channel URL
ODYSEE_CHANNEL_NAME: str = REPLACE  # Optional: Replace with your Odysee channel name (e.g., "@mychannel") or leave as None
ODYSEE_BID: str = "0.001"  # Amount of LBC to bid for each claim (required for publishing)

def format_duration(seconds: float) -> str:
    """Format duration in seconds to HH:MM:SS."""
    seconds = int(seconds)  # Convert to integer to avoid float issues
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"

def parse_duration(duration_str: str) -> int:
    """Parse HH:MM:SS duration string to total seconds."""
    h, m, s = map(int, duration_str.split(':'))
    return h * 3600 + m * 60 + s

def determine_type(info: Dict) -> str:
    """Determine the type of content based on video info."""
    if 'shorts' in info.get('original_url', ''):
        return 'short'
    live_status = info.get('live_status', 'not_live')
    if live_status != 'not_live':
        return 'livestream'
    return 'video'

def sanitize_name(name: str) -> str:
    """Sanitize a name to be a valid LBRY stream name."""
    name = name.lower().replace(' ', '-')
    name = re.sub(r'[^a-z0-9_-]', '', name)
    if not name:
        name = 'unnamed-stream'
    name = name[:100]
    name = name.strip('-_')
    return name

def extract_youtube_content(channel_url: str, content_type: str, start_date: datetime.date, end_date: datetime.date,
                            cookies: Optional[str], verbose: bool, log_file: str, video_log: Dict[str, Dict]) -> Dict[str, Dict]:
    """Extract and filter YouTube videos, livestreams, or shorts using yt-dlp with date and content filters, using video_log for caching."""
    if content_type.lower() == 'videos':
        tab = '/videos'
        match_filters = ['live_status!=is_live & !original_url~=shorts']
    elif content_type.lower() == 'livestreams':
        tab = '/streams'
        match_filters = ['live_status=is_live|was_live|post_live']
    else:  # shorts
        tab = '/shorts'
        match_filters = ['original_url~=shorts']

    url = f"{channel_url}{tab}"

    ydl_opts: Dict = {
        'quiet': not verbose,
        'extract_flat': True,  # Fetch minimal metadata initially to optimize
        'no_warnings': not verbose,
        'verbose': verbose,
        'dateafter': start_date.strftime('%Y%m%d'),
        'datebefore': end_date.strftime('%Y%m%d'),
        'match_filters': match_filters,
        'sleep_interval': 5,  # Sleep 5-30s between requests
        'max_sleep_interval': 30,
        'sleep_requests': 1,  # Sleep 1s before each API call
        'retry_sleep': 10,  # Sleep 10s before retrying on rate limit errors
        # 'playlist_items': '1-100',  # Limit to first 100 items; adjust or remove for full fetch
    }
    if cookies:
        ydl_opts['cookiefile'] = cookies

    try:
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"Fetching {content_type} from {url}\n")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get('entries', [])
    except Exception as e:
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"Extraction failed for {url}: {e}\n")
        print(f"Extraction error: {e}. Check {log_file} for details.")
        return {}

    if not entries:
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"No entries found for {url} with content_type={content_type}, date range {start_date} to {end_date}. Verify channel URL, content visibility, or use --cookies if private.\n")
        print("No videos found. Enable --verbose for more details or check migration_log.txt.")
        return {}

    video_dict: Dict[str, Dict] = {}
    for entry in entries:
        if not entry or 'id' not in entry:
            with open(log_file, 'a', encoding='utf-8') as log:
                try:
                    log.write(f"Skipping invalid entry (id: {entry.get('id', 'unknown')}, title: {entry.get('title', 'unknown')[:50]})\n")
                except UnicodeEncodeError:
                    log.write(f"Skipping invalid entry (id: {entry.get('id', 'unknown')}, title: <unencodable>)\n")
            continue

        vid_id = entry['id']
        required_keys = ['title', 'upload_date', 'duration', 'description', 'type', 'thumbnail', 'tags']
        if vid_id in video_log and all(k in video_log[vid_id] for k in required_keys):
            data = video_log[vid_id]
        else:
            ydl_full_opts = {
                'quiet': not verbose,
                'no_warnings': not verbose,
                'verbose': verbose,
            }
            if cookies:
                ydl_full_opts['cookiefile'] = cookies
            with yt_dlp.YoutubeDL(ydl_full_opts) as ydl_full:
                try:
                    full_info = ydl_full.extract_info(f"https://www.youtube.com/watch?v={vid_id}", download=False)
                except Exception as e:
                    with open(log_file, 'a', encoding='utf-8') as log:
                        log.write(f"Failed to fetch full info for {vid_id}: {e}\n")
                    continue

            # Apply match_filter manually since it's not applied on individual extract
            with yt_dlp.YoutubeDL(ydl_opts) as ydl_matcher:
                if ydl_matcher._match_entry(full_info, incomplete=False) is not None:
                    continue

            upload_str = full_info.get('upload_date')
            if not upload_str:
                with open(log_file, 'a', encoding='utf-8') as log:
                    log.write(f"No upload_date for video {vid_id}; skipping.\n")
                continue

            data = {
                'title': full_info.get('title', 'Untitled'),
                'upload_date': upload_str,
                'duration': format_duration(full_info.get('duration', 0)),
                'description': full_info.get('description', ''),
                'type': determine_type(full_info),
                'thumbnail': full_info.get('thumbnail', ''),
                'tags': full_info.get('tags', [])
            }
            video_log[vid_id] = data
            time.sleep(5)  # Avoid rate limits

        # Check date range
        upload_str = data.get('upload_date')
        if upload_str:
            try:
                upload_dt = datetime.datetime.strptime(upload_str, '%Y%m%d').date()
            except ValueError:
                continue
            if upload_dt > end_date:
                continue
            if upload_dt < start_date:
                break  # Entries are newest first
            video_dict[vid_id] = data

    if not video_dict:
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"No videos matched the criteria for content_type={content_type}, date range {start_date} to {end_date}.\n")
        print("No videos matched the criteria. Check migration_log.txt for details.")

    return video_dict

def confirm_videos(video_dict: Dict[str, Dict], log_file: str) -> Dict[str, Dict]:
    """Interactively confirm and remove videos from the dictionary; allow cancel to exit."""
    while True:
        print("\nCurrent videos to migrate:")
        print(json.dumps(video_dict, indent=4, ensure_ascii=False))
        user_input = input(f"{len(video_dict.keys())} videos found. Enter space-separated video IDs to remove, 'cancel' to exit, or press Enter to proceed: ").strip()
        if user_input.lower() == 'cancel':
            with open(log_file, 'a', encoding='utf-8') as log:
                log.write("Migration cancelled by user.\n")
            print("Exiting as requested.")
            sys.exit(0)
        if not user_input:
            break
        ids_to_remove = user_input.split()
        for vid_id in ids_to_remove:
            video_dict.pop(vid_id, None)
    return video_dict

def is_vertical_short(video_path: str) -> bool:
    """Check if the video is vertical (short-like) using ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
             '-of', 'csv=s=x:p=0', video_path],
            capture_output=True, text=True
        )
        width, height = map(int, result.stdout.strip().split('x'))
        return height > width  # Vertical if height > width
    except Exception as e:
        print(f"Failed to check aspect ratio for {video_path}: {e}")
        return False  # Assume not vertical on error

# def get_audio_stats(video_path: str) -> Optional[Dict[str, float]]:
#     """Get max and mean audio volume stats using ffmpeg."""
#     try:
#         # Run ffmpeg with astats filter to get stats
#         command = ['ffmpeg', '-i', video_path, '-af', 'astats=metadata=1:reset=1', '-vn', '-f', 'null', '-']
#         result = subprocess.run(command, stderr=subprocess.PIPE, text=True, check=True)
#         lines = result.stderr.split('\n')
#         max_volume = None
#         mean_volume = None
#         for line in lines:
#             if 'Max volume' in line:
#                 max_volume = float(line.split(':')[1].strip().split(' ')[0])
#             if 'Mean volume' in line:
#                 mean_volume = float(line.split(':')[1].strip().split(' ')[0])
#         if max_volume is None or mean_volume is None:
#             return None
#         return {'max': max_volume, 'mean': mean_volume}
#     except Exception as e:
#         print(f"Failed to get audio stats for {video_path}: {e}")
#         return None

# def normalize_audio(video_path: str, temp_folder: str, vid_id: str, log_file: str) -> str:
#     """Normalize audio if too low by boosting volume to target max ~0 dB."""
#     stats = get_audio_stats(video_path)
#     if stats is None:
#         return video_path  # Skip if stats fail
#     max_vol = stats['max']
#     if max_vol >= -5:  # Already above threshold
#         return video_path

#     # Calculate boost: negative of max_vol to reach 0 dB (with headroom to avoid clipping)
#     boost_db = -max_vol - 1  # -1 dB headroom
#     normalized_path = os.path.join(temp_folder, f"{vid_id}_normalized.mp4")
#     command = ['ffmpeg', '-i', video_path, '-af', f'volume={boost_db}dB', '-c:v', 'copy', '-c:a', 'aac', normalized_path]
#     try:
#         result = subprocess.run(command, check=True, capture_output=True, text=True)
#         with open(log_file, 'a', encoding='utf-8') as log:
#             log.write(f"Normalized audio for {vid_id}: {result.stdout}\n")
#         os.remove(video_path)  # Replace original
#         return normalized_path
#     except Exception as e:
#         with open(log_file, 'a', encoding='utf-8') as log:
#             log.write(f"Audio normalization failed for {video_path}: {str(e)}\n")
#         return video_path  # Fallback to original

def download_video(video_id: str, temp_folder: str, cookies: Optional[str], log_file: str) -> Optional[str]:
    """Download video in highest quality using yt-dlp, converting to MP4 if necessary, handling SABR formats, and normalizing audio."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    video_path = os.path.join(temp_folder, f"{video_id}.%(ext)s")

    ydl_opts: Dict = {
        'format': 'best[height<=1080][fps>=30]/best[height<=1080]',
        'outtmpl': {'default': video_path},
        'quiet': False,  # Show progress
        'sleep_interval': 5,
        'max_sleep_interval': 30,
        'retry_sleep': 10,
        'extractor_args': {
            'youtube': ['formats=missing_pot']  # Enable broken/missing URL formats
        },
        'postprocessors': [
            # Removed FFmpegMerger, as format '+' handles merging
            {  # Convert to MP4 with H.264 baseline for better iOS compatibility
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'
            },
        ],
    }
    if cookies:
        ydl_opts['cookiefile'] = cookies

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            ydl.download([url])

        # Find video file (now always MP4 after postprocessing)
        actual_video = next((f for f in os.listdir(temp_folder) if f.startswith(video_id) and f.endswith('.mp4')), None)
        if actual_video:
            video_path = os.path.join(temp_folder, actual_video)
        else:
            return None

        # Always normalize audio to ensure it passes verification
        # video_path = normalize_audio(video_path, temp_folder, video_id, log_file)
        return video_path
    except Exception as e:
        print(f"Download failed for {video_id}: {e}")
        return None

def claim_exists(video_name: str, log_file: str) -> bool:
    """Check if a valid claim (active stream with source) with the given name already exists on Odysee using LBRY API."""
    api_url = "http://localhost:5279"
    data = {
        "jsonrpc": "2.0",
        "method": "resolve",
        "params": {"urls": [video_name]},
        "id": 1
    }
    try:
        response = requests.post(api_url, json=data)
        response.raise_for_status()
        result = response.json().get("result", {})
        if video_name in result:
            claim = result[video_name]
            # Check if it's a valid stream claim with a source (file)
            if claim.get('value_type') == 'stream' and claim.get('value', {}).get('source'):
                with open(log_file, 'a', encoding='utf-8') as log:
                    log.write(f"Valid claim '{video_name}' already exists on Odysee (active stream). Skipping upload.\n")
                return True
            else:
                with open(log_file, 'a', encoding='utf-8') as log:
                    log.write(f"Claim '{video_name}' exists but is invalid/inactive (no source or not a stream). Proceeding with upload.\n")
                return False
        return False
    except Exception as e:
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"Failed to check if claim '{video_name}' exists: {str(e)}\n")
        print(f"Warning: Failed to check existing claim: {e}. Proceeding with upload.")
        return False  # Assume not exists on error to avoid blocking

def upload_to_odysee(video_path: str, thumbnail_url: str, title: str, description: str, channel_name: Optional[str],
                     bid: str, log_file: str, duration: str, upload_date: str, content_type: str, tags: List[str]) -> bool:
    """Upload video to Odysee using LBRY API (requires daemon running at localhost:5279)."""
    api_url = "http://localhost:5279"

    # Verify video file exists
    video_path = os.path.normpath(video_path)
    if not os.path.isfile(video_path):
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"Video file not found: {video_path}\n")
        return False

    # Detect if short/vertical and adjust params
    is_short = content_type == 'short' or is_vertical_short(video_path)
    optimize_file = False if is_short else True  # Disable optimization for shorts to avoid re-encoding issues

    # Prepare release time
    try:
        dt = datetime.datetime.strptime(upload_date, '%Y%m%d')
        release_time = int(dt.timestamp())
    except Exception:
        release_time = int(time.time())

    # Publish video with retry
    video_name = sanitize_name(title)
    params_video: Dict = {
        "name": video_name,
        "bid": bid,
        "file_path": video_path,
        "title": title,
        "description": description,
        "thumbnail_url": thumbnail_url,
        "languages": ["en"],
        "release_time": release_time,
        "optimize_file": optimize_file,
        "tags": tags + [content_type] + (["short"] if is_short else []),
    }
    if duration:
        params_video["duration"] = parse_duration(duration)
    if channel_name:
        params_video["channel_name"] = channel_name

    data_video = {
        "jsonrpc": "2.0",
        "method": "publish",
        "params": params_video,
        "id": 1
    }

    for attempt in range(3):  # Retry up to 3 times
        try:
            response_video = requests.post(api_url, json=data_video)
            response_video.raise_for_status()
            result_video = response_video.json()
            if "result" not in result_video:
                with open(log_file, 'a', encoding='utf-8') as log:
                    log.write(f"Video publish failed for {title} (attempt {attempt + 1}): No 'result' in response: {json.dumps(result_video)}\n")
                time.sleep(5)
                continue
            with open(log_file, 'a', encoding='utf-8') as log:
                log.write(f"Uploaded {title} (name: {video_name}) to Odysee: {json.dumps(result_video)}\n")
            # Reflect all blobs and clean cache after successful upload
            reflect_and_clean_blobs(log_file)
            return True
        except Exception as e:
            with open(log_file, 'a', encoding='utf-8') as log:
                log.write(f"Video publish failed for {title} (attempt {attempt + 1}): {str(e)}\n")
            time.sleep(5)
    return False

def reflect_and_clean_blobs(log_file: str) -> None:
    """Reflect all saved blobs to distribute to the network, then clean the blob cache."""
    api_url = "http://localhost:5279"
    reflector_servers = [
        "reflector.lbry.com:5566",
        "lbryumx1.lbry.com:5566",
        "lbryumx2.lbry.com:5566",
        "blobcache-eu.odycdn.com:5567",
        "blobcache-eu.odycdn.com:5568",
        "blobcache-eu.odycdn.com:5569"
    ]

    # Step 1: List all finished blobs
    data_list = {
        "jsonrpc": "2.0",
        "method": "blob_list",
        "params": {"finished": True},
        "id": 1
    }
    try:
        response_list = requests.post(api_url, json=data_list)
        response_list.raise_for_status()
        result_list = response_list.json()
        if "result" not in result_list or "items" not in result_list["result"]:
            raise ValueError("Blob list failed or returned unexpected result.")
        blob_hashes = result_list["result"]["items"]
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"Found {len(blob_hashes)} finished blobs to reflect.\n")
    except Exception as e:
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"Failed to list blobs: {str(e)}\n")
        return

    if not blob_hashes:
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write("No blobs to reflect.\n")
    else:
        reflected_count = 0
        for reflector in reflector_servers:
            # Step 2: Try reflecting with current server
            data_reflect = {
                "jsonrpc": "2.0",
                "method": "blob_reflect",
                "params": {"blob_hashes": blob_hashes, "reflector_server": reflector},
                "id": 1
            }
            try:
                response_reflect = requests.post(api_url, json=data_reflect)
                response_reflect.raise_for_status()
                result_reflect = response_reflect.json()
                if "result" in result_reflect:
                    reflected_count = len(result_reflect["result"])
                    with open(log_file, 'a', encoding='utf-8') as log:
                        log.write(f"Successfully reflected {reflected_count} blobs using {reflector}.\n")
                    break  # Success, no need to try more
                else:
                    raise ValueError(f"Blob reflect failed with {reflector}.")
            except Exception as e:
                with open(log_file, 'a', encoding='utf-8') as log:
                    log.write(f"Failed to reflect blobs with {reflector}: {str(e)}\n")
        if reflected_count == 0:
            with open(log_file, 'a', encoding='utf-8') as log:
                log.write("Failed to reflect blobs with all alternative servers.\n")

    # Step 3: Clean blobs regardless of reflection success
    data_clean = {
        "jsonrpc": "2.0",
        "method": "blob_clean",
        "params": {},
        "id": 1
    }
    try:
        response_clean = requests.post(api_url, json=data_clean)
        response_clean.raise_for_status()
        result_clean = response_clean.json()
        if "result" in result_clean and result_clean["result"] is True:
            with open(log_file, 'a', encoding='utf-8') as log:
                log.write("Successfully cleaned blob cache to free local storage.\n")
        else:
            raise ValueError("Blob cleaning failed or returned unexpected result.")
    except Exception as e:
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"Failed to clean blobs: {str(e)}\n")

def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate YouTube content to Odysee.")
    parser.add_argument('--start-date', required=True, help="Earliest upload date (MM-DD-YYYY)")
    parser.add_argument('--end-date', default=datetime.date.today().strftime('%m-%d-%Y'), help="Latest upload date (MM-DD-YYYY), defaults to today")
    parser.add_argument('--content-type', choices=['videos', 'livestreams', 'shorts', 'all'], required=True, help="Content type to migrate")
    parser.add_argument('--temp-folder', required=True, help="Temporary folder for downloads")
    parser.add_argument('--cookies', default=None, help="Path to cookies.txt for authenticated access (optional)")
    parser.add_argument('--verbose', action='store_true', help="Enable verbose output for debugging")
    args = parser.parse_args()

    try:
        start_date = datetime.datetime.strptime(args.start_date, '%m-%d-%Y').date()
        end_date = datetime.datetime.strptime(args.end_date, '%m-%d-%Y').date()
    except ValueError:
        print("Error: Dates must be in MM-DD-YYYY format.")
        sys.exit(1)

    if end_date < start_date:
        print("Error: End date cannot be before start date.")
        sys.exit(1)
    if end_date > datetime.date.today():
        print(f"Warning: End date {end_date} is in the future, which may exclude most videos.")

    os.makedirs(args.temp_folder, exist_ok=True)
    log_file = "migration_log.txt"
    with open(log_file, 'w', encoding='utf-8') as log:
        log.write(f"Started migration on {datetime.datetime.now()} to Odysee\n")

    # Load or initialize video_log
    video_log_file = "video_log.json"
    try:
        with open(video_log_file, 'r', encoding='utf-8') as f:
            video_log = json.load(f)
    except FileNotFoundError:
        video_log = {}

    # Determine content types to fetch
    content_types = ['videos', 'livestreams', 'shorts'] if args.content_type == 'all' else [args.content_type]

    # Extract and filter videos
    video_dict = {}
    for ctype in content_types:
        video_dict.update(extract_youtube_content(YOUTUBE_CHANNEL_URL, ctype, start_date, end_date,
                                                  args.cookies, args.verbose, log_file, video_log))

    # Save updated video_log
    with open(video_log_file, 'w', encoding='utf-8') as f:
        json.dump(video_log, f, indent=4, ensure_ascii=False)

    # User confirmation with cancel option
    video_dict = confirm_videos(video_dict, log_file)

    # Sort videos by upload_date, oldest first
    videos_sorted = sorted(video_dict.items(), key=lambda x: x[1]['upload_date'])

    # Track successful and failed uploads
    successful_ids: List[str] = []
    failed_ids: List[str] = []

    # Process each video in sorted order
    for vid_id, info in videos_sorted:
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"Processing {info['title']} (ID: {vid_id})\n")

        # Check if claim already exists on Odysee before downloading
        video_name = sanitize_name(info['title'])
        if claim_exists(video_name, log_file):
            continue  # Skip download and upload, don't add to lists

        video_path = download_video(vid_id, args.temp_folder, args.cookies, log_file)
        if not video_path:
            with open(log_file, 'a', encoding='utf-8') as log:
                log.write(f"Download failed for {info['title']}\n")
            failed_ids.append(vid_id)
            continue

        success = upload_to_odysee(video_path, info['thumbnail'], info['title'], info['description'], ODYSEE_CHANNEL_NAME,
                                   ODYSEE_BID, log_file, info['duration'], info['upload_date'], info['type'], info.get('tags', []))
        if success:
            successful_ids.append(vid_id)
        else:
            failed_ids.append(vid_id)

        # Delete all related files
        try:
            # Find all files starting with vid_id
            related_files = glob.glob(os.path.join(args.temp_folder, f"{vid_id}*"))
            if not related_files:
                with open(log_file, 'a', encoding='utf-8') as log:
                    log.write(f"No files found to delete for {info['title']} (ID: {vid_id})\n")
            for file_path in related_files:
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                        with open(log_file, 'a', encoding='utf-8') as log:
                            log.write(f"Deleted file: {file_path}\n")
                    except PermissionError as e:
                        with open(log_file, 'a', encoding='utf-8') as log:
                            log.write(f"Failed to delete {file_path}: {e} (file may be in use)\n")
                    except Exception as e:
                        with open(log_file, 'a', encoding='utf-8') as log:
                            log.write(f"Failed to delete {file_path}: {e}\n")
        except Exception as e:
            with open(log_file, 'a', encoding='utf-8') as log:
                log.write(f"Error while attempting to delete files for {info['title']}: {e}\n")

    # Log completion and upload summaries
    with open(log_file, 'a', encoding='utf-8') as log:
        log.write(f"Completed migration on {datetime.datetime.now()}\n")
        log.write("Successful Uploads:\n")
        log.write(" ".join(successful_ids) + "\n" if successful_ids else "\n")
        log.write("Failed Uploads:\n")
        log.write(" ".join(failed_ids) + "\n" if failed_ids else "\n")
    print(f"Migration complete. See {log_file} for details.")

if __name__ == "__main__":
    main()