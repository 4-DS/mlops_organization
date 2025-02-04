import hashlib
import re
import urllib
import time
import socket
import os
import json
from pathlib import Path
import shutil
import logging
from multiprocessing import cpu_count
import math
import platform

class fc:
    HEADER = '\033[95m'
    UNDERLINE = '\033[4m'
    BLACK   = '\033[30m'
    RED     = '\033[31m'
    GREEN   = '\033[32m'
    YELLOW  = '\033[33m'
    BLUE    = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN    = '\033[36m'
    WHITE   = '\033[37m'
    RESET   = '\033[39m'

def get_bentoservice_profile_name(bentoservice_dir):
    profile = None
    profile_file = os.path.join(bentoservice_dir, 'bentoservice_profile.json')
    if os.path.isfile(profile_file):
        with open(profile_file, 'r+') as f:
            profile_data = json.load(f)
            profile = profile_data['bentoservice_profile']['name']
    return profile

def replace_bentoservice_model_server_image(dockerfile_path, model_server_image):
    insert_marker = 'from '
    with open(dockerfile_path, 'r+') as docker_file:
        dockerfile_content = docker_file.readlines()
        marker_index = [idx for idx, s in enumerate(dockerfile_content) if insert_marker in s.lower()][0]
        insert_index = marker_index + 1
        del dockerfile_content[0]
        dockerfile_content.insert(0, f"FROM {model_server_image}\n")
        docker_file.seek(0)
        docker_file.writelines(dockerfile_content)
        docker_file.truncate()

def remove_bentoservice_deps_install(dockerfile_path):
    strs_to_remove = ["RUN ./bentoml-init.sh restore_conda_env\n", "RUN ./bentoml-init.sh install_pip_packages\n"]
    with open(dockerfile_path, 'r+') as docker_file:
        dockerfile_content = docker_file.readlines()
        dockerfile_content[:] = [x for x in dockerfile_content if x not in strs_to_remove]
        docker_file.seek(0)
        docker_file.writelines(dockerfile_content)
        docker_file.truncate()

def compute_md5(file_name):
    hash_md5 = hashlib.md5()
    with open(file_name, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def ip_address_is_valid(ip_address):
    ip_v4_seg  = r'(?:25[0-5]|(?:2[0-4]|1{0,1}[0-9]){0,1}[0-9])'
    ip_v4_addr = r'(?:(?:' + ip_v4_seg + r'\.){3,3}' + ip_v4_seg + r')'

    ip_v6_seg  = r'(?:(?:[0-9a-fA-F]){1,4})'
    ip_v6_groups = (
        r'(?:' + ip_v6_seg + r':){7,7}' + ip_v6_seg,                  # 1:2:3:4:5:6:7:8
        r'(?:' + ip_v6_seg + r':){1,7}:',                           # 1::                                 1:2:3:4:5:6:7::
        r'(?:' + ip_v6_seg + r':){1,6}:' + ip_v6_seg,                 # 1::8               1:2:3:4:5:6::8   1:2:3:4:5:6::8
        r'(?:' + ip_v6_seg + r':){1,5}(?::' + ip_v6_seg + r'){1,2}',  # 1::7:8             1:2:3:4:5::7:8   1:2:3:4:5::8
        r'(?:' + ip_v6_seg + r':){1,4}(?::' + ip_v6_seg + r'){1,3}',  # 1::6:7:8           1:2:3:4::6:7:8   1:2:3:4::8
        r'(?:' + ip_v6_seg + r':){1,3}(?::' + ip_v6_seg + r'){1,4}',  # 1::5:6:7:8         1:2:3::5:6:7:8   1:2:3::8
        r'(?:' + ip_v6_seg + r':){1,2}(?::' + ip_v6_seg + r'){1,5}',  # 1::4:5:6:7:8       1:2::4:5:6:7:8   1:2::8
        ip_v6_seg + r':(?:(?::' + ip_v6_seg + r'){1,6})',             # 1::3:4:5:6:7:8     1::3:4:5:6:7:8   1::8
        r':(?:(?::' + ip_v6_seg + r'){1,7}|:)',                     # ::2:3:4:5:6:7:8    ::2:3:4:5:6:7:8  ::8       ::
        r'fe80:(?::' + ip_v6_seg + r'){0,4}%[0-9a-zA-Z]{1,}',       # fe80::7:8%eth0     fe80::7:8%1  (link-local IPv6 addresses with zone index)
        r'::(?:ffff(?::0{1,4}){0,1}:){0,1}[^\s:]' + ip_v4_addr,     # ::255.255.255.255  ::ffff:255.255.255.255  ::ffff:0:255.255.255.255 (IPv4-mapped IPv6 addresses and IPv4-translated addresses)
        r'(?:' + ip_v6_seg + r':){1,4}:[^\s:]' + ip_v4_addr,          # 2001:db8:3:4::192.0.2.33  64:ff9b::192.0.2.33 (IPv4-Embedded IPv6 Address)
    )
    ip_v6_addr = '|'.join(['(?:{})'.format(g) for g in ip_v6_groups[::-1]])  # Reverse rows for greedy match

    ip_v4 = None
    ip_v6 = None
    try:
        ip_v4 = re.search(ip_v4_addr, ip_address).group()
    except:
        pass
    try:
        ip_v6 = re.search(ip_v6_addr, ip_address).group()
    except:
        pass
    return bool(ip_v4 or ip_v6)

def get_public_ip():
    public_ip_service_url = "https://ipinfo.io/ip"
    result = None
    for i in range(2):
        try:
            response = urllib.request.urlopen(public_ip_service_url)
        except:
            time.sleep(1)
            continue
        else:
            with response as f:
                public_ip = f.read().decode('utf-8')
                if ip_address_is_valid(public_ip):
                    result = public_ip
            break
    return result

def get_expanded_path(dest_path):
    dest_path = str(dest_path).lstrip()
    if dest_path[0] == '~':
        result = os.path.expanduser(dest_path)
    elif dest_path[0] != os.sep:
        result = os.path.join(os.getcwd(), dest_path)
    else:
        result = os.path.abspath(dest_path)
    return result

def str_to_bool(value):
    value = value.lower()
    if value in ('y', 'yes', 't', 'true', 'on', '1'):
        return True
    elif value in ('n', 'no', 'f', 'false', 'off', '0'):
        return False
    else:
        raise ValueError("invalid truth value %r" % (value,))
    
def get_system_cpu_count():
    return cpu_count()

def get_system_memory_size():
    return os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')

def delete_folder_contents(dest_folder):
    for path in Path(dest_folder).glob("**/*"):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

def get_cli_version():
    try:
        from ._version import __version__
        return __version__
    except Exception as e:
        logging.info(e)
    return 'unknown'

def convert_size(size_bytes):
   if size_bytes == 0:
       return "0B"
   size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
   i = int(math.floor(math.log(size_bytes, 1024)))
   p = math.pow(1024, i)
   s = round(size_bytes / p, 2)
   return "%s %s" % (s, size_name[i])

def platform_is_wsl():
    platform_release = platform.uname().release
    if platform_release.endswith("-Microsoft") or platform_release.endswith("microsoft-standard-WSL2"):
        return True
    return False

def get_folder_size(root):
    def _get_sizes(folder):
        for path, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                full_path = os.path.join(path, file)
                try:
                    yield (os.path.getsize(full_path), full_path)
                except Exception:
                    pass
                
    total_size = 0
    for (size, name) in _get_sizes(root):
        total_size += size
    
    return total_size
