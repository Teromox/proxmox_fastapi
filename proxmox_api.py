import requests
import json
from settings import AUTH_TXT
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import random
import string
import urllib.parse
import subprocess

def make_password(length=8):
    return "".join([random.choice(string.ascii_letters) for _ in range(length)])

def make_keypair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    public_key = private_key.public_key()
    openssh_public = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH
    )
    
    return openssh_public.decode('utf-8'), pem_private.decode('utf-8')

BASE_URL = "https://59.23.119.207:8006"

def get_next_vmid():
    response = requests.get(
        url=BASE_URL+"/api2/json/cluster/nextid",
        headers={
            "Authorization": AUTH_TXT
        },
        verify=False
    )
    res = json.loads(response.text)
    return res.get("data", 0)

def create_vm(vmid):
    data = {
        "newid": str(vmid),
        "name": f"vm-{vmid}",
        "full": 1
    }
    response = requests.post(
        url=BASE_URL+"/api2/json/nodes/proxmox/qemu/9004/clone",
        headers={
            "Authorization": AUTH_TXT,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
        },
        data=data,
        verify=False
    )
    res = json.loads(response.text)
    return res.get("data", 0)

# def setting_vm(username, vmid):
#     password = make_password()
#     public_pem, private_pem = make_keypair()
    
#     clean_sshkey = public_pem.strip().replace('\n', '').replace('\r', '')
#     encoded_key = urllib.parse.quote(clean_sshkey, safe='')
    
#     ipconfig_val = f"ip=10.0.0.{vmid}/24,gw=10.0.0.1"
#     encoded_ipconfig = urllib.parse.quote(ipconfig_val, safe='=,./: ')
    
#     body = "&".join([
#         f"sshkeys={encoded_key}",
#         f"ciuser={urllib.parse.quote(username, safe='')}",
#         f"cipassword={urllib.parse.quote(password, safe='')}",
#         f"ipconfig0={encoded_ipconfig}",
#     ])
    
#     response = requests.put(
#         url=BASE_URL + f"/api2/json/nodes/proxmox/qemu/{vmid}/config",
#         headers={
#             "Authorization": AUTH_TXT,
#             "Content-Type": "application/x-www-form-urlencoded"
#         },
#         data=body,
#         verify=False
#     )
    
#     return response.text, private_pem, password

def setting_vm(username, vmid):
    password = make_password()
    public_pem, private_pem = make_keypair()
    
    clean_sshkey = public_pem.strip().replace('\n', '').replace('\r', '')
    
    encoded_once = urllib.parse.quote(clean_sshkey, safe='')
    encoded_twice = urllib.parse.quote(encoded_once, safe='')
    
    body = "&".join([
        f"sshkeys={encoded_twice}",
        f"ciuser={username}",
        f"cipassword={password}",
        f"ipconfig0=ip%3D10.0.0.{vmid}%2F24%2Cgw%3D10.0.0.1",
    ])
    
    response = requests.put(
        url=BASE_URL + f"/api2/json/nodes/proxmox/qemu/{vmid}/config",
        headers={
            "Authorization": AUTH_TXT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=body,
        verify=False,
    )
    return response.text, private_pem, password



def add_disk(vmid):
    data = {
        "disk": "scsi0",
        "size": f"20G"
    }
    response = requests.post(
        url=BASE_URL+f"/api2/json/nodes/proxmox/qemu/{vmid}/resize",
        headers={
            "Authorization": AUTH_TXT
        },
        data=data,
        verify=False
    )
    res = json.loads(response.text)
    return res.get("data", 0)

def set_boot(vmid):
    data = {
        "boot": "order=scsi0;net0"
    }
    response = requests.post(
        url=BASE_URL+f"/api2/json/nodes/proxmox/qemu/{vmid}/config",
        headers={
            "Authorization": AUTH_TXT
        },
        data=data,
        verify=False
    )
    res = json.loads(response.text)
    return res.get("data", 0)

def start_vm(vmid):
    response = requests.post(
        url=BASE_URL+f"/api2/json/nodes/proxmox/qemu/{vmid}/status/start",
        headers={
            "Authorization": AUTH_TXT
        },
        verify=False
    )
    res = json.loads(response.text)
    return res.get("data", 0)

def stop_vm(vmid):
    response = requests.post(
        url=BASE_URL+f"/api2/json/nodes/proxmox/qemu/{vmid}/status/stop",
        headers={
            "Authorization": AUTH_TXT
        },
        verify=False
    )
    res = json.loads(response.text)
    return res.get("data", 0)

def restart_vm(vmid):
    response = requests.post(
        url=BASE_URL+f"/api2/json/nodes/proxmox/qemu/{vmid}/status/reboot",
        headers={
            "Authorization": AUTH_TXT
        },
        verify=False
    )
    res = json.loads(response.text)
    return res.get("data", 0)

def get_vm_status(vmid):
    response = requests.get(
        url=BASE_URL + f"/api2/json/nodes/proxmox/qemu/{vmid}/status/current",
        headers={
            "Authorization": AUTH_TXT
        },
        verify=False
    )
    res = json.loads(response.text)
    return res.get("data", {})

def delete_vm(vmid):
    response = requests.delete(
        url=BASE_URL + f"/api2/json/nodes/proxmox/qemu/{vmid}",
        headers={
            "Authorization": AUTH_TXT
        },
        params={
            "purge": 1,
            "destroy-unreferenced-disks": 1
        },
        verify=False
    )
    res = json.loads(response.text)
    return res.get("data", 0)

def add_port_forwarding(external_port, internal_ip, internal_port=22):
    for proto in ["tcp", "udp"]:
        subprocess.run([
            "iptables", "-t", "nat", "-A", "PREROUTING",
            "-p", proto, "--dport", str(external_port),
            "-j", "DNAT", "--to-destination", f"{internal_ip}:{internal_port}"
        ], check=True)
        
        subprocess.run([
            "iptables", "-A", "FORWARD",
            "-p", proto, "-d", internal_ip,
            "--dport", str(internal_port),
            "-j", "ACCEPT"
        ], check=True)
    
    subprocess.run(["netfilter-persistent", "save"], check=True)

def delete_port_forwarding(external_port, internal_ip, internal_port=22):
    for proto in ["tcp", "udp"]:
        subprocess.run([
            "iptables", "-t", "nat", "-D", "PREROUTING",
            "-p", proto, "--dport", str(external_port),
            "-j", "DNAT", "--to-destination", f"{internal_ip}:{internal_port}"
        ], check=True)
        
        subprocess.run([
            "iptables", "-D", "FORWARD",
            "-p", proto, "-d", internal_ip,
            "--dport", str(internal_port),
            "-j", "ACCEPT"
        ], check=True)
    
    subprocess.run(["netfilter-persistent", "save"], check=True)
    
# st = setting_vm("user1234", 102)
# print(st)
# f = open("pk.pem", "w")
# f.write(st[1])
# f.close()
# # print(make_keypair())
# print(restart_vm(102))