import os
import sys
from docker import types
import socket
import re
import time
import datetime
import json
import subprocess
from pathlib import Path
from .docker_utils import ensure_docker_volume, \
                          docker_volume_remove, \
                          docker_container_create, \
                          docker_container_exists, \
                          docker_container_start, \
                          docker_container_stop, \
                          docker_container_remove, \
                          docker_container_exec, \
                          docker_pull_image, \
                          docker_get_port_on_host, \
                          docker_get_container_labels, \
                          docker_get_latest_image_version, \
                          docker_get_container_mounts, \
                          docker_list_containers, \
                          docker_copy_to_container
from .common_utils import get_public_ip, \
                          get_expanded_path, \
                          get_system_cpu_count, \
                          get_system_memory_size, \
                          get_cli_version, \
                          delete_folder_contents, \
                          fc
from .sinara_platform import SinaraPlatform
from .config_manager import SinaraServerConfigManager, SinaraGlobalConfigManager

class SinaraServer():

    subject = 'server'
    container_name = 'personal_public_desktop'
    sinara_images = [['buslovaev/sinara-notebook', 'buslovaev/sinara-cv'], ['buslovaev/sinara-notebook-exp', 'buslovaev/sinara-cv-exp']]
    server_types = ["ml", "cv"]
    root_parser = None
    subject_parser = None
    create_parser = None
    start_parser = None
    remove_parser = None

    @staticmethod
    def add_command_handlers(root_parser, subject_parser):
        #SinaraServer.root_parser = root_parser
        #SinaraServer.subject_parser = subject_parser
        parser_server = subject_parser.add_parser(SinaraServer.subject, help='SinaraML Server commands')
        server_subparsers = parser_server.add_subparsers(title='action', dest='action', help='Action to do with server')

        SinaraServer.add_create_handler(server_subparsers)
        SinaraServer.add_start_handler(server_subparsers)
        SinaraServer.add_stop_handler(server_subparsers)
        SinaraServer.add_remove_handler(server_subparsers)
        SinaraServer.add_update_handler(server_subparsers)
        SinaraServer.add_list_handler(server_subparsers)

    @staticmethod
    def add_create_handler(server_cmd_parser):
        SinaraServer.create_parser = server_cmd_parser.add_parser('create', help='Create SinaraML Server')
        SinaraServer.create_parser.add_argument('--instanceName', default=SinaraServer.container_name, type=str, help='sinara server container name (default: %(default)s)')
        SinaraServer.create_parser.add_argument('--runMode', default='q', choices=["q", "b"], help='Runmode, quick (q) - work, data, tmp will be mounted inside docker volumes, basic (b) - work, data, tmp will be mounted from host folders (default: %(default)s)')
        SinaraServer.create_parser.add_argument('--createFolders', action='store_false', help='Create work, data, tmp folders in basic mode automatically if not exists, or else folders must be created manually (default: %(default)s)')
        SinaraServer.create_parser.add_argument('--useCustomFolders', action='store_true', help='Use custom work, data, raw and tmp folders in basic mode. Folders must exist (default: %(default)s)')
        SinaraServer.create_parser.add_argument('--gpuEnabled', choices=["y", "n"], help='y - Enables docker container to use Nvidia GPU, n - disable GPU')
        SinaraServer.create_parser.add_argument('--memLimit', default=str(SinaraServer.get_memory_size_limit()), type=str, help='Maximum amount of memory for server container (default: %(default)s)')
        SinaraServer.create_parser.add_argument('--cpuLimit', default=SinaraServer.get_cpu_cores_limit(), type=int, help='Number of CPU cores to use for server container (default: %(default)s)')
        SinaraServer.create_parser.add_argument('--jovyanRootPath', type=str, help='Path to parent folder for data, work, raw and tmp (only used in basic mode with --createFolders)')
        SinaraServer.create_parser.add_argument('--jovyanDataPath', type=str, help='Path to data fodler on host (only used in basic mode)')
        SinaraServer.create_parser.add_argument('--jovyanWorkPath', type=str, help='Path to work folder on host (only used in basic mode)')
        SinaraServer.create_parser.add_argument('--jovyanRawPath', type=str, help='Path to raw folder on host (only used in basic mode)')
        SinaraServer.create_parser.add_argument('--jovyanTmpPath', type=str, help='Path to tmp folder on host (only used in basic mode)')
        #SinaraServer.create_parser.add_argument('--infraName', default=SinaraInfra.LocalFileSystem, choices=SinaraServer.get_available_infra_names(), type=str, help='Infrastructure name to use (default: %(default)s)')
        SinaraServer.create_parser.add_argument('--insecure', action='store_true', help='Run server without password protection')
        SinaraServer.create_parser.add_argument('--platform', default="desktop", type=str, help='Server platform - get all available platforms with "sinara org list"')
        #SinaraServer.create_parser.add_argument('--platform', default=SinaraPlatform.Desktop, choices=list(SinaraPlatform), type=SinaraPlatform, help='Server platform - host where the server is run')
        SinaraServer.create_parser.add_argument('--experimental', action='store_true', help='Use experimiental server images')
        SinaraServer.create_parser.add_argument('--image', type=str, help='Custom server image name')
        SinaraServer.create_parser.add_argument('--shmSize', type=str, default=str(SinaraServer.get_default_shm_size()), help='Docker shared memory size option (default: %(default)s)')
        SinaraServer.create_parser.add_argument('--fromConfig', type=str, help='Create a server using server.json config')
        SinaraServer.create_parser.add_argument('--project', type=str, choices=SinaraServer.server_types, help='DEPRECATED: use --serverType. Project type for server (default: %(default)s)')
        SinaraServer.create_parser.add_argument('--serverType', type=str, choices=SinaraServer.server_types, help='SinaraML Server type (default: %(default)s)')
        SinaraServer.create_parser.set_defaults(func=SinaraServer.create)

    @staticmethod
    def add_start_handler(root_parser):
        server_start_parser = root_parser.add_parser('start', help='start sinara server')
        server_start_parser.add_argument('--instanceName', default=SinaraServer.container_name, help='sinara server container name (default: %(default)s)')
        server_start_parser.set_defaults(func=SinaraServer.start)

    @staticmethod
    def add_stop_handler(root_parser):
        server_stop_parser = root_parser.add_parser('stop', help='stop sinara server')
        server_stop_parser.add_argument('--instanceName', default=SinaraServer.container_name, help='sinara server container name (default: %(default)s)')
        server_stop_parser.set_defaults(func=SinaraServer.stop)

    @staticmethod
    def add_remove_handler(root_parser):
        server_remove_parser = root_parser.add_parser('remove', help='remove sinara server')
        server_remove_parser.add_argument('--instanceName', default=SinaraServer.container_name, help='sinara server container name (default: %(default)s)')
        server_remove_parser.add_argument('--withVolumes', default='n', choices=["y", "n"], help='y - remove existing data, work, tmp docker volumes, n - keep volumes  (default: %(default)s)')
        server_remove_parser.set_defaults(func=SinaraServer.remove)

    @staticmethod
    def add_update_handler(root_parser):
        server_remove_parser = root_parser.add_parser('update', help='update docker image of a sinara server')
        server_remove_parser.add_argument('--image', choices=["ml", "cv"], help='ml - update ml image, cv - update CV image')
        server_remove_parser.add_argument('--experimental', action='store_true', help='Update expermiental server images')
        server_remove_parser.set_defaults(func=SinaraServer.update)

    @staticmethod
    def add_list_handler(root_parser):
        server_list_parser = root_parser.add_parser('list', help='list sinara servers')
        server_list_parser.add_argument('--hideRemoved', action='store_true', help='Do not show removed servers')
        server_list_parser.set_defaults(func=SinaraServer.list)

    @staticmethod
    def _is_port_free(port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        if result == 0:
            return False
        return True
    
    @staticmethod
    def get_free_port(port):
        while not SinaraServer._is_port_free(port):
            port += 1
        return port
    
    @staticmethod
    def get_spark_ui_ports_mapping():
        spark_ui_start_port = 4040
        port_count = 20
        sparkui_end_port = spark_ui_start_port + port_count
        result = {}
        free_host_port = spark_ui_start_port-1
        for container_port in range(spark_ui_start_port, sparkui_end_port+1):
            free_host_port = SinaraServer.get_free_port(port=free_host_port+1)
            result[str(container_port)] = str(free_host_port)
        return result
    
    @staticmethod
    def get_jupyter_ui_ports_mapping():
        result = {}
        jupyter_ui_start_port = 8888
        free_host_port = SinaraServer.get_free_port(port=jupyter_ui_start_port)
        result['8888'] = str(free_host_port)
        return result

    @staticmethod
    def get_ports_mapping():
        result = {}
        spark_ui_ports = SinaraServer.get_spark_ui_ports_mapping()
        jupyter_ui_ports = SinaraServer.get_jupyter_ui_ports_mapping()
        result = {**spark_ui_ports, **jupyter_ui_ports}
        return result
    
    @staticmethod
    def get_available_infra_names():
        infras = SinaraServer.get_available_infras()
        return infras.keys()

    # @staticmethod
    # def get_available_infras():
    #     infras = {}
    #     for _infra in SinaraInfra:
    #         infras[_infra.value] = ["self"]
    #     infra_plugins = SinaraPluginLoader.get_infra_plugins()
    #     for plugin in infra_plugins:
    #         plugin_infras = SinaraPluginLoader.get_infras(plugin)
    #         for infra in plugin_infras:
    #             if infra in infras and isinstance(infras[infra], list):
    #                 infras[infra].append(plugin)
    #             else:
    #                 infras[infra] = [plugin]
    #     return infras

    @staticmethod
    def get_cpu_cores_limit():
        cpu_cores = get_system_cpu_count()
        cores_reserve_for_host = 1
        if not cpu_cores or cpu_cores <= cores_reserve_for_host:
            result = 1
        else:
            result = cpu_cores - cores_reserve_for_host
        return result

    @staticmethod
    def get_memory_size_limit():
        total_mem_bytes = get_system_memory_size()
        bytes_reserve_for_host = int(2 * 1024.**3) # Reserve 2 Gb by default
        if total_mem_bytes <= bytes_reserve_for_host:
            result = int(total_mem_bytes * 0.7)
        else:
            result = int(total_mem_bytes - bytes_reserve_for_host)
        return result
    
    @staticmethod
    def get_default_shm_size():
        total_mem_bytes = get_system_memory_size()
        return int(total_mem_bytes / 6)

    @staticmethod
    def ensure_proxy_from_host(instance):
        keep_env_in_sudo_cmd = "sed -i '/Defaults:%sudo env_keep += \"http_proxy https_proxy ftp_proxy all_proxy no_proxy\"/s/^#//g' /etc/sudoers"
        exit_code, output = docker_container_exec(instance, keep_env_in_sudo_cmd)
        if exit_code:
            print("Failed to set proxy settings for sudo users, apt / apt-get might not work properly")

    @staticmethod
    def create(args):
        if args.fromConfig:
            print(f"Using config {args.fromConfig} to create the sinara server")
            with open(args.fromConfig, "r") as cfg:
                server_config = json.load(cfg)
                server_script_args = server_config["cmd"]["calculated_args"]
            subprocess.run(f"sinara {server_script_args}", shell=True, env=dict(os.environ), check=True)
            return

        gpu_requests = []
        sinara_image_num = 0

        if docker_container_exists(args.instanceName):
            print(f"Sinara server {args.instanceName} aleady exists, remove it and run create again")
            return

        if args.serverType is None and not args.project is None: # for backward compatibility
            args.serverType = args.project
        if args.serverType is None:
            sinara_image_num = -1
            while sinara_image_num not in [0, 1]:
                try:
                    sinara_image_num = int(input('Please, choose a SinaraML Server type for [1] ML or [2] CV: ')) - 1
                    args.serverType = SinaraServer.server_types[sinara_image_num]
                except ValueError:
                    pass

        else:
            sinara_image_num = SinaraServer.server_types.index(args.serverType)

        if args.serverType == "cv":
            args.gpuEnabled = "y"  

        if args.gpuEnabled == "y":
            gpu_requests = [ types.DeviceRequest(count=-1, capabilities=[['gpu']]) ]

        if not args.image:
            sinara_image = SinaraServer.sinara_images[ int(args.experimental) ][ int(sinara_image_num) ]
            versioned_image_tag = docker_get_latest_image_version(sinara_image.split('/')[-1])
            sinara_image_versioned = f"{sinara_image.replace('latest', '')}:{versioned_image_tag}"
        else:
            sinara_image = args.image
            sinara_image_versioned = sinara_image

        if args.runMode == "q":
            docker_volumes = SinaraServer._prepare_quick_mode(args)
        elif args.runMode == "b":
            docker_volumes = SinaraServer._prepare_basic_mode(args)

        server_cmd = "start-notebook.sh --ip=0.0.0.0 --port=8888 --NotebookApp.default_url=/lab --ServerApp.allow_password_change=False"
        if args.insecure:
            server_cmd = f"{server_cmd} --NotebookApp.token='' --NotebookApp.password=''"

        cm = SinaraServerConfigManager(args.instanceName)

        print(args.platform)
        org_json_path = Path(Path(__file__).parent.parent, "mlops_organization.json")
        with open(org_json_path) as f:
            org_json = json.load(f)
        #print(org_json)

        server_params = {
            "image": sinara_image,
            "command": server_cmd,
            "working_dir": "/home/jovyan/work",
            "name": args.instanceName,
            "mem_limit": args.memLimit,
            "nano_cpus": 1000000000 * int(args.cpuLimit), # '--cpus' parameter equivalent in python docker client
            "shm_size": args.shmSize,
            "ports": SinaraServer.get_ports_mapping(),
            "volumes": docker_volumes,
            "environment": {
                "DSML_USER": "jovyan",
                "JUPYTER_ALLOW_INSECURE_WRITES": "true",
                "JUPYTER_RUNTIME_DIR": "/tmp",
                "INFRA_NAME": "local_filesystem",
                "JUPYTER_IMAGE_SPEC": sinara_image_versioned,
                "SINARA_SERVER_MEMORY_LIMIT": args.memLimit,
                "SINARA_SERVER_CORES": int(args.cpuLimit),
                "SINARA_ORG": org_json,
                "SINARA_PLATFORM": str(args.platform),
                "SINARA_IMAGE_TYPE": SinaraServer.get_image_type(args)
            },
            "labels": {
                "sinaraml.platform": str(args.platform),
                #"sinaraml.infra": str(args.infraName),
                "sinaraml.config.path": str(cm.server_config),
                "sinaraml.serverType": str(args.serverType),
                "sinaraml.cli.version": str(get_cli_version())
            },
            "device_requests": gpu_requests # '--gpus all' flag equivalent in python docker client
        }

        docker_container_create(**server_params)
        SinaraServer.save_server_config(server_params, args, cm)
        print(f"Sinara server {args.instanceName} is created")

    @staticmethod
    def _prepare_quick_mode(args):
        data_volume = f"jovyan-data-{args.instanceName}"
        work_volume = f"jovyan-work-{args.instanceName}"
        tmp_volume =  f"jovyan-tmp-{args.instanceName}"
        raw_volume =  f"jovyan-raw-{args.instanceName}"

        ensure_docker_volume(data_volume, already_exists_msg="Docker volume with jovyan data is found")
        ensure_docker_volume(work_volume, already_exists_msg="Docker volume with jovyan work is found")
        ensure_docker_volume(tmp_volume, already_exists_msg="Docker volume with jovyan tmp data is found")
        ensure_docker_volume(raw_volume, already_exists_msg="Docker volume with jovyan raw data is found")

        return  [f"{data_volume}:/data",
                 f"{work_volume}:/home/jovyan/work",
                 f"{tmp_volume}:/tmp",
                 f"{raw_volume}:/raw"]

    @staticmethod
    def _prepare_basic_mode(args):
        #folders_exist = ''
        
        if args.useCustomFolders != True:
             
            if args.jovyanRootPath:
                jovyan_root_path = get_expanded_path(args.jovyanRootPath)
            else:
                jovyan_root_path = get_expanded_path( input('Please, choose jovyan Root folder path (data, work and tmp will be created there): ') )
                args.jovyanRootPath = jovyan_root_path

            jovyan_data_path = os.path.join(jovyan_root_path, "data")
            jovyan_work_path = os.path.join(jovyan_root_path, "work")
            jovyan_tmp_path = os.path.join(jovyan_root_path, "tmp")
            jovyan_raw_path = os.path.join(jovyan_root_path, "raw")

            print("Creating work folders")
            os.makedirs(jovyan_data_path, exist_ok=True)
            os.makedirs(jovyan_work_path, exist_ok=True)
            os.makedirs(jovyan_tmp_path, exist_ok=True)
            os.makedirs(jovyan_raw_path, exist_ok=True)
        else:
            if args.jovyanDataPath:
                jovyan_data_path = get_expanded_path(args.jovyanDataPath)
            else:
                jovyan_data_path = get_expanded_path( input("Please, enter Data path: ") )
                args.jovyanDataPath = jovyan_data_path
            
            if args.jovyanWorkPath:
                jovyan_work_path = get_expanded_path(args.jovyanWorkPath)
            else:
                jovyan_work_path = get_expanded_path( input("Please, enter Work path: ") )
                args.jovyanWorkPath = jovyan_work_path

            if args.jovyanTmpPath:
                jovyan_tmp_path = get_expanded_path(args.jovyanTmpPath)
            else:
                jovyan_tmp_path = get_expanded_path( input("Please, enter Tmp path: ") )
                args.jovyanTmpPath = jovyan_tmp_path

            if args.jovyanRawPath:
                jovyan_raw_path = get_expanded_path(args.jovyanRawPath)
            else:
                jovyan_raw_path = get_expanded_path( input("Please, enter Raw path: ") )
                args.jovyanRawPath = jovyan_raw_path

            # while folders_exist not in ["y", "n"]:
            #     folders_exist = input("Please, ensure that the folders exist (y/n): ")

            # if folders_exist != "y":
            #     raise Exception("Sorry, you should prepare the folders beforehand")
        
        print("Trying to run your environment...")
        
        return  [f"{jovyan_data_path}:/data",
                 f"{jovyan_work_path}:/home/jovyan/work",
                 f"{jovyan_tmp_path}:/tmp",
                 f"{jovyan_raw_path}:/raw"]
        
    @staticmethod
    def get_notebook_user(instance):
        exit_code, output = docker_container_exec(instance, "printenv NB_USER")
        stdout, stderr = output
        if stdout:
           return stdout.decode('utf-8').split('\n')[0]
        return None

    @staticmethod
    def prepare_mounted_folders(instance):
        notebook_user = SinaraServer.get_notebook_user(instance)
        docker_container_exec(instance, f"chown -R {notebook_user}:users /tmp")
        docker_container_exec(instance, f"chown -R {notebook_user}:users /data")
        docker_container_exec(instance, f"chown -R {notebook_user}:users /raw")
        docker_container_exec(instance, f"chown {notebook_user}:users /home/$NB_USER")
        docker_container_exec(instance, f"chmod 777 /home/{notebook_user}")
        docker_container_exec(instance, f"chmod 777 /home/{notebook_user}/work")
        docker_container_exec(instance, "rm -rf /tmp/*")
        docker_container_exec(instance, f"chmod 777 /tmp")

    @staticmethod
    def get_server_logs(instance, server_command):
        exit_code, output = docker_container_exec(instance, server_command)
        return output

    @staticmethod
    def get_server_url(instance):
        url = None
        commands = ["jupyter lab list", "jupyter server list", "jupyter notebook list"]
        for cmd in commands:
            output = SinaraServer.get_server_logs(instance, cmd)
            stdout, stderr = output
            log_lines_stderr = [] if not stderr else stderr.decode('utf-8').split('\n')
            log_lines_stdout = [] if not stdout else stdout.decode('utf-8').split('\n')
            log_lines = [] if not stderr and not stdout else [*log_lines_stderr, *log_lines_stdout]
            for line in log_lines:
                if any(x in line for x in ['http://', 'https://']):
                    m = re.search(r"(http[^\s]+)", line)
                    url = m.group(1) if m else None
                    if url: 
                        break
            if url:
                break
        return url
    
    @staticmethod
    def get_server_protocol(server_url):
        m = re.search(r"^(http:|https:)", server_url)
        return str(m.group(1))[:-1] if m else None

    @staticmethod
    def get_server_token(server_url):
        m = re.search(r"token=([a-f0-9-][^\s]+)", server_url)
        return m.group(1) if m else None
    
    @staticmethod
    def get_server_platform(instance):
        labels = docker_get_container_labels(instance)
        # Fallback to desktop platform for legacy servers without labels
        if not "sinaraml.platform" in labels or not labels["sinaraml.platform"]:
            return SinaraPlatform.Desktop
        return SinaraPlatform(labels["sinaraml.platform"])
    
    @staticmethod
    def get_server_ip():
        public_ip = get_public_ip()
        if not public_ip:
            return "{{vm_public_ip}}"
        return public_ip

    
    @staticmethod
    def wait_for_token(jupyter_ui_url):
        import urllib.request
        http_exception = None
        for i in range(30):
            try:
                req = urllib.request.Request(jupyter_ui_url)
                urllib.request.urlopen(req)
            except Exception as e:
                http_exception = e
                time.sleep(1)
                continue
            else:
                http_exception = None
                time.sleep(1)
                break
        if http_exception:
            raise http_exception
        
    @staticmethod
    def get_server_clickable_url(server_name):
        import socket
        hostname_loopback = "127.0.0.1"
        hostname_local_dns = socket.getfqdn()
        hostname_public = SinaraServer.get_server_ip()
        host_port = docker_get_port_on_host(server_name, 8888)
        url = SinaraServer.get_server_url(server_name)
        protocol = SinaraServer.get_server_protocol(url)
        server_alive_url = f"{protocol}://{hostname_local_dns}:{host_port}"
        # Wait for server token to be available in container logs, may take some time
        try:
            SinaraServer.wait_for_token(server_alive_url)
        except Exception as e:
            if "certificate_verify_failed" not in str(e).lower():
                raise e
        token = SinaraServer.get_server_token(url)
        token_str = f"?token={token}" if token else ""
        
        return [
            f"{protocol}://{hostname_loopback}:{host_port}/{token_str}",
            f"{protocol}://{hostname_local_dns}:{host_port}/{token_str}",
            f"{protocol}://{hostname_public}:{host_port}/{token_str}"]

    @staticmethod
    def start(args):

        # check jovyan-single-use for backward compatibility
        sinara_containers = docker_list_containers("sinaraml.platform")
        for sinara_container in sinara_containers:
            container_name = sinara_container.attrs["Names"][0][1:]
            print(container_name)
            if container_name == 'jovyan-single-use' and args.instanceName == 'personal_public_desktop':
                args.instanceName = container_name
                break

        if not docker_container_exists(args.instanceName):
            print(f"Sinara server with name {args.instanceName} doesn't exist yet, run 'sinara server create' first")
            return
        
        print(f'Starting sinara server {args.instanceName}...')

        curr_dir = os.path.dirname(os.path.realpath(__file__))
        docker_copy_to_container(args.instanceName, Path(curr_dir) / 'assets/sinaraml_jupyter_host_ext-0.1.0-py3-none-any.whl',
            '/home/sinarian/')
        
        container_name = args.instanceName
        docker_container_start(container_name)
        SinaraServer.prepare_mounted_folders(container_name)
        SinaraServer.ensure_proxy_from_host(container_name)
        docker_container_exec(container_name, "pip install sinaraml_jupyter -U")

        docker_container_exec(container_name, "pip install /home/sinarian/sinaraml_jupyter_host_ext-0.1.0-py3-none-any.whl")
        docker_container_exec(container_name, "python /home/sinarian/check_sinara.py")
        # docker_copy_from_container(container_name, "/tmp/sinara_check.txt", "/tmp")
        # report_outdated_sinara_lib('/tmp/sinara_check.txt')
        # restart container to activate and enable extension
        docker_container_stop(container_name)
        docker_container_start(container_name)
        
        platform = SinaraServer.get_server_platform(container_name)
        server_clickable_url = SinaraServer.get_server_clickable_url(container_name)
        server_clickable_url = '\n'.join(server_clickable_url)
        server_hint = f"""To access the server, copy and paste one of these URLs in a browser:\n{server_clickable_url}
            If server is not accessible, find your's machine public IP address manually
            """
        
        print(f"Sinara server {container_name} started, platform: {platform}\n{server_hint}")

    @staticmethod
    def stop(args):

        # check jovyan-single-use for backward compatibility
        sinara_containers = docker_list_containers("sinaraml.platform")
        for sinara_container in sinara_containers:
            container_name = sinara_container.attrs["Names"][0][1:]
            if container_name == 'jovyan-single-use' and args.instanceName == 'personal_public_desktop':
                args.instanceName = container_name

        if not docker_container_exists(args.instanceName):
            raise Exception(f"Your server with name {args.instanceName} doesn't exist")
        docker_container_stop(args.instanceName)
        print(f'Sinara server {args.instanceName} stopped')

    @staticmethod
    def remove(args):
        container_folders = ["/data", "/home/jovyan/work", "/tmp", "/raw"]
        container_volumes = [f"jovyan-data-{args.instanceName}", f"jovyan-work-{args.instanceName}", f"jovyan-tmp-{args.instanceName}"]

        if not docker_container_exists(args.instanceName):
            print(f"Server with name {args.instanceName} has been already removed")
            return
        if args.withVolumes == "y":
            mounts = docker_get_container_mounts(args.instanceName)
            for mount in mounts:
                if mount["Type"] == "bind":
                    if mount["Destination"] in container_folders:
                        print(f"Removing sinara volume {mount['Source']}")
                        delete_folder_contents(mount["Source"])

            # always try to remove docker volumes, in case they are orphaned
            docker_container_remove(args.instanceName)

            for vol in container_volumes:
                print(f"Removing sinara volume {vol}")
                docker_volume_remove(vol)
        else:
            docker_container_remove(args.instanceName)

        cm = SinaraServerConfigManager(args.instanceName)
        server_config = cm.trash_server()            

        print(f'Sinara server {args.instanceName} removed.\n\nTo create it again use command:\nsinara server create --fromConfig {server_config}')

    @staticmethod
    def update(args):
        args_dict = vars(args)
        sinara_image_num = -1
        if not args.image:
            while sinara_image_num not in [1, 2]:
                try:
                    sinara_image_num = int(input('Please, choose a SinaraML Server to update [1] ML or [2] CV:'))
                except ValueError:
                    pass
        elif args.image == "ml":
            sinara_image_num = 1
        elif args.image == "cv":
            sinara_image_num = 2

        sinara_image = SinaraServer.sinara_images[ int(args.experimental) ][ sinara_image_num-1 ]
        docker_pull_image(sinara_image)
        print(f'Sinara server image {sinara_image} updated successfully')

    @staticmethod
    def save_server_config(container_params, args, config_manager):
        calculated_args = ""
        for k, v in vars(args).items():
            if k in ["func", "verbose"]: continue
            if type(v) == bool and v == True:
              calculated_args = calculated_args + ' ' + f'--{k}'
            elif (type(v) == bool and v == False) or not v:
              continue
            elif k in ["subject", "action"]:
                calculated_args = calculated_args + ' ' + f'{v}'
            else:
              calculated_args = calculated_args + ' ' + f'--{k}={v}'
        
        if args.verbose:
            calculated_args = " --verbose" + calculated_args

        server_config = {
            "subject_type": "server",
            "cli_version" : "",
            "cmd": {
                "script": sys.argv[0],
                "args": " ".join(sys.argv[1:]),
                "calculated_args": calculated_args
            },
            "container": container_params
        }
        config_manager.save_server_config(server_config)

    @staticmethod
    def list(args):
        print("Gathering servers info...")
        gcm = SinaraGlobalConfigManager()
        sinara_containers = docker_list_containers("sinaraml.platform")
        sinara_removed_server = gcm.get_trashed_servers()

        print(f"{fc.HEADER}\nSinara servers:\n-------------------------------------{fc.RESET}")
        for sinara_container in sinara_containers:
            container_name = sinara_container.attrs["Names"][0][1:]
            container_image = sinara_container.attrs["Image"]
            container_status = sinara_container.attrs["Status"]
            if "sinaraml.serverType" in sinara_container.attrs["Labels"]:
                container_type = sinara_container.attrs["Labels"]["sinaraml.serverType"]
            else:
                # fallback to guessing by name
                if "notebook" in container_image:
                    container_type = SinaraServer.server_types[0]
                else:
                    container_type = SinaraServer.server_types[1]
            print(f"\n{fc.CYAN}Server{fc.RESET}: {fc.WHITE}{container_name}{fc.RESET}\n" \
                  f"{fc.CYAN}Image{fc.RESET}: {fc.WHITE}{container_image}{fc.RESET}\n" \
                  f"{fc.CYAN}Type{fc.RESET}: {fc.WHITE}{container_type}{fc.RESET}\n" \
                  f"{fc.CYAN}Status{fc.RESET}: {fc.WHITE}{container_status}{fc.RESET}")
            if container_status.lower().startswith("running") or container_status.lower().startswith("up"):
                server_clickable_urls = SinaraServer.get_server_clickable_url(container_name)
                url_str = ", ".join(server_clickable_urls)
                print(f"{fc.CYAN}Urls{fc.RESET}: {fc.WHITE}{url_str}{fc.RESET}")
        
        if not args.hideRemoved:
            print(f"\n{fc.HEADER}Sinara removed servers:\n-------------------------------------{fc.RESET}")
            for server in sinara_removed_server:
                try:
                    with open(sinara_removed_server[server], 'r') as cfg:
                        server_config = json.load(cfg)

                    server_name = server_config['container']['name']
                    server_image = server_config['container']['image']
                    if "sinaraml.serverType" in server_config['container']["labels"]:
                        server_type = server_config['container']["labels"]["sinaraml.serverType"]
                    else:
                        # fallback to guessing by name
                        if "notebook" in server_image:
                            server_type = SinaraServer.server_types[0]
                        else:
                            server_type = SinaraServer.server_types[1]
                    removal_time = datetime.datetime.strptime(server.split('.')[-1], "%Y%m%d-%H%M%S")
                    removal_time_str = removal_time.strftime("%d.%m.%Y %H:%M:%S")
                    reset_command = server_config['cmd']
                    print(f"\n{fc.CYAN}Server: {fc.WHITE}{server_name}{fc.RESET}\n" \
                        f"{fc.CYAN}Image{fc.RESET}: {server_image}{fc.RESET}\n" \
                        f"{fc.CYAN}Type{fc.RESET}: {fc.WHITE}{server_type}{fc.RESET}\n" \
                        f"{fc.CYAN}Status{fc.RESET}: {fc.WHITE}removed{fc.RESET}\n" \
                        f"{fc.CYAN}Removed at{fc.RESET}: {fc.WHITE}{removal_time_str}{fc.RESET}\n" \
                        f"{fc.CYAN}To create it again use command{fc.RESET}: {fc.WHITE}\nsinara server create --fromConfig {sinara_removed_server[server]}{fc.RESET}")
                except Exception as e:
                    print(f"{fc.RED}\nServer config at {sinara_removed_server[server]} cannot be read, skipping{fc.RESET}")
                    
    @staticmethod
    def get_image_type(args):
        exp_part = ''
        if not args.serverType:
            raise Exception('Sinara server type not set, cannot detemine image type')
        if args.experimental:
            exp_part = '-exp'
        return str(args.serverType) + exp_part 
