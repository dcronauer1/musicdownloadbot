# how to:
sudo apt install python3 python3-pip samba ffmpeg atomicparsley python3-mutagen 
*sudo apt install npm #used for freyr-js
*    npm install -g freyr
*    https://github.com/miraclx/freyr-js
get runable for yt-dlp: https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#usage-and-options
set up samba (optional)



set up directories accordingly in config.json

# on phone:
get foobar2000 or musicolet
    both are "supported"
    Foobar2000 will automatically split files with timestamps into separate songs
    musicolet needs a seperate txt file for timestamps (which is generated).
        need to enable timestamp file generation in config. also need to tell musicolet to use .LRC file. will auto-apply for each song
set up foldersync with sftp or smb2 to auto copy (recommended sftp)

# on client pc(s):
foobar2000 recommended
get rsync & cwRsync (latter is for windows)
    can sync music over sftp

# common commands:
ffmpeg -i [name].m4a


# features:
download youtube videos as .m4a (ALAC so lossless)
add title, author, album title, tags, and more (year, date)
store a list of authors and tags so if names are very close, it will be stored as the same artist/tag.
    user confirmations for adding new authors/tags