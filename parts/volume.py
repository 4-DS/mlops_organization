from tabulate import tabulate
import json
import os

from .docker_utils import docker_list_volumes, docker_list_containers
from .common_utils import convert_size, fc, platform_is_wsl, get_folder_size
from .config_manager import SinaraGlobalConfigManager


class SinaraVolume:

    subject = 'volume'
    list_parser = None
    
    @staticmethod
    def add_command_handlers(root_parser, subject_parser):
        parser_volume = subject_parser.add_parser(SinaraVolume.subject, help='sinara volume subject')
        volume_subparsers = parser_volume.add_subparsers(title='action', dest='action', help='Action to do with subject')
        SinaraVolume.add_list_handler(volume_subparsers)

    @staticmethod
    def add_list_handler(volume_cmd_parser):
        SinaraVolume.list_parser = volume_cmd_parser.add_parser('list', help='list sinara volumes')
        SinaraVolume.list_parser.add_argument('--all', action='store_true', help='Show all sinara volumes including attached to removed servers')
        SinaraVolume.list_parser.set_defaults(func=SinaraVolume.list)
        
    @staticmethod
    def print_as_table(args, volumes, list_header):
        print(f"{fc.HEADER}{list_header}{fc.RESET}{fc.HEADER}\n************************************\n")
        for server in volumes:
            print(f"{fc.CYAN}Server:{fc.RESET} {fc.WHITE}{server}{fc.RESET}{fc.CYAN}\nVolumes:{fc.RESET}")
            vols = volumes[server]["volumes"]
            header = vols[0].keys()
            rows = [x.values() for x in vols]
            print(tabulate(rows, header))
            print(f"{fc.HEADER}************************************{fc.RESET}\n")
                
    @staticmethod
    def _get_bind_vol_wsl_source(server_container, dest_path):
        labels = server_container.attrs["Labels"]
        for label in labels:
            if "Target" in label and labels[label] == dest_path:
                source_key = label.replace("Target", "Source")
                return labels[source_key]
            
    @staticmethod
    def get_volume_type_description(mount):
        if mount["Type"] == "volume":
            return "docker volume"
        elif mount["Type"] == "bind":
            return "host folder"
        else:
            return "unknown"
        
    @staticmethod
    def get_mounts_from_container_spec(container_spec):
        mounts = []
        for volume in container_spec["volumes"]:
            mount = {}
            mount_spec = volume.split(":")
            if os.sep in mount_spec[0]:
                mount["Type"] = "bind"
                mount["Source"] = mount_spec[1]
            else:
                mount["Type"] = "volume"
                mount["Source"] = ""
                
            mount["Name"] = mount_spec[0]
            mount["Destination"] = mount_spec[1]
            mounts.append(mount)
        return mounts
        
    @staticmethod
    def list(args):
        volumes = {}
        all_docker_volumes = docker_list_volumes()
        
        gcm = SinaraGlobalConfigManager()
        
        sinara_containers = docker_list_containers("sinaraml.platform")
        sinara_removed_servers = gcm.get_trashed_servers()
        
        for sinara_container in sinara_containers:
            container_name = sinara_container.attrs["Names"][0][1:]
            volumes[container_name] = {
                "volumes": []
            }
            for volume in sinara_container.attrs["Mounts"]:
                volume_parsed = {}
                if volume["Type"] == "volume":
                    volume_parsed["name"] = volume["Name"]
                    docker_volume = [vol for vol in all_docker_volumes if vol["Name"] == volume["Name"]][0]
                    volume_parsed["used"] = convert_size(docker_volume["UsageData"]["Size"])
                    volume_parsed["type"] = SinaraVolume.get_volume_type_description(volume)
                
                elif volume["Type"] == "bind":
                    if platform_is_wsl():
                        volume_parsed["name"] = SinaraVolume._get_bind_vol_wsl_source(sinara_container, volume["Destination"])
                    else:
                        volume_parsed["name"] = volume["Source"]
                    volume_parsed["used"] = convert_size(get_folder_size(volume_parsed["name"]))
                    volume_parsed["type"] = SinaraVolume.get_volume_type_description(volume)
                
                else:
                    raise Exception(f"Unsupported volume type {volume['Type']}")
                volumes[container_name]["volumes"].append(volume_parsed)
                
        SinaraVolume.print_as_table(args, volumes, "Active Servers")
        
        if args.all:
            volumes_of_removed_servers = {}
            for removed_server in sinara_removed_servers:
                try:
                    with open(sinara_removed_servers[removed_server], "r") as cfg:
                        server_config = json.load(cfg)
                    container_name = server_config["container"]["name"]
                    
                    volumes_of_removed_servers[container_name] = {
                        "volumes": []
                    }
                    
                    volumes_from_spec = SinaraVolume.get_mounts_from_container_spec(server_config["container"])
                    for volume in volumes_from_spec:
                        volume_parsed = {}
                        if volume["Type"] == "volume":
                            volume_parsed["name"] = volume["Name"]
                            
                            docker_volumes = [vol for vol in all_docker_volumes if vol["Name"] == volume["Name"]]
                            if docker_volumes:
                                docker_volume = docker_volumes[0]
                                volume_parsed["used"] = convert_size(docker_volume["UsageData"]["Size"])
                            else:
                                volume_parsed["used"] = "N/A"
                                
                            volume_parsed["exists"] = True if len(docker_volumes) > 0 else False
                            volume_parsed["type"] = SinaraVolume.get_volume_type_description(volume)
                        
                        elif volume["Type"] == "bind":
                            volume_parsed["name"] = volume["Source"]
                            
                            if os.path.exists(volume_parsed["name"]):
                                volume_parsed["used"] = convert_size(get_folder_size(volume_parsed["name"]))
                            else:
                                volume_parsed["used"] = "N/A"
                                
                            volume_parsed["type"] = SinaraVolume.get_volume_type_description(volume)   
                            volume_parsed["exists"] = os.path.exists(volume_parsed["name"])   
                        
                        else:
                            raise Exception(f"Unsupported volume type {volume['Type']}")
                        volumes_of_removed_servers[container_name]["volumes"].append(volume_parsed)
                    
                except Exception as e:
                    print(f"{fc.RED}\nServer config at {sinara_removed_servers[removed_server]} cannot be read, skipping{fc.RESET}")

            SinaraVolume.print_as_table(args, volumes_of_removed_servers, "Removed Servers")
