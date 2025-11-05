# Music Download Bot
This program allows you to download youtube videos/playlists as songs/albums, with metadata options, through Discord

# Features:
* Download music from YouTube as .opus.  
  * Download playlists as either separate or single file(s) using type = playlist or type = album, respectively
  * .m4a is partially supported.
* Add title, author, album title, tags, and more ~~(year, date)~~  
* Store a list of authors and tags. 
  * If names are very close, it will be stored as the same artist/tag.
    * Todo: add config to disable this
* Add Album/Song covers from musicbrainz database

# How To Setup:
This program has only been tested on ubuntu-server, but should work on any linux-based system with the apt package manager  
Download and run "installer.sh" from the newest release  
set up directories accordingly in config.json

## Environment Setup:
### On Phone:
* Get foobar2000 or musicolet
  * Both are supported
  * Foobar2000 will automatically split files with timestamps into separate songs
  * Musicolet needs a seperate txt file for timestamps (which is generated).  
    * ~~Need to enable timestamp file generation in config.~~ Also need to tell musicolet to use .LRC file. Will auto-apply for each song.
* Get FolderSync app. Set up with ssh keys to auto sync music to phone.
    * Unknown if there is an IOS alternative.

### On Client PC(s):
* Foobar2000 recommended  
* Will add sync script in the future

## How to set up FolderSync with SSH

### 1. Prepare the Private Key
- Get the private key (`musicdownloadbot/ssh_private_key` if generated with `installer.sh`)
- Move it to your phone
- **Important**: Delete this file from the server after moving it

### 2. Create New SFTP Account in FolderSync
- **Username**: The user you created with `installer.sh` (not the user running the program)
- **Address**: Your public IPv4 address
- **Port**: The port defined in `/etc/ssh/sshd_config`
- **Private Key File**: `ssh_private_key`

### 3. Create Folder Pair
- **Sync Type**: "To right folder"
- **Left Account**: SFTP user created in step 2
- **Folder**: Music folder location (default /var/music)
- **Right Account**: Local folder of your choosing (recommended: `/Music`)
- **Scheduling**: Set up as needed (example: every hour)
- Recommended Sync Options:
  - Enable "Sync deletions"
  - Overwrite old files: Always
  - If both local and remote file have been modified: Use left file

# Notes
* Soundcloud "works"; however, without a Soundcloud Go subscription, downloads are heavily compressed.
  * Resource for adding soundcloud go token: https://www.reddit.com/r/youtubedl/wiki/howdoidownloadhighqualityaudiofromsoundcloud/
* Default cover size can be "250”, “500”, “1200”. Anything else will default to max size, which is often much larger than 1200, so is not recommended.

# Config File:
TODO
keep_perms_consistent:  

group: user group to set music files to. Default uses same group as user running program 


# Commands:
TODO: add more
## Download:
### Types:
- Default: Song: behaves as expected.
- album_playlist: downloads a playlist into a single file, where each song is timestampped
    - Note: no album cover will be downloaded for this option
    - `/replace thumbnail title:{title} usedatabase:True` should be used after
    - "album" is also valid
- playlist: downloads a playlist, but each song is an individual file inside a sub directory
    - Album covers are downloaded for each song individually
    - Track numbers are excluded if excludetracknumsforplaylist is True


# Dependencies:
https://github.com/yt-dlp/yt-dlp