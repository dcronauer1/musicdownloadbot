#!/bin/bash
set -e

# --- CONFIG ---
REPO="dcronauer1/musicdownloadbot"
BINARY_NAME="musicdownloadbot"
INSTALL_DIR="$(pwd)/$BINARY_NAME"  #current working directory + musicdownloadbot folder
LOCAL_BINARY="$INSTALL_DIR/$BINARY_NAME"

# --- CREATE INSTALL DIR ---
mkdir -p "$INSTALL_DIR"

# --- GET LATEST RELEASE INFO ---
LATEST_URL=$(curl -s "https://api.github.com/repos/$REPO/releases/latest" \
              | grep "browser_download_url.*$BINARY_NAME\"" \
              | cut -d '"' -f 4)

if [ -z "$LATEST_URL" ]; then
    echo "Failed to find latest release."
    exit 1
fi

# --- DOWNLOAD AND UPDATE ---
TMP_FILE=$(mktemp)
echo "Downloading latest musicdownloadbot..."
curl -L "$LATEST_URL" -o "$TMP_FILE"
chmod +x "$TMP_FILE"

# Move to install dir
mv "$TMP_FILE" "$LOCAL_BINARY"
echo "Installed $BINARY_NAME to $LOCAL_BINARY"

# --- RUN ---
echo "Running $BINARY_NAME..."
"$LOCAL_BINARY"
