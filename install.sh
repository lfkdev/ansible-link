#!/usr/bin/env bash
# info: github.com/lfkdev/ansible-link

set -e

ANSIBLE_LINK_VERSION="2.1.1"
INSTALL_DIR="/opt/ansible-link"
TEMP_DIR="/tmp/ansible-link-install$RANDOM"
VENV_DIR="$INSTALL_DIR/venv"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')][$1] $2"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
       log "ERROR" "This script must be run as root" 
       exit 1
    fi
}

check_existing_installation() {
    if [[ -d "$INSTALL_DIR" ]]; then
        read -p "ansible-link is already installed. Do you want to reinstall? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "INFO" "Installation cancelled."
            exit 0
        fi
    fi
}

check_systemd() {
    if ! pidof systemd &>/dev/null; then
        log "INFO" "systemd not detected"
        return 1
    fi
}

install_dependencies() {
    log "INFO" "Installing dependencies..."
    apt-get update
    apt-get install -y python3 python3-venv python3-pip unzip
}

download_ansible_link() {
    log "INFO" "Downloading ansible-link..."
    mkdir -p "$TEMP_DIR"
    wget "https://github.com/lfkdev/ansible-link/releases/download/v${ANSIBLE_LINK_VERSION}/ansible-link-${ANSIBLE_LINK_VERSION}.zip" -O "$TEMP_DIR/ansible-link.zip"
    unzip -o "$TEMP_DIR/ansible-link.zip" -d "$TEMP_DIR"
}

install_ansible_link() {
    log "INFO" "Installing ansible-link..."
    mkdir -p "$INSTALL_DIR"
    mv "$TEMP_DIR/config.yml" "$TEMP_DIR/ansible_link.py" "$TEMP_DIR/webhook.py" "$TEMP_DIR/version.py" "$INSTALL_DIR/"
}

setup_venv() {
    log "INFO" "Setting up virtual environment..."
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
}

install_python_requirements() {
    log "INFO" "Installing Python requirements in virtual environment..."
    "$VENV_DIR/bin/pip" install -r "$TEMP_DIR/requirements.txt"
}

cleanup() {
    log "INFO" "Cleaning up..."
    rm -rf "$TEMP_DIR"
}

detect_ansible() {
    ANSIBLE_PATH=$(which ansible 2>/dev/null || echo "")
    if [[ -z "$ANSIBLE_PATH" ]]; then
        log "ERROR" "Ansible not found. Please install Ansible before continuing."
        exit 1
    fi

    if [[ -d "/etc/ansible" ]]; then
        ANSIBLE_DIR="/etc/ansible"
    else
        log "ERROR" "Could not find /etc/ansible directory. Please ensure Ansible is correctly installed."
        exit 1
    fi
}

update_config() {
    log "INFO" "Updating configuration..."
    sed -i "s|^playbook_dir:.*|playbook_dir: '$ANSIBLE_DIR'|" "$INSTALL_DIR/config.yml"
    sed -i "s|^inventory_file:.*|inventory_file: '$ANSIBLE_DIR/hosts'|" "$INSTALL_DIR/config.yml"
}

setup_service() {
    log "INFO" "Setting up systemd service..."
    cat > /etc/systemd/system/ansible-link.service <<EOL
[Unit]
Description=Ansible Link Service
After=network.target

[Service]
ExecStart=$VENV_DIR/bin/python3 $INSTALL_DIR/ansible_link.py
WorkingDirectory=$INSTALL_DIR
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOL

    systemctl daemon-reload
    systemctl enable ansible-link.service
    systemctl start ansible-link.service
}

main() {
    log "INFO" "Preparing to install ansible-link version $ANSIBLE_LINK_VERSION..."

    download_ansible_link

    echo "This script will install (if not already) the following:"
    echo "- Python 3, python3-venv, pip"
    echo "- ansible-link in $INSTALL_DIR"
    echo "- A systemd service for ansible-link"
    
    read -p "Do you want to proceed with the installation? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "INFO" "Installation cancelled."
        cleanup
        exit 0
    fi

    check_root
    check_existing_installation
    check_systemd
    install_dependencies
    install_ansible_link
    setup_venv
    install_python_requirements
    detect_ansible
    update_config
    setup_service
    cleanup

    log "INFO" "Ansible-Link has been installed and configured. ✔"
    log "INFO" "The service is running and will start automatically on boot. ✔"
    log "INFO" "You can check the status with: systemctl status ansible-link. ✔"
    log "WARN" "Ansible user defaults to root. ⚠"
    log "INFO" "Please check the configuration and if needed change the default values in $INSTALL_DIR/config.yml. ⚠" 
}

main