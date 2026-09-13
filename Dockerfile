FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    QT_QPA_PLATFORM=offscreen \
    ODA_FILE_CONVERTER=/opt/oda/squashfs-root/AppRun

# ODA's Qt runtime is bundled in its AppImage; extract it to avoid FUSE.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl libgl1 libegl1 libopengl0 libglib2.0-0 libfontconfig1 \
    libxrender1 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-xinerama0 \
    libxcb-util1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
    libdbus-1-3 libsm6 libice6 libxi6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/oda
RUN curl --fail --location --retry 3 \
    'https://www.opendesign.com/guestfiles/get?filename=ODAFileConverter_QT6_lnxX64_8.3dll_27.1.AppImage' \
    --output converter.AppImage \
    && chmod +x converter.AppImage \
    && ./converter.AppImage --appimage-extract > /dev/null \
    && rm converter.AppImage \
    && test -x "$ODA_FILE_CONVERTER"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# This ODA release bundles xcb only, so run its GUI on a private virtual display.
RUN apt-get update && apt-get install -y --no-install-recommends xvfb xauth \
    && rm -rf /var/lib/apt/lists/* \
    && printf '#!/bin/sh\nexport QT_QPA_PLATFORM=xcb\nexec xvfb-run -a /opt/oda/squashfs-root/AppRun "$@"\n' > /usr/local/bin/oda-converter \
    && chmod +x /usr/local/bin/oda-converter
ENV ODA_FILE_CONVERTER=/usr/local/bin/oda-converter

# Fail the image build if DWG conversion cannot actually run on Linux.
RUN python scripts/check_dwg_runtime.py

EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn src.web.app:app --bind 0.0.0.0:${PORT:-10000}"]
