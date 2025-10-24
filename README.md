# How To Setup:
`sudo apt install python3 python3-pip samba ffmpeg atomicparsley python3-mutagen`  
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

# Features:
* Download music from YouTube as .opus. .m4a is partially supported.  
  * Download playlists as either separate or single file(s) using type = playlist or type = album, respectively
* Add title, author, album title, tags, and more ~~(year, date)~~  
* Store a list of authors and tags. 
  * If names are very close, it will be stored as the same artist/tag.
    * Todo: add config to disable this
* Add Album/Song covers from musicbrainz database

# Notes
* Soundcloud "works"; however, without a Soundcloud Go subscription, downloads are heavily compressed.
  * Resource for adding soundcloud go token: https://www.reddit.com/r/youtubedl/wiki/howdoidownloadhighqualityaudiofromsoundcloud/
* Default cover size can be "250”, “500”, “1200”. Anything else will default to max size, which is often much larger than 1200, so is not recommended.

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