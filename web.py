import sqlite3
import fastapi
import uvicorn
from pydantic import BaseModel
import proxmox_api
from settings import WEB_API_KEY, MIN_PORT, MAX_PORT

def start_db():
    con = sqlite3.connect('db.db')
    cur = con.cursor()
    return con, cur

def get_blank_port():
    con, cur = start_db()
    cur.execute("SELECT ext_port FROM nat_table")
    used_ports = [row[0] for row in cur.fetchall()]
    con.close()
    for port in range(MIN_PORT, MAX_PORT):
        if port not in used_ports:
            return port
    raise Exception("No available ports")

app = fastapi.FastAPI()

def is_exist_port(ext_port):
    con, cur = start_db()
    cur.execute("SELECT * FROM nat_table WHERE ext_port=?", (ext_port,))
    result = cur.fetchone()
    con.close()
    return True if result else False

def get_exist_port(ext_port):
    con, cur = start_db()
    cur.execute("SELECT * FROM nat_table WHERE ext_port=?", (ext_port,))
    result = cur.fetchone()
    con.close()
    return result if result else False

def adder_port(ext_port, ip, in_port):
    try:
        if is_exist_port(ext_port):
            print(f"Port {ext_port} is already in use")
            return False
        proxmox_api.add_port_forwarding(
            external_port=ext_port,
            internal_ip=ip,
            internal_port=in_port
        )
    except Exception as e:
        print(e)
        return False
    else:
        con, cur = start_db()
        cur.execute("INSERT INTO nat_table (ext_port, ip, in_port) VALUES (?, ?, ?)", (ext_port, ip, in_port))
        con.commit()
        con.close()
        return True
    
def remover_port(ext_port):
    try:
        if not is_exist_port(ext_port):
            return False
        _, internal_ip, internal_port = get_exist_port(ext_port)
        proxmox_api.delete_port_forwarding(ext_port, internal_ip, internal_port)
    except Exception as e:
        return False
    else:
        con, cur = start_db()
        cur.execute("DELETE FROM nat_table WHERE ext_port=?", (ext_port,))
        con.commit()
        con.close()
        return True
    
def make_vm(vmid ,username):
    proxmox_api.create_vm(vmid)
    _, private_pem, password = proxmox_api.setting_vm(username, vmid)
    proxmox_api.add_disk(vmid)
    proxmox_api.set_boot(vmid)
    proxmox_api.start_vm(vmid)
    return vmid, private_pem, password

def remove_vm(vmid):
    proxmox_api.stop_vm(vmid)
    proxmox_api.delete_vm(vmid)
    con, cur = start_db()
    cur.execute("SELECT ext_port FROM nat_table WHERE ip=?", (f"10.0.0.{vmid}",))
    ports = cur.fetchall()
    for port in ports:
        remover_port(port[0])
    con.close()

def remaker_vm(username, vmid):
    proxmox_api.stop_vm(vmid)
    proxmox_api.delete_vm(vmid)
    return make_vm(vmid, username)

def check_authentication(key):
    return key == WEB_API_KEY

NOT_AUTH = fastapi.HTTPException(status_code=401, detail="Unauthorized")

@app.get("/")
def read_root():
    return {"Hello": "World"}

class AddPort(BaseModel):
    ext_port: int
    ip: str
    in_port: int
    
@app.post("/api/port")
def add_port(addport: AddPort, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key):
        raise NOT_AUTH
    if addport.ext_port < MIN_PORT or addport.ext_port > MAX_PORT:
        raise fastapi.HTTPException(status_code=400, detail=f"Port must be between {MIN_PORT} and {MAX_PORT}")
    if adder_port(addport.ext_port, addport.ip, addport.in_port):
        return {"message": "Port added successfully"}
    raise fastapi.HTTPException(status_code=400, detail="Failed to add port")

class RemovePort(BaseModel):
    ext_port: int

@app.delete("/api/port")
def remove_port(removeport: RemovePort, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key):
        raise NOT_AUTH
    if remover_port(removeport.ext_port):
        return {"message": "Port removed successfully"}
    raise fastapi.HTTPException(status_code=400, detail="Failed to remove port")

@app.get("/api/port")
def exist_port(ext_port: int, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key):
        raise NOT_AUTH
    return {"data": is_exist_port(ext_port)}

@app.get("/api/ip/port")
def get_ip_port(ip: str, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key):
        raise NOT_AUTH
    con, cur = start_db()
    cur.execute("SELECT * FROM nat_table WHERE ip=?", (ip,))
    result = cur.fetchall()
    con.close()
    return {"data": result}

@app.post("/api/vm")
def create_vm(username: str, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key):
        raise NOT_AUTH
    vmid = proxmox_api.get_next_vmid()
    vmid, private_pem, password = make_vm(vmid, username)
    ssh_port = get_blank_port()
    adder_port(ssh_port, f"10.0.0.{vmid}", 22)
    return {
        "vmid": vmid, 
        "private_key": private_pem, 
        "password": password,
        "ip": f"10.0.0.{vmid}",
        "ssh_port": ssh_port
    }

@app.delete("/api/vm")
def delete_vm(vmid: int, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key):
        raise NOT_AUTH
    remove_vm(vmid)
    return {"message": "VM deleted successfully"}

@app.put("/api/vm")
def remake_vm(username: str, vmid: int, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key):
        raise NOT_AUTH
    vmid, private_pem, password = remaker_vm(username, vmid)
    return {"vmid": vmid, "private_key": private_pem, "password": password}
        
@app.get("/api/vm/status")
def get_vm_status(vmid: int, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key):
        raise NOT_AUTH
    return {"data": proxmox_api.get_vm_status(vmid)}

@app.get("/api/vm/blank_port")
def get_blanked_port(api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key):
        raise NOT_AUTH
    return {"data": get_blank_port()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9071)