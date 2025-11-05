#!/bin/bash
set -e

# --- CONFIG ---
SERVICE_NAME="musicdownloadbot"

REPO="dcronauer1/musicdownloadbot"
BINARY_NAME="musicdownloadbot"
INSTALL_DIR="$(pwd)/$BINARY_NAME"
LOCAL_BINARY="$INSTALL_DIR/$BINARY_NAME"
TEMP_DIR="$INSTALL_DIR/temp"
VERSION_FILE="$TEMP_DIR/${REPO//\//_}_version.txt"

#Verify user is running as intended user
read -p "Are you sure you want this program to run as $USER? [y/N]: " TEMP
if [[ "$TEMP" =~ ^[Nn]$ ]]; then
    exit 1
fi

#Update installer.sh
read -p "Get most recent version of installer.sh? [y/N]: " TEMP2
if [[ "$TEMP2" =~ ^[Yy]$ ]]; then
    echo "Downloading latest installer..."
    
    # Get installer download URL from latest release (same method as binary)
    INSTALLER_URL=$(curl -s "https://api.github.com/repos/$REPO/releases/latest" \
        | grep "browser_download_url.*installer.sh\"" \
        | cut -d '"' -f 4)
    
    if [ -z "$INSTALLER_URL" ]; then
        echo "Installer.sh not found in latest release. Continuing with current version."
    else
        TMP_SCRIPT=$(mktemp)
        curl -L "$INSTALLER_URL" -o "$TMP_SCRIPT"
        chmod +x "$TMP_SCRIPT"
        mv "$TMP_SCRIPT" "$0"
        echo "Installer updated successfully. Please run the script again."
        exit 0
    fi
fi

# --- CHECK PERMISSIONS ---
if [ ! -w "$PWD" ]; then
    echo "You do not have write permissions in $(pwd). Please run in a directory you own."
    exit 1
fi

# --- INSTALL REQUIRED PACKAGES ---
echo "Installing required packages..."
sudo apt update
sudo apt install -y python3 python3-pip ffmpeg atomicparsley python3-mutagen

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
echo ""
read -p "Do you want to create a separate user for copying music over ssh? This will generate an SSH key for you, and place it in authorized_keys for that user. This is recommended, as the user pulling music should only have read access to the music. This will install openssh client and server. [y/N]: " CREATE_USER
if [[ "$CREATE_USER" =~ ^[Yy]$ ]]; then
    read -p "Enter username for music user: " MUSIC_USER

    if id "$MUSIC_USER" >/dev/null 2>&1; then
        echo "User $MUSIC_USER already exists."
    else
        sudo adduser --disabled-password --gecos "" "$MUSIC_USER"
        echo "User $MUSIC_USER created."
    fi

    # --- GENERATE SSH KEY ---
    sudo apt install -y openssh-client openssh-server

    SSH_DIR="/home/$MUSIC_USER/.ssh"
    sudo mkdir -p "$SSH_DIR"
    # Set proper ownership and permissions before generating keys
    sudo chown -R "$MUSIC_USER:$MUSIC_USER" "$SSH_DIR"
    sudo chmod 700 "$SSH_DIR"
    
    # Generate SSH key as the music user
    sudo -u "$MUSIC_USER" ssh-keygen -t ed25519 -f "$SSH_DIR/id_ed25519" -N ""
    sudo -u "$MUSIC_USER" bash -c "cat $SSH_DIR/id_ed25519.pub >> $SSH_DIR/authorized_keys"
    sudo chmod 600 "$SSH_DIR/authorized_keys"

    # Copy private key for user convenience
    sudo cp "$SSH_DIR/id_ed25519" "$INSTALL_DIR/ssh_private_key"
    sudo chown $USER "$INSTALL_DIR/ssh_private_key"
    chmod 600 "$INSTALL_DIR/ssh_private_key"
    echo -e "\n\nPrivate key copied to $INSTALL_DIR/ssh_private_key. Add this key to your devices and delete it when done."
    
    # Clean up the original keys from the music user's .ssh directory
    sudo rm "$SSH_DIR/id_ed25519"
    sudo rm "$SSH_DIR/id_ed25519.pub"
    echo "Ensure SSH is configured, The ssh port you use is forwarded, etc."
    echo "Recommended /etc/ssh/sshd_config configs:"
    echo -e "Port 2022 (Recommended to not use default port)\nPermitRootLogin no\nPubkeyAuthentication yes\nPasswordAuthentication no\nAuthorizedKeysFile .ssh/authorized_keys"
    echo "Remember to run sudo systemctl restart ssh"
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
RestartSec=10
StartLimitInterval=100
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
EOL

    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME.service"

    echo -e "\n\nService $SERVICE_NAME installed. It will run once on start to generate config, then stop."
    echo "If config is generated, edit config.json, then start service manually if installed:"
    echo "sudo systemctl start $SERVICE_NAME"
    echo "To see logs, run:"
    echo "journalctl -u $SERVICE_NAME"
fi

# --- RUN ONCE TO GENERATE CONFIG ---
CONFIG_FILE="$INSTALL_DIR/config.json"

if [ -f "$CONFIG_FILE" ]; then
    echo "Config file already exists at $CONFIG_FILE."
    echo "Skipping initial config generation."
else
    echo "Running $BINARY_NAME once to generate config..."
    "$LOCAL_BINARY" || true
fi