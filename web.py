import sqlite3
import fastapi
import uvicorn
import threading
from pydantic import BaseModel
from contextlib import contextmanager
import proxmox_api
from settings import WEB_API_KEY, MIN_PORT, MAX_PORT

write_lock = threading.Lock()
app = fastapi.FastAPI()

@contextmanager
def get_db(timeout=15):
    conn = sqlite3.connect('db.db', timeout=timeout)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def get_blank_port():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT ext_port FROM nat_table")
        used_ports = [row[0] for row in cur.fetchall()]
    for port in range(MIN_PORT, MAX_PORT):
        if port not in used_ports:
            return port
    raise Exception("No available ports")

def is_exist_port(ext_port):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM nat_table WHERE ext_port=?", (ext_port,))
        return cur.fetchone() is not None

def adder_port(ext_port, ip, in_port):
    try:
        proxmox_api.add_port_forwarding(ext_port, ip, in_port)
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO nat_table (ext_port, ip, in_port) VALUES (?, ?, ?)", (ext_port, ip, in_port))
            conn.commit()
        return True
    except:
        return False

def remover_port(ext_port):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT ip, in_port FROM nat_table WHERE ext_port=?", (ext_port,))
        res = cur.fetchone()
        if not res: return False
        ip, in_port = res[0], res[1]
        try:
            proxmox_api.delete_port_forwarding(ext_port, ip, in_port)
            cur.execute("DELETE FROM nat_table WHERE ext_port=?", (ext_port,))
            conn.commit()
            return True
        except:
            return False

def check_authentication(key):
    return key == WEB_API_KEY

NOT_AUTH = fastapi.HTTPException(status_code=401, detail="Unauthorized")

@app.get("/api/vm/status")
def get_vm_status(vmid: int, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key): raise NOT_AUTH
    return {"data": proxmox_api.get_vm_status(vmid)}

@app.get("/api/port")
def check_port(ext_port: int, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key): raise NOT_AUTH
    return {"data": is_exist_port(ext_port)}

@app.post("/api/vm")
def create_vm(username: str, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key): raise NOT_AUTH
    with write_lock:
        vmid = proxmox_api.get_next_vmid()
        ssh_port = get_blank_port()
        try:
            proxmox_api.create_vm(vmid)
            _, private_pem, password = proxmox_api.setting_vm(username, vmid)
            proxmox_api.add_disk(vmid)
            proxmox_api.set_boot(vmid)
            proxmox_api.start_vm(vmid)
            adder_port(ssh_port, f"10.0.0.{vmid}", 22)
            return {"vmid": vmid, "private_key": private_pem, "password": password, "ip": f"10.0.0.{vmid}", "ssh_port": ssh_port}
        except Exception as e:
            raise fastapi.HTTPException(status_code=500, detail=str(e))

@app.delete("/api/vm")
def delete_vm(vmid: int, api_key: str = fastapi.Header(...)):
    if not check_authentication(api_key): raise NOT_AUTH
    with write_lock:
        try:
            proxmox_api.stop_vm(vmid)
            proxmox_api.delete_vm(vmid)
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT ext_port FROM nat_table WHERE ip=?", (f"10.0.0.{vmid}",))
                ports = [row[0] for row in cur.fetchall()]
                for p in ports: remover_port(p)
            return {"message": "success"}
        except Exception as e:
            raise fastapi.HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9071)
