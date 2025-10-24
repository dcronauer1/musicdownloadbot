#!/bin/bash
set -e

# --- CONFIG ---
REPO="dcronauer1/musicdownloadbot"
BINARY_NAME="musicdownloadbot"
INSTALL_DIR="$(pwd)/$BINARY_NAME"
LOCAL_BINARY="$INSTALL_DIR/$BINARY_NAME"
SERVICE_NAME="musicdownloadbot"
TEMP_DIR="$INSTALL_DIR/temp"
VERSION_FILE="$TEMP_DIR/${REPO//\//_}_version.txt"

# --- CHECK PERMISSIONS ---
if [ ! -w "$PWD" ]; then
    echo "You do not have write permissions in $(pwd). Please run in a directory you own."
    exit 1
fi

# --- INSTALL REQUIRED PACKAGES ---
echo "Installing required packages..."
sudo apt update
sudo apt install -y python3 python3-pip samba ffmpeg atomicparsley python3-mutagen

# --- CREATE INSTALL DIRS ---
mkdir -p "$INSTALL_DIR"
mkdir -p "$TEMP_DIR"

# --- DOWNLOAD LATEST RELEASE ---
echo "Fetching latest release from $REPO..."
LATEST_URL=$(curl -s "https://api.github.com/repos/$REPO/releases/latest" \
    | grep "browser_download_url.*$BINARY_NAME\"" \
    | cut -d '"' -f 4)

if [ -z "$LATEST_URL" ]; then
    echo "Failed to find latest release."
    exit 1
fi

LATEST_VERSION=$(curl -s "https://api.github.com/repos/$REPO/releases/latest" \
    | grep '"tag_name":' | head -n1 | cut -d '"' -f 4)

echo "Downloading $BINARY_NAME version $LATEST_VERSION..."
TMP_FILE=$(mktemp)
curl -L "$LATEST_URL" -o "$TMP_FILE"
chmod +x "$TMP_FILE"
mv "$TMP_FILE" "$LOCAL_BINARY"

# --- WRITE VERSION FILE ---
echo "$LATEST_VERSION" > "$VERSION_FILE"
chmod 644 "$VERSION_FILE"
echo "Installed $BINARY_NAME version $LATEST_VERSION to $LOCAL_BINARY"

# --- CREATE SYSTEM USER (OPTIONAL) ---
read -p "Do you want to create a separate user for copying music over ssh? This will generate an SSH key for you. [y/N]: " CREATE_USER
if [[ "$CREATE_USER" =~ ^[Yy]$ ]]; then
    read -p "Enter username for music user: " MUSIC_USER

    if id "$MUSIC_USER" >/dev/null 2>&1; then
        echo "User $MUSIC_USER already exists."
    else
        sudo adduser --disabled-password --gecos "" "$MUSIC_USER"
        echo "User $MUSIC_USER created."
    fi

    # --- GENERATE SSH KEY ---
    SSH_DIR="/home/$MUSIC_USER/.ssh"
    sudo mkdir -p "$SSH_DIR"
    sudo -u "$MUSIC_USER" ssh-keygen -t ed25519 -f "$SSH_DIR/id_ed25519" -N ""
    sudo -u "$MUSIC_USER" bash -c "cat $SSH_DIR/id_ed25519.pub >> $SSH_DIR/authorized_keys"
    sudo chown -R "$MUSIC_USER:$MUSIC_USER" "$SSH_DIR"
    sudo chmod 700 "$SSH_DIR"
    sudo chmod 600 "$SSH_DIR/authorized_keys"

    # Copy private key for user convenience
    cp "$SSH_DIR/id_ed25519" "$INSTALL_DIR/ssh_private_key"
    chmod 600 "$INSTALL_DIR/ssh_private_key"
    echo "Private key copied to $INSTALL_DIR/ssh_private_key. Add this key to your devices and delete it when done."
    sudo rm "$SSH_DIR/id_ed25519"
    sudo rm "$SSH_DIR/id_ed25519.pub"
    echo "Ensure SSH is configured: disable password auth, port forwarding, etc."
fi

# --- SET UP SYSTEMD SERVICE ---
read -p "Do you want to set up the musicdownloadbot systemd service? [y/N]: " SETUP_SERVICE
if [[ "$SETUP_SERVICE" =~ ^[Yy]$ ]]; then
    RUN_USER=$(logname 2>/dev/null || echo "$USER")
    SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
    echo "Creating systemd service $SERVICE_NAME..."
    sudo bash -c "cat > $SERVICE_FILE" <<EOL
[Unit]
Description=MusicDownloadBot Service
After=network.target

[Service]
Type=simple
User=$RUN_USER
ExecStart=$LOCAL_BINARY
WorkingDirectory=$INSTALL_DIR
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOL

    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME.service"
    echo "Service $SERVICE_NAME installed. It will run once on start to generate config, then stop."
fi

# --- RUN ONCE TO GENERATE CONFIG ---
CONFIG_FILE="$INSTALL_DIR/config.json"

if [ -f "$CONFIG_FILE" ]; then
    echo "Config file already exists at $CONFIG_FILE."
    echo "Skipping initial config generation."
else
    echo "Running $BINARY_NAME once to generate config..."
    "$LOCAL_BINARY" || true
    echo "If config was generated, edit config.json, then start service manually if installed:"
    echo "sudo systemctl start $SERVICE_NAME"
fi
