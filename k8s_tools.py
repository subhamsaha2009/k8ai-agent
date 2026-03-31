from kubernetes import client, config

try:
    config.load_kube_config()
except Exception as e:
    print(f"[Warning] Could not load kubeconfig: {e}")


def _sanitize_name(name):
    """Convert any string to a valid K8s RFC 1123 name (lowercase, hyphens only)."""
    import re
    name = name.lower().replace("_", "-").replace(" ", "-")
    name = re.sub(r"[^a-z0-9\-]", "", name)
    name = name.strip("-")
    return name[:63]  # K8s max name length


def list_pods(namespace="default"):
    """List all pods and their current status."""
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace)
    result = []
    for pod in pods.items:
        container_statuses = []
        for c in (pod.status.container_statuses or []):
            state = c.state
            state_str = "unknown"
            reason = None
            message = None
            if state.running:
                state_str = "running"
            elif state.waiting:
                state_str = "waiting"
                reason = state.waiting.reason
                message = state.waiting.message
            elif state.terminated:
                state_str = "terminated"
                reason = state.terminated.reason
                message = state.terminated.message

            container_statuses.append({
                "name": c.name,
                "ready": c.ready,
                "restart_count": c.restart_count,
                "state": state_str,
                "reason": reason,
                "message": message,
            })

        result.append({
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "status": pod.status.phase,
            "node": pod.spec.node_name,
            "containers": container_statuses,
        })
    return result


def describe_pod(pod_name, namespace="default"):
    """Get full details and events for a pod — reveals ImagePullBackOff, OOMKilled, CrashLoopBackOff etc."""
    v1 = client.CoreV1Api()
    pod = v1.read_namespaced_pod(pod_name, namespace)
    events = v1.list_namespaced_event(
        namespace,
        field_selector=f"involvedObject.name={pod_name}"
    )

    conditions = []
    for c in (pod.status.conditions or []):
        conditions.append({
            "type": c.type,
            "status": c.status,
            "reason": c.reason,
            "message": c.message,
        })

    event_list = []
    for e in events.items:
        event_list.append({
            "reason": e.reason,
            "message": e.message,
            "count": e.count,
            "type": e.type,
        })

    init_statuses = []
    for c in (pod.status.init_container_statuses or []):
        init_statuses.append({
            "name": c.name,
            "ready": c.ready,
            "restart_count": c.restart_count,
        })

    return {
        "phase": pod.status.phase,
        "node": pod.spec.node_name,
        "conditions": conditions,
        "init_containers": init_statuses,
        "events": event_list,
    }


def get_pod_logs(pod_name, namespace="default", lines=100, previous=False):
    """Get logs from a running or recently failed pod."""
    v1 = client.CoreV1Api()
    try:
        logs = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            tail_lines=lines,
            previous=previous,
        )
        return logs if logs else "(no logs available)"
    except Exception as e:
        return f"Error fetching logs: {e}"


def deploy_pod(name, image, namespace="default", env_vars=None):
    """Deploy a new pod to the cluster."""
    v1 = client.CoreV1Api()

    env = []
    if env_vars:
        for k, v in env_vars.items():
            env.append(client.V1EnvVar(name=k, value=v))

    pod_manifest = client.V1Pod(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        spec=client.V1PodSpec(
            containers=[
                client.V1Container(
                    name=name,
                    image=image,
                    env=env if env else None,
                )
            ],
            restart_policy="Always",
        ),
    )

    v1.create_namespaced_pod(namespace, pod_manifest)
    return f"Pod '{name}' deployed with image '{image}' in namespace '{namespace}'"


def delete_pod(pod_name, namespace="default"):
    """Delete a pod — forces a restart if managed by a controller."""
    v1 = client.CoreV1Api()
    v1.delete_namespaced_pod(pod_name, namespace)
    return f"Pod '{pod_name}' deleted from namespace '{namespace}'"


def create_configmap(name, html_content, namespace="default"):
    """Create a ConfigMap containing custom HTML content to serve via nginx."""
    name = _sanitize_name(name)
    v1 = client.CoreV1Api()
    configmap = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        data={"index.html": html_content},
    )
    v1.create_namespaced_config_map(namespace, configmap)
    return f"ConfigMap '{name}' created in namespace '{namespace}'"


def update_configmap(name, html_content, namespace="default"):
    """Update an existing ConfigMap with new HTML content."""
    name = _sanitize_name(name)
    v1 = client.CoreV1Api()
    configmap = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        data={"index.html": html_content},
    )
    v1.replace_namespaced_config_map(name, namespace, configmap)
    return f"ConfigMap '{name}' updated in namespace '{namespace}'"


def deploy_web_pod(name, namespace="default", configmap_name=None, image="nginx:latest"):
    """Deploy an nginx pod optionally mounting a ConfigMap as the web content.
    Use configmap_name to serve custom HTML. Creates a LoadBalancer service to expose it."""
    name = _sanitize_name(name)
    if configmap_name:
        configmap_name = _sanitize_name(configmap_name)
    v1 = client.CoreV1Api()

    volumes = []
    volume_mounts = []

    if configmap_name:
        volumes.append(client.V1Volume(
            name="html-content",
            config_map=client.V1ConfigMapVolumeSource(name=configmap_name),
        ))
        volume_mounts.append(client.V1VolumeMount(
            name="html-content",
            mount_path="/usr/share/nginx/html",
        ))

    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels={"app": name},
        ),
        spec=client.V1PodSpec(
            containers=[
                client.V1Container(
                    name="nginx",
                    image=image,
                    ports=[client.V1ContainerPort(container_port=80)],
                    volume_mounts=volume_mounts if volume_mounts else None,
                )
            ],
            volumes=volumes if volumes else None,
            restart_policy="Always",
        ),
    )
    v1.create_namespaced_pod(namespace, pod)
    return f"Web pod '{name}' deployed with image '{image}'"


def create_service(name, pod_name, port=80, namespace="default", service_type="LoadBalancer"):
    """Create a Kubernetes Service to expose a pod. Use service_type='LoadBalancer' for external access via public IP."""
    name = _sanitize_name(name)
    pod_name = _sanitize_name(pod_name)
    v1 = client.CoreV1Api()
    service = client.V1Service(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        spec=client.V1ServiceSpec(
            selector={"app": pod_name},
            ports=[client.V1ServicePort(port=port, target_port=80)],
            type=service_type,
        ),
    )
    v1.create_namespaced_service(namespace, service)
    return f"Service '{name}' created as {service_type} on port {port}"


def get_service(name, namespace="default"):
    """Get a service and return its external IP (LoadBalancer IP). Poll this after creating a LoadBalancer service."""
    v1 = client.CoreV1Api()
    svc = v1.read_namespaced_service(name, namespace)
    ingress = svc.status.load_balancer.ingress
    external_ip = None
    if ingress:
        external_ip = ingress[0].ip or ingress[0].hostname

    return {
        "name": svc.metadata.name,
        "type": svc.spec.type,
        "cluster_ip": svc.spec.cluster_ip,
        "external_ip": external_ip,
        "port": svc.spec.ports[0].port if svc.spec.ports else None,
        "url": f"http://{external_ip}" if external_ip else "Pending (external IP not assigned yet)",
    }


def delete_service(name, namespace="default"):
    """Delete a Kubernetes Service."""
    v1 = client.CoreV1Api()
    v1.delete_namespaced_service(name, namespace)
    return f"Service '{name}' deleted from namespace '{namespace}'"


def exec_in_pod(pod_name, command, namespace="default"):
    """Execute a shell command inside a running pod and return the output."""
    from kubernetes.stream import stream
    v1 = client.CoreV1Api()
    resp = stream(
        v1.connect_get_namespaced_pod_exec,
        pod_name,
        namespace,
        command=["/bin/sh", "-c", command],
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
    )
    return resp.strip() if resp else "(no output)"


def list_namespaces():
    """List all namespaces in the cluster."""
    v1 = client.CoreV1Api()
    namespaces = v1.list_namespace()
    return [ns.metadata.name for ns in namespaces.items]


def get_node_status():
    """Get status of all nodes in the cluster."""
    v1 = client.CoreV1Api()
    nodes = v1.list_node()
    result = []
    for node in nodes.items:
        conditions = {c.type: c.status for c in node.status.conditions}
        result.append({
            "name": node.metadata.name,
            "ready": conditions.get("Ready", "Unknown"),
            "cpu": node.status.capacity.get("cpu"),
            "memory": node.status.capacity.get("memory"),
        })
    return result
