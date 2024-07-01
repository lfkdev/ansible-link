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

display_header() {
    cat << "EOF"
    _____         _ _   _         __    _     _
   |  _  |___ ___|_| |_| |___ ___|  |  |_|___| |_
   |     |   |_ -| | . | | -_|___|  |__| |   | '_|
   |__|__|_|_|___|_|___|_|___|   |_____|_|_|_|_,_|
EOF
    echo "   $ANSIBLE_LINK_VERSION | github.com/lfkdev/ansible-link"
    echo
}

get_latest_version() {
    LATEST_VERSION=$(curl -s https://api.github.com/repos/lfkdev/ansible-link/releases/latest | grep -Po '"tag_name": "\K.*?(?=")' | sed 's/^v//')
    if [[ -z "$LATEST_VERSION" ]]; then
        log "ERROR" "Failed to fetch the latest version. Using default version $ANSIBLE_LINK_VERSION."
    else
        ANSIBLE_LINK_VERSION="$LATEST_VERSION"
        log "INFO" "Latest version is $ANSIBLE_LINK_VERSION."
    fi
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
       log "ERROR" "This script must be run as root"
       exit 1
    fi
}

check_existing_installation() {
    if [[ -d "$INSTALL_DIR" ]]; then
        read -p "ansible-link is already installed. Do you want to reinstall? This will delete $INSTALL_DIR. (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log "INFO" "Stopping ansible-link service..."
            if systemctl list-units --full -all | grep -Fq 'ansible-link.service'; then
                systemctl stop ansible-link
                systemctl disable ansible-link
                log "INFO" "ansible-link service stopped and disabled."
            fi
            log "INFO" "Removing existing installation..."
            if [[ -n "$INSTALL_DIR" ]]; then
                rm -rf "${INSTALL_DIR:?}"
            fi
        else
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
    apt-get update -qq > /dev/null
    apt-get install -y -qq python3 python3-venv python3-pip unzip > /dev/null
}

download_ansible_link() {
    log "INFO" "Downloading ansible-link..."
    mkdir -p "$TEMP_DIR"
    wget -q "https://github.com/lfkdev/ansible-link/releases/download/v${ANSIBLE_LINK_VERSION}/ansible-link-${ANSIBLE_LINK_VERSION}.zip" -O "$TEMP_DIR/ansible-link.zip"
    unzip -o "$TEMP_DIR/ansible-link.zip" -d "$TEMP_DIR"
}

install_ansible_link() {
    log "INFO" "Installing ansible-link..."
    mkdir -p "$INSTALL_DIR"
    mv "$TEMP_DIR"/*.py "$TEMP_DIR"/*.yml "$INSTALL_DIR/"
}
setup_venv() {
    log "INFO" "Setting up virtual environment..."
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
}

install_python_requirements() {
    log "INFO" "Installing Python requirements in virtual environment..."
    "$VENV_DIR/bin/pip" install --upgrade pip --quiet
    "$VENV_DIR/bin/pip" install 'importlib-metadata<6.3,>=4.6' --quiet # importlib ubuntu 22 workaround
    "$VENV_DIR/bin/pip" install -r "$TEMP_DIR/requirements.txt" --quiet
    "$VENV_DIR/bin/pip" install gunicorn --quiet
}

cleanup() {
    log "INFO" "Cleaning up..."
    if [[ -d "$TEMP_DIR" ]]; then
        rm -r "${TEMP_DIR:?}"
    fi
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
ExecStart=$VENV_DIR/bin/gunicorn --workers 1 --bind unix:$INSTALL_DIR/ansible_link.sock -m 007 wsgi:application
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

check_os_version() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        if [[ "$ID" == "ubuntu" && "$VERSION_ID" < "16.04" ]]; then
            log "ERROR" "Ubuntu version must be at least 16.04. Detected version: $VERSION_ID"
            exit 1
        elif [[ "$ID" == "debian" && "$VERSION_ID" < "9" ]]; then
            log "ERROR" "Debian version must be at least 9. Detected version: $VERSION_ID"
            exit 1
        elif [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
            log "ERROR" "Unsupported OS. Only Ubuntu and Debian are supported."
            exit 1
        fi
    else
        log "ERROR" "Cannot determine OS version. /etc/os-release not found."
        exit 1
    fi
}

main() {
    echo
    check_os_version
    get_latest_version
    detect_ansible
    display_header
    echo "This script will ensure your system is set up with the following components:"
    echo "1. Python 3, python3-venv, and pip"
    echo -e "2. Ansible-Link installed in the directory: \e[32m$INSTALL_DIR\e[0m"
    echo "3. A SystemD service for Ansible-Link utilizing Gunicorn"
    echo
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
    download_ansible_link
    install_ansible_link
    setup_venv
    install_python_requirements
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