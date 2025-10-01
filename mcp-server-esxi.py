# esxi_mcp_server.py
import argparse
import ssl
import atexit
import time
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from mcp.server.fastmcp import FastMCP

app = FastMCP("esxi-info")

# -----------------------
# Helpers
# -----------------------
def connect_esxi(host, user, password, port=443):
    """
    Connect to a standalone ESXi host and return the service instance.
    """
    context = ssl._create_unverified_context()
    si = SmartConnect(
        host=host,
        user=user,
        pwd=password,
        port=port,
        sslContext=context
    )
    atexit.register(Disconnect, si)
    return si


def get_host_object(content):
    """Return the HostSystem object for standalone ESXi."""
    for child in content.rootFolder.childEntity:
        if hasattr(child, 'hostFolder'):
            for compute in child.hostFolder.childEntity:
                for h in compute.host:
                    return h
    for dc in content.rootFolder.childEntity:
        if isinstance(dc, vim.HostSystem):
            return dc
    return None

# -----------------------
# ESXi Info
# -----------------------
def fetch_esxi_info(host, user, password):
    """
    Fetch CPU, memory, storage, VM details, and live usage stats from ESXi.
    """
    si = connect_esxi(host, user, password)
    content = si.RetrieveContent()
    host_obj = get_host_object(content)

    if not host_obj:
        return {"error": "Could not find ESXi host system."}

    hw = host_obj.hardware
    summary = host_obj.summary
    stats = summary.quickStats

    # CPU & Memory (static + usage %)
    cpu_cores = hw.cpuInfo.numCpuCores
    cpu_threads = hw.cpuInfo.numCpuThreads
    cpu_hz = hw.cpuInfo.hz / 1e9  # GHz
    memory_gb = hw.memorySize / (1024 ** 3)

    cpu_usage_mhz = stats.overallCpuUsage
    cpu_total_mhz = hw.cpuInfo.hz * hw.cpuInfo.numCpuCores / 1e6
    cpu_usage_pct = round((cpu_usage_mhz / cpu_total_mhz) * 100, 2) if cpu_total_mhz > 0 else 0

    memory_usage_mb = stats.overallMemoryUsage
    memory_usage_pct = round((memory_usage_mb / (memory_gb * 1024)) * 100, 2) if memory_gb > 0 else 0

    # Datastores
    datastores = []
    for ds in host_obj.datastore:
        ds_summary = ds.summary
        capacity_gb = ds_summary.capacity / (1024 ** 3)
        free_gb = ds_summary.freeSpace / (1024 ** 3)
        used_pct = round(((capacity_gb - free_gb) / capacity_gb) * 100, 2) if capacity_gb > 0 else 0
        datastores.append({
            "name": ds_summary.name,
            "capacity_GB": round(capacity_gb, 2),
            "free_GB": round(free_gb, 2),
            "used_pct": used_pct
        })

    # VMs
    vms = []
    for vm in host_obj.vm:
        summary = vm.summary
        vm_stats = summary.quickStats
        vms.append({
            "name": summary.config.name,
            "cpu": summary.config.numCpu,
            "memory_MB": summary.config.memorySizeMB,
            "power_state": str(summary.runtime.powerState),
            "guest_OS": summary.config.guestFullName,
            "cpu_usage_MHz": vm_stats.overallCpuUsage,
            "memory_usage_MB": vm_stats.guestMemoryUsage
        })

    return {
        "host": host,
        "cpu": {
            "cores": cpu_cores,
            "threads": cpu_threads,
            "speed_GHz": round(cpu_hz, 2),
            "usage_pct": cpu_usage_pct,
            "usage_MHz": cpu_usage_mhz
        },
        "memory": {
            "total_GB": round(memory_gb, 2),
            "usage_MB": memory_usage_mb,
            "usage_pct": memory_usage_pct
        },
        "storage": datastores,
        "vm_count": len(vms),
        "vms": vms
    }

# -----------------------
# VM Info
# -----------------------
def fetch_vm_info(host, user, password, vm_name):
    """
    Fetch details for a specific VM on the ESXi host.
    """
    si = connect_esxi(host, user, password)
    content = si.RetrieveContent()
    host_obj = get_host_object(content)

    if not host_obj:
        return {"error": "Could not find ESXi host system."}

    for vm in host_obj.vm:
        summary = vm.summary
        if summary.config.name.lower() == vm_name.lower():
            vm_stats = summary.quickStats
            return {
                "name": summary.config.name,
                "cpu": summary.config.numCpu,
                "memory_MB": summary.config.memorySizeMB,
                "power_state": str(summary.runtime.powerState),
                "guest_OS": summary.config.guestFullName,
                "cpu_usage_MHz": vm_stats.overallCpuUsage,
                "memory_usage_MB": vm_stats.guestMemoryUsage
            }

    return {"error": f"VM '{vm_name}' not found on host {host}"}

# -----------------------
# Datastore Images
# -----------------------

def fetch_datastore_images(host, user, password):
    """
    Fetch ISO and VMDK images stored in ESXi datastores.
    """
    si = connect_esxi(host, user, password)
    content = si.RetrieveContent()

    result = {}
    for datacenter in content.rootFolder.childEntity:
        if hasattr(datacenter, 'datastore'):
            for datastore in datacenter.datastore:
                browser = datastore.browser
                search_spec = vim.HostDatastoreBrowserSearchSpec()
                search_spec.matchPattern = ["*.iso", "*.vmdk"]

                task = browser.SearchDatastoreSubFolders_Task(f"[{datastore.name}]", search_spec)
                while task.info.state in [vim.TaskInfo.State.running, vim.TaskInfo.State.queued]:
                    time.sleep(1)

                if task.info.state == vim.TaskInfo.State.success:
                    images = []
                    for folder in task.info.result:
                        for f in folder.file:
                            images.append({
                                "name": f.path,
                                "size_MB": (getattr(f, 'fileSize', 0) or 0) // (1024 * 1024),
                                "folder": folder.folderPath
                            })
                    result[datastore.name] = images
                else:
                    result[datastore.name] = {"error": str(task.info.error)}

    return result

# -----------------------
# MCP Tools
# -----------------------
@app.tool()
def get_esxi_info(host: str, user: str, password: str) -> dict:
    """
    Fetch overall information from a standalone ESXi host.
    """
    return fetch_esxi_info(host, user, password)


@app.tool()
def get_vm_info(host: str, user: str, password: str, vm_name: str) -> dict:
    """
    Fetch information about a specific VM on a standalone ESXi host.

    Args:
        host: ESXi IP or FQDN
        user: Username (e.g., root)
        password: Password for ESXi
        vm_name: Name of the VM to fetch details for
    """
    return fetch_vm_info(host, user, password, vm_name)

@app.tool()
def get_datastore_images(host: str, user: str, password: str) -> dict:
    """Fetch ISO and VMDK images from all datastores on a standalone ESXi host."""
    return fetch_datastore_images(host, user, password)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ESXi MCP Server / CLI Tool")
    parser.add_argument("--host", help="ESXi host IP or FQDN")
    parser.add_argument("--user", help="ESXi username (e.g., root)")
    parser.add_argument("--password", help="ESXi password")
    parser.add_argument("--vm", help="VM name (optional, fetch details for this VM only)")
    parser.add_argument("--images", action="store_true", help="Fetch datastore images")

    args = parser.parse_args()

    if args.host and args.user and args.password:
        if args.images:
            result = fetch_datastore_images(args.host, args.user, args.password)
        elif args.vm:
            result = fetch_vm_info(args.host, args.user, args.password, args.vm)
        else:
            result = fetch_esxi_info(args.host, args.user, args.password)
        import json
        print(json.dumps(result, indent=2))
    else:
        # Run as MCP server if no args given
        app.run()
