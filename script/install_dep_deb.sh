#! /bin/bash

# Check if system is Debian 13
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [ "$ID" = "debian" ] && [ "$VERSION_ID" = "13" ]; then
        echo "Debian 13 detected, proceeding with installation..."

        cp ./debian.sources /etc/apt/sources.list.d/debian.sources
        apt update

        pip install pyppeteer -i https://pypi.tuna.tsinghua.edu.cn/simple

        pyppeteer-install

        apt-get install -y libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libatspi2.0-0
        apt-get install -y fonts-noto-cjk fonts-noto-cjk-extra fonts-arphic-ukai fonts-arphic-uming
    else
        echo "Error: This script requires Debian 13"
        exit 1
    fi
else
    echo "Error: Cannot determine OS version"
    exit 1
fi