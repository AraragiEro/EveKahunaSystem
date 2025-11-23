import os

# 下载资源目录
DOWNLOAD_RESOURCE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../download_resource"))

# 临时文件目录
TMP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../tmp"))
# 资源目录
RESOURCE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../resource"))

if not os.path.exists(DOWNLOAD_RESOURCE_PATH):
    os.makedirs(DOWNLOAD_RESOURCE_PATH)
if not os.path.exists(TMP_PATH):
    os.makedirs(TMP_PATH)
if not os.path.exists(RESOURCE_PATH):
    os.makedirs(RESOURCE_PATH)