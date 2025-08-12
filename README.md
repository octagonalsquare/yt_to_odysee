# YouTube to Odysee Migrator

A Python script to migrate YouTube content over to Odysee.

Obviously, you need Python. This should work on any version 3.8 or newer, but I can't guarantee anything other than 3.12 as that is what I used it with.

The script is set to prefer 1080p video, or lower if 1080p is not available. It will also use the highest framerate it can get, not allowing lower than 30. I added the 1080p limitation as in all testing, even manual uploads, videos higher than 1080p seem to have severe loading issues. I was unable to load them on mobile at all and on PC they would stop about 10 minutes in and never load the rest, eventually just giving up.

> **WARNING**: Currently there seems to be an issue with shorts where once they are uploaded, they only play audio on iOS. I cannot confirm if this happens on Android, and it doesn't happen on PC. I have reached out to Odysee support to see if there is something I can do to fix this. You might try uploading just one short and see if it works for you before trying to migrate large numbers, save yourself the trouble of deleting them all.

## Setup:
(Mostly Windows but gave Linux/Mac steps where I knew what they were.)
### Visual C++ Build Tools
1. One of the Python packages you have to install requires you to have Visual C++ Build Tools version 13 or newer installed. You can get it [here](https://visualstudio.microsoft.com/visual-cpp-build-tools/).

2. Go through the installation process. Once you get to the screen where you can view installed versions, click "Modify". From there, check "Desktop Development with C++" and then clickt he install button in the bottom right.

### Virtual Environment
1. Create a Python virtual environment in the desired folder:
```powershell
python -m venv ./yt_to_odysee
```
2. Either download the zipfile of this repo and extract the contents into the root of the new folder, or use git cli to clone it into the folder.

### LBRY
1. Download [LBRY](https://lbry.com/get). This is the desktop app for the decentralized video sharing backend of Odysee. Uploading to it also uploads to Odysee.

2. Run the app and log in. If you don't have an account, you can create one [here](https://odysee.com/$/invite/@OctagonalSquare:0). Then use that to log in, and create a channel for your content. If you have multiple YouTube channels, you can add multiple channels. You will need the channel names later.

3. Download [lbrynet](https://github.com/lbryio/lbry-sdk/releases) for your system. Extract the file into the virtual enviroment folder.

4. Make sure you have enough LBC! Each video you migrate will take 0.001 LBC. This isn't a ton, and you can easily get LBC by doing tasks or from people watching, donating, or joining via your invite link. You get 1 LBC when you join, so if you're processing less than 1000 videos, you should be good. But CHECK YOUR WALLET in the top right as sometimes your coins are held for boosting purposes, meaning you don't have access to all of them. This amount goes up as you add more videos, and down as you delete them. If someone joins via your invite, you get another LBC, and as far as I've seen, it doesn't go to boosting content so you should have it fully available. It is a good way to get your friends to join, or your audience if you're big enough!
> LBC is apparently being replaced by AR at some point, but right now the system still uses LBC. If changes need to be made when AR is the default, I'll try to update this.

### Code
1. Open migrate_to_odysee.py in a text or code editor. I will assume you are using VS Code from this point forward.

2. On line 17, replace the word **REPLACE** with the URL of your YouTube channel, surrounded by quotation marks. Should look roughly like this:
```python
YOUTUBE_CHANNEL_URL: str = "https://www.youtube.com/@ChannelName"
```

3. On line 16, replace the word **REPLACE** with the channel name for your Odysee channel, including the @, and excluding the :[Number] at the end. Should look roughly like this:
```python
ODYSEE_CHANNEL_NAME: str = REPLACE
```
> NOTE: This second one is *technically* optional. However, it is best to ensure you actually have a channel to add the videos to.

4. Optionally, on line 80, if you want to limit the number of videos the script processes at one time, you can uncomment this line (CTRL-/ in most code editors, or just remove the # and the following space at the beginning of the line). Then replace the 1-100 in that line with whichever videos you want to get. So if you want to grab the first 100 videos, don't change it. If you want the next 200, you'd do 101-300. I would leave this uncommented for this first run.

### Running
1. In VS Code's terminal, or the CMD/Terminal of your operating system, make sure you're in the root directory of the virtual environment. Type in:
    #### Windows
    ```powershell
    ./Scripts/activate.bat
    ```
    #### Linux/Mac/POSIX
    ```bash
    source <venv>/bin/activate
    ```

2. Install required Python packages by running:
```bash
pip install -r requirements.txt
```
> NOTE: pip may complain about a certain package's version (likely libtorrent). Manually run `pip install [package name]` for just that package without a version number. The package that needs it thinks it has to have a specific version, but it works with the current one just fine.

3. Install an extension to get a copy of your internet cookies. For [Chrome/Brave/Chromium](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc?pli=1) or for [Firefox](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/).

4. Go open a private browser window. Navigate to https://www.youtube.com. Once it loads, change the URL to https://www.youtube.com/robot.txt. Then click the extension and click "Export As". Name it whatever you want but save it in the root of your virtual environment. I'll assume the name is "cookies.txt". Now close the browser window so you don't change the session. This should create a perpetual cookie file. YouTube likes to change the cookies in your session frequently but this bypasses it. If it doesn't work, navigate to YT normally and get the cookie file that way. If done the second way, you will need to re-make the cookies file again every so often.

5. Run the following command to start the lbrynet server:
```bash
./lbrynet.exe start
```

> NOTE: If it fails to start, make sure the desktop LBRY app is not running. Check your background apps tray and right click and click "Exit" to close it. You can open it back up once this is running.

6. You can now run the migration script. Below you will find all the command arguments and how to use them, but here is a recommended command for your first run:
```bash
python migrate_to_odysee.py --start-date 01-01-2015 --end-date 08-03-2025 --content-type all --temp-folder ./temp/ --cookies ./cookies.txt
```
- Replace the start-date with a day before your channel was created/first video was uploaded, and the end-date with today's date.
- Press enter and wait. This will take a while depending on how many videos you have. This will create a file called "video_log.json" which will store the required data for every video on your channel. It will not download the videos yet, but drastically reduces processing time on future runs and how many calls are made to YouTube, so DO NOT delete that file unless you want to do this again.
- Each video will take about 1-3 minutes to process, so leave it running and relax for a bit. Once it is done, you'll get a list of all your videos in the command line. From here, you can do two things:
    1. Type "cancel" to end right there now that you have your video data ready.
    2. If you want to start processing 100% of all videos, press "Enter". I do not recommend this for large channels!
- Read below for recommended process from here.

### Migrating
- The command-line options are as follows:

| Command | Options | Description |
| ------- | ------- | ----------- |
| --start-date | Any date | **REQUIRED** Earliest date you want to get videos from. MM-DD-YYYY format. |
|--end-date | Any date | Latest upload date you want to get videos from (Defaults to today). MM-DD-YYYY format. |
| --content-type | videos, livestreams, shorts, or all | **REQUIRED** What content type to migrate. Videos is the content in the videos tab on your channel, livestreams are the content from the live tab, and shorts are from the shorts tab. All is all three. |
| --temp-folder | | **REQUIRED** Where to store videos temporarily between download and upload. They will be deleted from this folder once they are uploaded. |
| --cookies | | Path to cookies.txt for authenticated access. (Technically optional, but not really) |
| --verbose || More detailed command-line output. Good for debugging related to yt-dlp |

#### Creating Your Command
- Start with `python migrate_to_odysee.py`
- Decide what type of content you want to migrate first. If you have a small channel, then you can probably do all without much issue. But the longer the script runs, the more likely you are to encounter issues. Add `--content-type [type]`
- Decide what upload dates you want to process first. Again, small channels can likely do from channel creation to today. Add `--start-date [MM-DD-YYYY]` and `--end-date [MM-DD-YYYY]`
- Add your temp folder `--temp-folder ./temp/` is what I recommend. Keeps everything within the virtual environment, but feel free to put this on a secondary drive or something.
- Add your cookies `--cookies ./cookies.txt` assuming you named it cookies.txt and put it in your root folder.
- Optionally add `--verbose` if you want to see all the details as it runs.

- Press "Enter" and it will run. If you already ran it as above to pre-fetch the video_log.json file, it should very quickly return a list. From here, you can provide a list of YouTube video IDs that you DON'T want to migrate. These can be ones you just don't care to migrate or ones that you already migrated previously. The list should be space-delimited.
> NOTE: You don't HAVE to provide this list for previously migrated videos that you migrated using this tool. Assuming you have changed nothing within Odysee about the video after it was migrated, the script will detect that the video it is working on is already on your Odysee channel and will skip it. In over 100 videos that I uploaded after adding the skip feature, no repeats were made when re-running the script.

- If you give it a list of IDs, press "Enter". You can do this as many times as needed if you have multiple lists to remove. Once you're done removing items, leave the text input blank and press "Enter" to start migrating.

The script will begin processing one video at a time. It will download the video and thumbnail and then attempt to upload it to Odysee via the local lbrynet server. If the server stops, it will fail, but will try on every video until it finishes, so make sure the command line for the server stays open and that you don't turn off all your monitors as that will cause the server to sleep or lose connection.

Once the script is done, you will have a migration_log.txt file that will show what happened. It will warn you about videos that failed to download or upload. If a video was already migrated, you'll see an entry saying "Valid claim exists..." and that it skipped that video.

The videos are uploaded, roughly, in order of upload/stream on YouTube, though sometimes they are off a bit. But the upload date from YouTube is used on Odysee, so a video uploaded to YouTube on January 1st, 2025 will appear as that date on Odysee as well.

To retry uploading failed videos, the end of the migration_log.txt should have 2 lists of video IDs: **Successful Uploads** and **Failed Uploads**. Copy the space separated list of IDs in the successful uploads list, click into the command line interface where you last ran the script, press the up arrow key, and tap "Enter". Then, when given the list of videos it found, click into the command line again and press CTRL-V to paste and then press "Enter" again. This should remove all the videos from the list that already successfully uploaded. As noted above, you don't HAVE to do this, but it reduces processing time as the script won't have to check to see if they were already uploaded.

## Troubleshooting
If several videos at the end of the log failed, it likely means one of a few things:
1. If it says "Download failed":
    - Check your network connection as you may have just lost internet.
    - Check the command line. You may see entries related to yt-dlp failing to connect. It is possible the traffic was blocked by YouTube, especially if you had processed a TON of videos.
2. If it says "Video publish failed", then check to make sure your lbrynet server is still running and that you haven't run out of space on whatever drive you configured for storing blobs.

You may run into errors from yt-dlp related to PO tokens, or SABR formats. These can either cause the downloads to fail or cause the videos to only download in low quality formats. If this happens, [check out this page](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide) for guides on how to solve it. It is too in-depth for me to explain. You will add the string it wants you to create to the list on line 266.

> I have added two functions that should make the below information moot. The idea is that, rather than letting the blobs sit there, after each video is fully uploaded and the blobs have been generated, they will be automatically reflected to various servers. Then, once that is done, they are deleted to make room for the next video. So far, this has not worked on my local machine. It should, according to the documentation for the lbrynet sdk. Due to this and some logs from lbrynet, I've determined my router is blocking my PC from making the right connections. You may need to set up port forwarding to allow this to work, or your system may let it work automatically. The log will indicate if this fails or succeeds. I would do a testrun by uncommenting line 80 and setting the value to "1-2" or a similar low number so you can test just a few videos and see if it will delete the blobs. If I can get this to work consistently, I will update this README.

On that note:
- LBRY stores the videos locally on your C drive ([see here for how to move it to another drive](https://lbry.com/faq/how-to-change-lbry-blob-files)). The videos are stored as blobs and slowly synced across the blockchain for further decentralization. This means that as you're uploading, you do slowly fill your drive, even though the videos get deleted after upload. This can be a problem. The solution is be slower.
1. Run the script for however many videos you can comfortably handle, leaving drive space so you don't cause issues.
2. Stop running the script and let the lbrynet server keep running.
3. Login to Odysee and start watching your videos on your PC and your phone or other devices.
4. This will, I think, help speed up the process of distributing the blobs across different nodes of the blockchain. If you have a ton of followers, create an invite link for Odysee, get them to sign up and start watching videos. 
5. If you get to where you can shut down the server and LBRY app and still watch the videos on other devices, then you're good! That means the videos are fully distributed and decentralized from your system.
6. Once that happens, you can go to your lbrynet folder and delete the blobs. [Check this page](https://lbry.com/faq/lbry-directories) to see where that is.
7. So if you have the space to store all your files, then I'd say just process them all and leave your PC running for a few days after if you can. If you have a ton of videos, it will take a few days anyway, and the first videos should be distributed properly by the time the rest are uploaded.