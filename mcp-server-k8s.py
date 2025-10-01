from mcp.server.fastmcp import FastMCP
from kubernetes import client, config
from typing import List
import argparse

# Load kubeconfig (outside cluster) or incluster config (inside cluster)
try:
    config.load_kube_config(config_file="C:\\Users\\HP\\AppData\\Roaming\\Claude\\.kube\\config")
except Exception:
    config.load_incluster_config()

core_api = client.CoreV1Api()

# Create MCP server
mcp = FastMCP("k8s-mcp")

# --- MCP TOOLS ---
@mcp.tool()
async def get_nodes() -> List[str]:
    """
    List all nodes in the cluster.
    """
    nodes = core_api.list_node()
    return [node.metadata.name for node in nodes.items]

@mcp.tool()
async def get_namespaces() -> List[str]:
    """
    List all namespaces in the cluster.
    """
    namespaces = core_api.list_namespace()
    return [ns.metadata.name for ns in namespaces.items]

@mcp.tool()
async def get_pods(namespace: str = "default") -> List[str]:
    """
    List all pods in a namespace.
    """
    pods = core_api.list_namespaced_pod(namespace)
    return [pod.metadata.name for pod in pods.items]

@mcp.tool()
async def get_logs(pod: str, namespace: str = "default") -> str:
    """
    Get logs for a specific pod in a namespace.
    """
    return core_api.read_namespaced_pod_log(name=pod, namespace=namespace)

@mcp.tool()
async def get_events(namespace: str = "default") -> List[str]:
    """
    List recent events in a namespace.
    """
    events = core_api.list_namespaced_event(namespace)
    return [f"{event.metadata.name}: {event.message}" for event in events.items]

@mcp.tool()
async def get_deployments(namespace: str = "default") -> List[str]:
    """
    List all deployments in a namespace.
    """
    apps_api = client.AppsV1Api()
    deployments = apps_api.list_namespaced_deployment(namespace)
    return [dep.metadata.name for dep in deployments.items]

@mcp.tool()
async def get_services(namespace: str = "default") -> List[str]:
    """
    List all services in a namespace.
    """
    services = core_api.list_namespaced_service(namespace)
    return [svc.metadata.name for svc in services.items]

@mcp.tool()
async def get_configmaps(namespace: str = "default") -> List[str]:
    """
    List all configmaps in a namespace.
    """
    configmaps = core_api.list_namespaced_config_map(namespace)
    return [cm.metadata.name for cm in configmaps.items]

@mcp.tool()
async def get_secrets(namespace: str = "default") -> List[str]:
    """
    List all secrets in a namespace.
    """
    secrets = core_api.list_namespaced_secret(namespace)
    return [sec.metadata.name for sec in secrets.items]

@mcp.tool()
async def get_persistent_volumes() -> List[str]:
    """
    List all persistent volumes in the cluster.
    """
    pvs = core_api.list_persistent_volume()
    return [pv.metadata.name for pv in pvs.items]

@mcp.tool()
async def get_persistent_volume_claims(namespace: str = "default") -> List[str]:
    """
    List all persistent volume claims in a namespace.
    """
    pvcs = core_api.list_namespaced_persistent_volume_claim(namespace)
    return [pvc.metadata.name for pvc in pvcs.items]

@mcp.tool()
async def get_cluster_info() -> str:
    """
    Get basic cluster information.
    """
    version_api = client.VersionApi()
    version_info = version_api.get_code()
    return f"Cluster Version: {version_info.git_version}, Platform: {version_info.platform}"

@mcp.tool()
async def get_node_metrics() -> List[str]:
    """
    List node metrics (requires metrics-server to be deployed).
    """
    try:
        metrics_api = client.CustomObjectsApi()
        metrics = metrics_api.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
        return [f"{item['metadata']['name']}: CPU {item['usage']['cpu']}, Memory {item['usage']['memory']}" for item in metrics['items']]
    except client.exceptions.ApiException as e:
        return [f"Error fetching node metrics: {e}"]
    
@mcp.tool()
async def get_pod_metrics(namespace: str = "default") -> List[str]:
    """
    List pod metrics in a namespace (requires metrics-server to be deployed).
    """
    try:
        metrics_api = client.CustomObjectsApi()
        metrics = metrics_api.list_namespaced_custom_object("metrics.k8s.io", "v1beta1", namespace, "pods")
        return [f"{item['metadata']['name']}: CPU {item['usage']['cpu']}, Memory {item['usage']['memory']}" for item in metrics['items']]
    except client.exceptions.ApiException as e:
        return [f"Error fetching pod metrics: {e}"]
    
@mcp.tool()
async def get_resource_quota(namespace: str = "default") -> List[str]:
    """
    List resource quotas in a namespace.
    """
    quotas = core_api.list_namespaced_resource_quota(namespace)
    return [f"{rq.metadata.name}: {rq.status.hard}" for rq in quotas.items]

@mcp.tool()
async def create_namespace(name: str) -> str:
    """
    Create a new namespace.
    """
    body = client.V1Namespace(metadata=client.V1ObjectMeta(name=name))
    try:
        core_api.create_namespace(body)
        return f"Namespace '{name}' created successfully."
    except client.exceptions.ApiException as e:
        return f"Error creating namespace: {e}"

@mcp.tool()
async def create_deployment(name: str, image: str, namespace: str = "default", replicas: int = 1) -> str:
    """
    Create a new deployment in a namespace.
    """
    apps_api = client.AppsV1Api()
    body = client.V1Deployment(
        metadata=client.V1ObjectMeta(name=name),
        spec=client.V1DeploymentSpec(
            replicas=replicas,
            selector={'matchLabels': {'app': name}},
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={'app': name}),
                spec=client.V1PodSpec(containers=[client.V1Container(name=name, image=image)])
            )
        )
    )
    try:
        apps_api.create_namespaced_deployment(namespace=namespace, body=body)
        return f"Deployment '{name}' created successfully in namespace '{namespace}'."
    except client.exceptions.ApiException as e:
        return f"Error creating deployment: {e}"
    
@mcp.tool()
async def create_service(name: str, port: int, target_port: int, namespace: str = "default") -> str:
    """
    Create a new service in a namespace.
    """
    body = client.V1Service(
        metadata=client.V1ObjectMeta(name=name),
        spec=client.V1ServiceSpec(
            selector={'app': name},
            ports=[client.V1ServicePort(port=port, target_port=target_port)]
        )
    )
    try:
        core_api.create_namespaced_service(namespace=namespace, body=body)
        return f"Service '{name}' created successfully in namespace '{namespace}'."
    except client.exceptions.ApiException as e:
        return f"Error creating service: {e}"

@mcp.tool()
async def create_configmap(name: str, data: dict, namespace: str = "default") -> str:
    """
    Create a new configmap in a namespace.
    """
    body = client.V1ConfigMap(metadata=client.V1ObjectMeta(name=name), data=data)
    try:
        core_api.create_namespaced_config_map(namespace=namespace, body=body)
        return f"ConfigMap '{name}' created successfully in namespace '{namespace}'."
    except client.exceptions.ApiException as e:
        return f"Error creating configmap: {e}"

@mcp.tool()
async def create_secret(name: str, data: dict, namespace: str = "default") -> str:
    """
    Create a new secret in a namespace.
    """
    body = client.V1Secret(metadata=client.V1ObjectMeta(name=name), string_data=data)
    try:
        core_api.create_namespaced_secret(namespace=namespace, body=body)
        return f"Secret '{name}' created successfully in namespace '{namespace}'."
    except client.exceptions.ApiException as e:
        return f"Error creating secret: {e}"
    
@mcp.tool()
async def delete_namespace(name: str) -> str:
    """
    Delete a namespace.
    """
    try:
        core_api.delete_namespace(name=name)
        return f"Namespace '{name}' deleted successfully."
    except client.exceptions.ApiException as e:
        return f"Error deleting namespace: {e}"

@mcp.tool()
async def delete_pod(name: str, namespace: str = "default") -> str:
    """
    Delete a pod in a namespace.
    """
    try:
        core_api.delete_namespaced_pod(name=name, namespace=namespace)
        return f"Pod '{name}' in namespace '{namespace}' deleted successfully."
    except client.exceptions.ApiException as e:
        return f"Error deleting pod: {e}"
    

# --- SERVER SETUP ---
def server():
    """ "Run the MCP server."""
    parser = argparse.ArgumentParser(description="MCP Kubernetes Server")
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport mechanism to use (stdio or sse or streamable-http)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to use for sse or streamable-http server",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to use for sse or streamable-http server",
    )

    args = parser.parse_args()
    mcp.settings.port = args.port
    mcp.settings.host = args.host


    # Run the server
    mcp.run(transport=args.transport)


# --- ENTRYPOINT ---
if __name__ == "__main__":
    server()
