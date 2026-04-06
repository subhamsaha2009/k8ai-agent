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


def deploy_pod(name, image, namespace="default", env_vars=None,
               command=None, memory_limit=None, cpu_limit=None,
               memory_request=None, cpu_request=None):
    """Deploy a new pod to the cluster with optional resource limits and command."""
    v1 = client.CoreV1Api()

    env = []
    if env_vars:
        for k, v in env_vars.items():
            env.append(client.V1EnvVar(name=k, value=v))

    # Build resource requirements if any limits/requests provided
    resources = None
    limits = {}
    requests = {}
    if memory_limit:
        limits["memory"] = memory_limit
    if cpu_limit:
        limits["cpu"] = cpu_limit
    if memory_request:
        requests["memory"] = memory_request
    if cpu_request:
        requests["cpu"] = cpu_request
    if limits or requests:
        resources = client.V1ResourceRequirements(
            limits=limits if limits else None,
            requests=requests if requests else None,
        )

    # command can be a list ["sh","-c","..."] or a plain string (wrapped automatically)
    cmd = None
    if command:
        cmd = command if isinstance(command, list) else ["sh", "-c", command]

    pod_manifest = client.V1Pod(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        spec=client.V1PodSpec(
            containers=[
                client.V1Container(
                    name=name,
                    image=image,
                    env=env if env else None,
                    command=cmd,
                    resources=resources,
                )
            ],
            restart_policy="Never",
        ),
    )

    v1.create_namespaced_pod(namespace, pod_manifest)
    details = f"image='{image}'"
    if memory_limit:
        details += f", memory_limit={memory_limit}"
    if cpu_limit:
        details += f", cpu_limit={cpu_limit}"
    if cmd:
        details += f", command={cmd}"
    return f"Pod '{name}' deployed ({details}) in namespace '{namespace}'"


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


def get_pod_resource_usage(pod_name=None, namespace="default"):
    """Get CPU and memory usage for pods using the metrics-server API."""
    import subprocess
    import json as _json

    try:
        if pod_name:
            cmd = ["kubectl", "get", "--raw",
                   f"/apis/metrics.k8s.io/v1beta1/namespaces/{namespace}/pods/{pod_name}"]
        else:
            cmd = ["kubectl", "get", "--raw",
                   f"/apis/metrics.k8s.io/v1beta1/namespaces/{namespace}/pods"]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if result.returncode != 0:
            return {
                "error": "metrics-server not available",
                "detail": result.stderr.strip(),
                "fix": "Install metrics-server: kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"
            }

        data = _json.loads(result.stdout)
        pods = [data] if pod_name else data.get("items", [])

        output = []
        for pod in pods:
            containers = []
            for c in pod.get("containers", []):
                cpu_nano = c["usage"]["cpu"]
                mem_bytes = c["usage"]["memory"]

                # Convert nanocores to millicores
                if cpu_nano.endswith("n"):
                    cpu_m = round(int(cpu_nano[:-1]) / 1_000_000, 2)
                    cpu_display = f"{cpu_m}m"
                else:
                    cpu_display = cpu_nano

                # Convert Ki to Mi
                if mem_bytes.endswith("Ki"):
                    mem_mi = round(int(mem_bytes[:-2]) / 1024, 1)
                    mem_display = f"{mem_mi}Mi"
                else:
                    mem_display = mem_bytes

                containers.append({
                    "container": c["name"],
                    "cpu": cpu_display,
                    "memory": mem_display,
                })

            output.append({
                "pod": pod["metadata"]["name"],
                "namespace": pod["metadata"]["namespace"],
                "containers": containers,
                "timestamp": pod.get("timestamp", ""),
            })

        return output

    except FileNotFoundError:
        return {"error": "kubectl not found in PATH"}
    except Exception as e:
        return {"error": str(e)}


def get_pod_resource_limits(pod_name, namespace="default"):
    """Get the resource requests and limits configured for a pod (not live usage — what it's allowed to use)."""
    v1 = client.CoreV1Api()
    pod = v1.read_namespaced_pod(pod_name, namespace)

    result = []
    for c in pod.spec.containers:
        requests = {}
        limits = {}
        if c.resources:
            if c.resources.requests:
                requests = dict(c.resources.requests)
            if c.resources.limits:
                limits = dict(c.resources.limits)
        result.append({
            "container": c.name,
            "requests": requests if requests else "not set",
            "limits": limits if limits else "not set",
        })

    return {
        "pod": pod_name,
        "namespace": namespace,
        "resource_config": result,
        "note": "These are configured limits, not live usage. Use get_pod_resource_usage for live metrics."
    }


def check_metrics_server(namespace="default"):
    """Check if metrics-server is installed and working in the cluster."""
    import subprocess
    result = subprocess.run(
        ["kubectl", "get", "deployment", "metrics-server", "-n", "kube-system"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        # Also verify it's actually serving data
        test = subprocess.run(
            ["kubectl", "get", "--raw", f"/apis/metrics.k8s.io/v1beta1/namespaces/{namespace}/pods"],
            capture_output=True, text=True, timeout=10
        )
        if test.returncode == 0:
            return {"status": "ready", "message": "metrics-server is installed and serving data"}
        else:
            return {"status": "not_ready", "message": "metrics-server is installed but not yet serving data. Wait 1-2 minutes after install."}
    else:
        return {
            "status": "not_installed",
            "message": "metrics-server is not installed",
            "fix": "Run: kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"
        }


def get_kubelet_logs(node_name, lines=100):
    """Fetch kubelet logs from an AKS node by running a privileged debug pod.
    Automatically cleans up the debug pod after fetching logs."""
    import subprocess
    import time

    debug_pod = f"kubelet-debug-{node_name.split('-')[-1]}"

    # Pod spec: privileged, mounts host filesystem, runs on the target node
    overrides = (
        '{'
        '"spec":{'
        f'"nodeName":"{node_name}",'
        '"hostPID":true,'
        '"restartPolicy":"Never",'
        '"tolerations":[{"operator":"Exists"}],'
        '"containers":[{'
        f'"name":"{debug_pod}",'
        '"image":"mcr.microsoft.com/cbl-mariner/busybox:2.0",'
        '"securityContext":{"privileged":true},'
        '"command":["chroot","/host","journalctl","-u","kubelet",'
        f'"-n","{lines}","--no-pager"],'
        '"volumeMounts":[{"name":"host","mountPath":"/host"}]'
        '}],'
        '"volumes":[{"name":"host","hostPath":{"path":"/"}}]'
        '}}'
    )

    try:
        # Launch the debug pod
        create = subprocess.run(
            ["kubectl", "run", debug_pod,
             "--image=mcr.microsoft.com/cbl-mariner/busybox:2.0",
             "--restart=Never",
             f"--overrides={overrides}"],
            capture_output=True, text=True, timeout=30
        )
        if create.returncode != 0:
            return {"error": f"Failed to create debug pod: {create.stderr.strip()}"}

        # Wait for pod to complete (max 60s)
        for _ in range(20):
            time.sleep(3)
            status = subprocess.run(
                ["kubectl", "get", "pod", debug_pod,
                 "-o", "jsonpath={.status.phase}"],
                capture_output=True, text=True, timeout=10
            )
            phase = status.stdout.strip()
            if phase in ("Succeeded", "Failed"):
                break

        # Fetch logs
        logs = subprocess.run(
            ["kubectl", "logs", debug_pod],
            capture_output=True, text=True, timeout=30
        )

        return {
            "node": node_name,
            "lines_requested": lines,
            "logs": logs.stdout if logs.stdout else "(no logs retrieved)",
            "note": "These are kubelet system logs from the node."
        }

    except Exception as e:
        return {"error": str(e)}

    finally:
        # Always clean up the debug pod
        subprocess.run(
            ["kubectl", "delete", "pod", debug_pod, "--ignore-not-found"],
            capture_output=True, timeout=15
        )


def get_node_names():
    """Get list of all node names in the cluster. Use before get_kubelet_logs to find the node name."""
    v1 = client.CoreV1Api()
    nodes = v1.list_node()
    return [node.metadata.name for node in nodes.items]


def run_kubectl(command, namespace=None, output_format=None):
    """Execute any kubectl command and return the output.
    This is the generic kubectl executor — covers ALL kubectl operations."""
    import subprocess
    import shlex

    # Build the full command
    cmd = ["kubectl"] + shlex.split(command)

    # Add namespace if provided and not already in the command
    all_ns_values = {"-A", "--all-namespaces", "all", "*", "all-namespaces"}
    if namespace and namespace.strip().lower() in all_ns_values:
        if "-A" not in cmd and "--all-namespaces" not in cmd:
            cmd += ["-A"]
    elif namespace and "-n" not in command and "--namespace" not in command and "-A" not in command:
        cmd += ["-n", namespace]

    # Add output format if provided and not already in the command
    if output_format and "-o" not in command:
        cmd += ["-o", output_format]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip(), "command": " ".join(cmd)}
        return {"output": result.stdout.strip(), "command": " ".join(cmd)}
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out after 60 seconds", "command": " ".join(cmd)}
    except FileNotFoundError:
        return {"error": "kubectl not found in PATH"}
    except Exception as e:
        return {"error": str(e)}


def analyze_impact(command):
    """Analyze the impact of a destructive kubectl command before execution.
    Returns dependency info, risk level, and safer alternatives."""
    import subprocess
    import shlex

    parts = shlex.split(command)
    action = parts[0] if parts else ""
    analysis = {
        "command": f"kubectl {command}",
        "action": action,
        "what_this_does": "",
        "direct_impact": [],
        "dependent_resources": [],
        "risk_level": "UNKNOWN",
        "safer_alternatives": [],
    }

    # ── Identify resource type and name ──
    resource_type = parts[1] if len(parts) > 1 else ""
    resource_name = parts[2] if len(parts) > 2 else ""

    # Extract namespace from command
    ns = "default"
    for i, p in enumerate(parts):
        if p in ("-n", "--namespace") and i + 1 < len(parts):
            ns = parts[i + 1]

    # Check for --all flag
    has_all = "--all" in parts or "-A" in parts

    # ── Risk classification ──
    critical_actions = {"delete namespace", "drain", "delete node"}
    high_risk_indicators = ["--all", "-A", "delete deployment", "delete service",
                            "delete statefulset", "delete daemonset", "cordon"]
    medium_actions = ["delete pod", "scale", "rollout restart", "taint",
                      "label", "annotate", "patch", "apply", "create"]

    cmd_str = f"{action} {resource_type}"

    if cmd_str in critical_actions or (action == "delete" and has_all):
        analysis["risk_level"] = "CRITICAL"
    elif any(ind in f"{action} {resource_type} {' '.join(parts)}" for ind in high_risk_indicators):
        analysis["risk_level"] = "HIGH"
    elif any(cmd_str.startswith(m) for m in medium_actions):
        analysis["risk_level"] = "MEDIUM"
    else:
        analysis["risk_level"] = "LOW"

    # ── What this command does ──
    action_descriptions = {
        "delete": f"Permanently removes {resource_type} '{resource_name}' and all resources it manages",
        "drain": f"Evicts ALL pods from node '{resource_name}', marks it unschedulable",
        "cordon": f"Marks node '{resource_name}' as unschedulable — no new pods will be placed here",
        "uncordon": f"Marks node '{resource_name}' as schedulable again",
        "scale": f"Changes the number of replicas for {resource_type} '{resource_name}'",
        "rollout restart": f"Triggers a rolling restart of all pods in {resource_type} '{resource_name}'",
        "taint": f"Adds/removes a taint on node '{resource_name}' — may evict existing pods",
        "apply": f"Creates or updates resources from the provided configuration",
        "patch": f"Modifies specific fields of {resource_type} '{resource_name}'",
        "create": f"Creates a new {resource_type} resource",
        "replace": f"Replaces {resource_type} '{resource_name}' entirely — destructive if misconfigured",
    }
    analysis["what_this_does"] = action_descriptions.get(action, f"Executes '{action}' on {resource_type}")

    if has_all and action == "delete":
        analysis["what_this_does"] = f"Deletes ALL {resource_type} resources in namespace '{ns}'"
        analysis["risk_level"] = "CRITICAL"

    # ── Dependency check — query the cluster ──
    try:
        if action == "delete" and resource_type in ("deployment", "deployments", "deploy"):
            # Find pods managed by this deployment
            if resource_name and not has_all:
                result = subprocess.run(
                    ["kubectl", "get", "deployment", resource_name, "-n", ns, "-o",
                     "jsonpath={.spec.selector.matchLabels}"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout:
                    import json as _json
                    try:
                        labels = _json.loads(result.stdout.replace("'", '"'))
                        label_selector = ",".join(f"{k}={v}" for k, v in labels.items())
                    except Exception:
                        label_selector = f"app={resource_name}"
                else:
                    label_selector = f"app={resource_name}"

                # Count pods
                pods = subprocess.run(
                    ["kubectl", "get", "pods", "-l", label_selector, "-n", ns,
                     "-o", "jsonpath={.items[*].metadata.name}"],
                    capture_output=True, text=True, timeout=10
                )
                if pods.returncode == 0 and pods.stdout:
                    pod_names = pods.stdout.split()
                    analysis["direct_impact"].append(
                        f"{len(pod_names)} pod(s) will be terminated: {', '.join(pod_names[:5])}"
                        + (f" (+{len(pod_names)-5} more)" if len(pod_names) > 5 else "")
                    )

                # Check for services targeting these pods
                svcs = subprocess.run(
                    ["kubectl", "get", "services", "-n", ns, "-o", "json"],
                    capture_output=True, text=True, timeout=10
                )
                if svcs.returncode == 0:
                    import json as _json
                    svc_data = _json.loads(svcs.stdout)
                    for svc in svc_data.get("items", []):
                        svc_selector = svc.get("spec", {}).get("selector", {})
                        if any(svc_selector.get(k) == v for k, v in
                               (labels if 'labels' in dir() else {f"app": resource_name}).items()):
                            svc_name = svc["metadata"]["name"]
                            svc_type = svc["spec"].get("type", "ClusterIP")
                            analysis["dependent_resources"].append(
                                f"Service '{svc_name}' ({svc_type}) → will lose all backends"
                            )

                # Check for HPA
                hpa = subprocess.run(
                    ["kubectl", "get", "hpa", "-n", ns, "-o", "json"],
                    capture_output=True, text=True, timeout=10
                )
                if hpa.returncode == 0:
                    import json as _json
                    hpa_data = _json.loads(hpa.stdout)
                    for h in hpa_data.get("items", []):
                        target = h.get("spec", {}).get("scaleTargetRef", {})
                        if target.get("name") == resource_name:
                            analysis["dependent_resources"].append(
                                f"HPA '{h['metadata']['name']}' → will have no target"
                            )

                # Check for ingress
                ing = subprocess.run(
                    ["kubectl", "get", "ingress", "-n", ns, "-o", "json"],
                    capture_output=True, text=True, timeout=10
                )
                if ing.returncode == 0:
                    import json as _json
                    ing_data = _json.loads(ing.stdout)
                    for i in ing_data.get("items", []):
                        rules = i.get("spec", {}).get("rules", [])
                        for rule in rules:
                            for path in rule.get("http", {}).get("paths", []):
                                backend_svc = path.get("backend", {}).get("service", {}).get("name", "")
                                # Check if any affected service is referenced
                                for dep in analysis["dependent_resources"]:
                                    if backend_svc in dep:
                                        analysis["dependent_resources"].append(
                                            f"Ingress '{i['metadata']['name']}' → routes to affected service, will return 502"
                                        )

            analysis["safer_alternatives"] = [
                f"Scale to 0 first: kubectl scale deploy {resource_name} --replicas=0 -n {ns} (reversible)",
                f"Check what depends on it: kubectl get all -l app={resource_name} -n {ns}",
            ]

        elif action == "delete" and resource_type in ("service", "services", "svc"):
            if resource_name and not has_all:
                # Check for ingress using this service
                ing = subprocess.run(
                    ["kubectl", "get", "ingress", "-n", ns, "-o", "json"],
                    capture_output=True, text=True, timeout=10
                )
                if ing.returncode == 0:
                    import json as _json
                    ing_data = _json.loads(ing.stdout)
                    for i in ing_data.get("items", []):
                        rules = i.get("spec", {}).get("rules", [])
                        for rule in rules:
                            for path in rule.get("http", {}).get("paths", []):
                                backend_svc = path.get("backend", {}).get("service", {}).get("name", "")
                                if backend_svc == resource_name:
                                    analysis["dependent_resources"].append(
                                        f"Ingress '{i['metadata']['name']}' → route will break"
                                    )

                analysis["direct_impact"].append(
                    f"Service '{resource_name}' will be removed — external IP will be released"
                )
            analysis["safer_alternatives"] = [
                f"Check endpoints first: kubectl describe service {resource_name} -n {ns}",
            ]

        elif action == "delete" and resource_type in ("namespace", "namespaces", "ns"):
            analysis["what_this_does"] = f"Deletes namespace '{resource_name}' and EVERYTHING inside it"
            analysis["risk_level"] = "CRITICAL"

            # List everything in the namespace
            all_res = subprocess.run(
                ["kubectl", "get", "all", "-n", resource_name, "--no-headers"],
                capture_output=True, text=True, timeout=10
            )
            if all_res.returncode == 0 and all_res.stdout:
                lines = [l for l in all_res.stdout.strip().split("\n") if l.strip()]
                analysis["direct_impact"].append(f"{len(lines)} resource(s) will be permanently deleted")
                for line in lines[:10]:
                    analysis["direct_impact"].append(f"  • {line.split()[0]}")
                if len(lines) > 10:
                    analysis["direct_impact"].append(f"  ... and {len(lines)-10} more")

            analysis["safer_alternatives"] = [
                f"List everything first: kubectl get all -n {resource_name}",
                f"Delete resources individually instead of the entire namespace",
            ]

        elif action == "drain":
            # List pods on the node
            pods = subprocess.run(
                ["kubectl", "get", "pods", "--all-namespaces", "--field-selector",
                 f"spec.nodeName={resource_name}", "--no-headers"],
                capture_output=True, text=True, timeout=10
            )
            if pods.returncode == 0 and pods.stdout:
                lines = [l for l in pods.stdout.strip().split("\n") if l.strip()]
                analysis["direct_impact"].append(f"{len(lines)} pod(s) will be evicted from node")
                for line in lines[:8]:
                    parts_line = line.split()
                    analysis["direct_impact"].append(f"  • {parts_line[0]}/{parts_line[1]}")

            analysis["safer_alternatives"] = [
                f"Cordon first: kubectl cordon {resource_name} (stops new pods, keeps existing)",
                f"Check node status: kubectl describe node {resource_name}",
            ]

        elif action == "delete" and resource_type in ("pod", "pods", "po"):
            if resource_name and not has_all:
                # Check if pod is managed by a controller
                pod_info = subprocess.run(
                    ["kubectl", "get", "pod", resource_name, "-n", ns, "-o",
                     "jsonpath={.metadata.ownerReferences[0].kind}"],
                    capture_output=True, text=True, timeout=10
                )
                if pod_info.returncode == 0 and pod_info.stdout:
                    controller = pod_info.stdout.strip()
                    analysis["direct_impact"].append(
                        f"Pod is managed by {controller} — will be recreated automatically"
                    )
                    analysis["risk_level"] = "LOW"
                else:
                    analysis["direct_impact"].append(
                        "Pod is standalone (no controller) — will NOT be recreated"
                    )

            analysis["safer_alternatives"] = [
                f"Check pod status first: kubectl describe pod {resource_name} -n {ns}",
            ]

        elif action == "scale":
            # Find current replicas
            if resource_name:
                current = subprocess.run(
                    ["kubectl", "get", resource_type, resource_name, "-n", ns,
                     "-o", "jsonpath={.spec.replicas}"],
                    capture_output=True, text=True, timeout=10
                )
                if current.returncode == 0:
                    analysis["direct_impact"].append(
                        f"Current replicas: {current.stdout.strip()}"
                    )
                # Check for --replicas in command
                for i, p in enumerate(parts):
                    if p.startswith("--replicas="):
                        new_count = p.split("=")[1]
                        analysis["direct_impact"].append(f"Will scale to: {new_count} replicas")
                        if new_count == "0":
                            analysis["risk_level"] = "HIGH"
                            analysis["direct_impact"].append("⚠ Scaling to 0 — all pods will be terminated")

    except Exception:
        analysis["dependent_resources"].append("(could not query cluster for dependencies)")

    return analysis


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


# ══════════════════════════════════════════════════════════════════════════════
# AKS-specific operations (only available when cluster is AKS)
# ══════════════════════════════════════════════════════════════════════════════

def detect_aks_cluster():
    """Auto-detect if the current cluster is AKS.
    Returns {"is_aks": True, "resource_group": ..., "cluster_name": ...} or {"is_aks": False}."""
    import subprocess
    import json as _json

    # Step 1: Get current context name and detect AKS via API server URL
    # AKS API servers always have ".azmk8s.io" in the URL
    # Example: https://k8ai-clust-k8ai-rg-719f07-wbxlp0l5.hcp.eastus.azmk8s.io:443
    try:
        ctx = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True, text=True, timeout=10
        )
        context_name = ctx.stdout.strip() if ctx.returncode == 0 else ""

        server_check = subprocess.run(
            ["kubectl", "config", "view", "--minify", "-o",
             "jsonpath={.clusters[0].cluster.server}"],
            capture_output=True, text=True, timeout=10
        )
        if server_check.returncode != 0 or ".azmk8s.io" not in server_check.stdout:
            return {"is_aks": False, "reason": "Not an AKS cluster (API server is not .azmk8s.io)"}
    except Exception:
        return {"is_aks": False, "reason": "Could not check cluster type"}

    # Step 2: Use 'az aks show' with context name directly (faster than 'az aks list')
    # Context name in AKS is typically the cluster name
    try:
        # Try to find the cluster by querying az aks list with a JMESPath filter
        # Use shell=True because 'az' is a .cmd file on Windows
        result = subprocess.run(
            f'az aks list --query "[?name==\'{context_name}\'].{{name:name, resourceGroup:resourceGroup, location:location, kubernetesVersion:kubernetesVersion}}" -o json',
            capture_output=True, text=True, timeout=60, shell=True
        )
        if result.returncode == 0:
            clusters = _json.loads(result.stdout)
            if clusters:
                c = clusters[0]
                return {
                    "is_aks": True,
                    "cluster_name": c["name"],
                    "resource_group": c["resourceGroup"],
                    "location": c.get("location", ""),
                    "kubernetes_version": c.get("kubernetesVersion", ""),
                }

        # Fallback: list all clusters
        result = subprocess.run(
            'az aks list --query "[].{name:name, resourceGroup:resourceGroup, location:location, kubernetesVersion:kubernetesVersion}" -o json',
            capture_output=True, text=True, timeout=60, shell=True
        )
        if result.returncode != 0:
            # az CLI failed but nodes confirm AKS — return partial info
            return {
                "is_aks": True,
                "cluster_name": context_name,
                "resource_group": "(unknown — az CLI failed)",
                "location": "",
                "kubernetes_version": "",
                "note": "AKS detected via node naming but az CLI query failed. Run 'az login' if needed.",
            }

        clusters = _json.loads(result.stdout)
        if not clusters:
            return {
                "is_aks": True,
                "cluster_name": context_name,
                "resource_group": "(unknown — no clusters found in subscription)",
                "location": "",
                "kubernetes_version": "",
            }

        # Match by context name
        for cluster in clusters:
            if cluster.get("name", "") == context_name:
                return {
                    "is_aks": True,
                    "cluster_name": cluster["name"],
                    "resource_group": cluster["resourceGroup"],
                    "location": cluster.get("location", ""),
                    "kubernetes_version": cluster.get("kubernetesVersion", ""),
                }

        # No exact match — use first cluster
        c = clusters[0]
        return {
            "is_aks": True,
            "cluster_name": c["name"],
            "resource_group": c["resourceGroup"],
            "location": c.get("location", ""),
            "kubernetes_version": c.get("kubernetesVersion", ""),
            "note": f"Found {len(clusters)} AKS clusters, matched to '{c['name']}'",
        }

    except FileNotFoundError:
        return {"is_aks": True, "cluster_name": context_name,
                "resource_group": "(unknown — az CLI not installed)",
                "location": "", "kubernetes_version": ""}
    except subprocess.TimeoutExpired:
        return {"is_aks": True, "cluster_name": context_name,
                "resource_group": "(unknown — az CLI timed out)",
                "location": "", "kubernetes_version": "",
                "note": "AKS detected but az CLI was slow. Try running 'az aks list' manually."}
    except Exception as e:
        return {"is_aks": True, "cluster_name": context_name,
                "resource_group": "(unknown)", "location": "", "kubernetes_version": "",
                "note": str(e)}


# Known AKS doc pages for common topics — avoids relying on search API
AKS_DOC_REFERENCES = {
    "addons": "https://learn.microsoft.com/en-us/azure/aks/integrations",
    "add-ons": "https://learn.microsoft.com/en-us/azure/aks/integrations",
    "extensions": "https://learn.microsoft.com/en-us/azure/aks/integrations",
    "integrations": "https://learn.microsoft.com/en-us/azure/aks/integrations",
    "networking": "https://learn.microsoft.com/en-us/azure/aks/concepts-network",
    "monitoring": "https://learn.microsoft.com/en-us/azure/aks/monitor-aks",
    "scaling": "https://learn.microsoft.com/en-us/azure/aks/concepts-scale",
    "autoscaler": "https://learn.microsoft.com/en-us/azure/aks/cluster-autoscaler",
    "upgrade": "https://learn.microsoft.com/en-us/azure/aks/upgrade-cluster",
    "security": "https://learn.microsoft.com/en-us/azure/aks/concepts-security",
    "rbac": "https://learn.microsoft.com/en-us/azure/aks/manage-azure-rbac",
    "identity": "https://learn.microsoft.com/en-us/azure/aks/use-managed-identity",
    "ingress": "https://learn.microsoft.com/en-us/azure/aks/app-routing",
    "keda": "https://learn.microsoft.com/en-us/azure/aks/keda-about",
    "istio": "https://learn.microsoft.com/en-us/azure/aks/istio-about",
    "keyvault": "https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-driver",
    "gpu": "https://learn.microsoft.com/en-us/azure/aks/gpu-cluster",
    "virtual-node": "https://learn.microsoft.com/en-us/azure/aks/virtual-nodes",
    "policy": "https://learn.microsoft.com/en-us/azure/aks/use-azure-policy",
    "nodepool": "https://learn.microsoft.com/en-us/azure/aks/create-node-pools",
}


def search_azure_docs(query):
    """Search official Microsoft Learn documentation and return relevant content.
    Use this to look up Azure/AKS features, addons, extensions, best practices, or any Azure topic.
    For common topics (addons, extensions, networking, etc.), returns the exact official doc page.
    Returns search results with titles, URLs, and descriptions."""
    import urllib.request
    import urllib.parse
    import json as _json

    # Check if query matches a known doc page
    query_lower = query.lower()
    for keyword, doc_url in AKS_DOC_REFERENCES.items():
        if keyword in query_lower:
            # Directly fetch this known page instead of searching
            result = fetch_azure_doc(doc_url)
            return {
                "matched_topic": keyword,
                "source": doc_url,
                "content": result.get("content", result.get("error", "")),
            }

    try:
        encoded_query = urllib.parse.quote(query)
        url = (f"https://learn.microsoft.com/api/search?"
               f"search={encoded_query}&locale=en-us&$top=5"
               f"&$filter=category%20eq%20%27Documentation%27")
        req = urllib.request.Request(url, headers={"User-Agent": "k8ai-agent/1.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = _json.loads(resp.read())

        results = []
        for r in data.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", "")[:300],
            })
        return {"results": results, "query": query}

    except Exception as e:
        return {"error": str(e), "query": query}


def fetch_azure_doc(url):
    """Fetch the full content of a Microsoft Learn documentation page.
    Use this after search_azure_docs to get detailed information from a specific doc page.
    Also supports raw GitHub URLs for Microsoft docs."""
    import urllib.request
    import re

    try:
        # Convert learn.microsoft.com URL to raw GitHub URL for clean markdown
        if "learn.microsoft.com" in url:
            # Extract the path after /azure/ or /cli/
            match = re.search(r"learn\.microsoft\.com/en-us/(azure/aks/[^?#]+)", url)
            if match:
                doc_path = match.group(1)
                # Try raw GitHub for cleaner content
                raw_url = f"https://raw.githubusercontent.com/MicrosoftDocs/azure-aks-docs/main/articles/{doc_path.replace('azure/', '')}.md"
                req = urllib.request.Request(raw_url, headers={"User-Agent": "k8ai-agent/1.0"})
                try:
                    resp = urllib.request.urlopen(req, timeout=15)
                    content = resp.read().decode("utf-8", errors="replace")
                    # Trim to relevant content (skip frontmatter)
                    if "---" in content:
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            content = parts[2].strip()
                    # Strip reference links at the bottom (lines starting with [)
                    import re as _re
                    content = _re.sub(r'\n\[[\w-]+\]:.*', '', content)
                    content = content.strip()
                    # Limit to 8000 chars to include full addon + extension tables
                    if len(content) > 8000:
                        content = content[:8000] + "\n\n... (truncated — ask for a specific section if you need more)"
                    return {"content": content, "source": raw_url}
                except Exception:
                    pass  # Fall through to direct fetch

        # Direct fetch for any URL
        req = urllib.request.Request(url, headers={"User-Agent": "k8ai-agent/1.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        content = resp.read().decode("utf-8", errors="replace")

        # Basic HTML to text (strip tags)
        import re as _re
        content = _re.sub(r"<script[^>]*>.*?</script>", "", content, flags=_re.DOTALL)
        content = _re.sub(r"<style[^>]*>.*?</style>", "", content, flags=_re.DOTALL)
        content = _re.sub(r"<[^>]+>", " ", content)
        content = _re.sub(r"\s+", " ", content).strip()

        if len(content) > 8000:
            content = content[:8000] + "\n\n... (truncated)"
        return {"content": content, "source": url}

    except Exception as e:
        return {"error": str(e), "url": url}


def get_az_aks_help(subcommand=""):
    """Get the official help text for any az aks command to find correct syntax and flags.
    Examples: get_az_aks_help("update"), get_az_aks_help("nodepool update"), get_az_aks_help("nodepool scale")"""
    import subprocess

    cmd = f"az aks {subcommand} --help" if subcommand else "az aks --help"
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, shell=True
        )
        output = result.stdout.strip()
        # Trim to keep it concise — focus on arguments and examples
        if len(output) > 3000:
            output = output[:3000] + "\n... (truncated)"
        return {"help": output, "command": cmd}
    except Exception as e:
        return {"error": str(e)}


def run_az_aks(command, resource_group=None, cluster_name=None):
    """Execute any 'az aks' command. Only works on AKS clusters.
    resource_group and cluster_name are auto-injected if not in the command."""
    import subprocess
    import shlex

    # Build the full command
    parts = shlex.split(command)
    cmd = ["az", "aks"] + parts

    # Commands that operate on ALL clusters — do NOT inject --name or --resource-group
    cmd_str = command.lower()
    no_inject_commands = {"list", "get-versions"}
    first_arg = parts[0].lower() if parts else ""
    skip_inject = first_arg in no_inject_commands

    if not skip_inject:
        # Auto-inject --resource-group and cluster name if not already in command
        if resource_group and "--resource-group" not in cmd_str and "-g" not in cmd_str:
            cmd += ["--resource-group", resource_group]

        # For nodepool commands: --cluster-name is required (separate from --name which is the pool name)
        # For non-nodepool commands: --name is the cluster name
        if cluster_name:
            if "nodepool" in cmd_str:
                if "--cluster-name" not in cmd_str:
                    cmd += ["--cluster-name", cluster_name]
            else:
                if "--name" not in cmd_str and "-n" not in cmd_str:
                    cmd += ["--name", cluster_name]

    try:
        # Use shell=True on Windows because 'az' is a .cmd file
        cmd_str = " ".join(cmd)
        result = subprocess.run(
            cmd_str,
            capture_output=True,
            text=True,
            timeout=300,  # AKS operations can take several minutes
            shell=True,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip(), "command": cmd_str}

        # Try to parse JSON output
        output = result.stdout.strip()
        try:
            import json as _json
            return {"output": _json.loads(output), "command": cmd_str}
        except Exception:
            return {"output": output, "command": cmd_str}

    except subprocess.TimeoutExpired:
        return {"error": "Command timed out (AKS operations can take several minutes)", "command": cmd_str}
    except FileNotFoundError:
        return {"error": "az CLI not found in PATH. Install: https://aka.ms/installazurecli"}
    except Exception as e:
        return {"error": str(e)}


def analyze_aks_impact(command, resource_group=None, cluster_name=None):
    """Analyze the impact of a destructive az aks command before execution."""
    import subprocess
    import shlex

    parts = shlex.split(command)
    # Identify the sub-command (e.g., "update", "nodepool scale", "stop")
    sub_cmd = parts[0] if parts else ""
    if sub_cmd == "nodepool" and len(parts) > 1:
        sub_cmd = f"nodepool {parts[1]}"

    analysis = {
        "command": f"az aks {command}",
        "action": sub_cmd,
        "what_this_does": "",
        "direct_impact": [],
        "dependent_resources": [],
        "risk_level": "MEDIUM",
        "safer_alternatives": [],
    }

    cluster_display = cluster_name or "(current cluster)"

    # ── What this command does ──
    descriptions = {
        "stop": f"Stops AKS cluster '{cluster_display}' completely — all workloads will be down",
        "delete": f"PERMANENTLY deletes AKS cluster '{cluster_display}' and ALL its resources",
        "upgrade": f"Upgrades Kubernetes version on cluster '{cluster_display}' — causes rolling restart of all nodes",
        "update": f"Updates configuration of cluster '{cluster_display}'",
        "nodepool add": f"Adds a new node pool to cluster '{cluster_display}'",
        "nodepool delete": "Removes a node pool — all pods on those nodes will be evicted",
        "nodepool scale": "Changes the number of nodes in a node pool",
        "nodepool update": "Updates node pool configuration",
        "nodepool upgrade": "Upgrades the Kubernetes version on a specific node pool",
        "enable-addons": f"Enables addon(s) on cluster '{cluster_display}'",
        "disable-addons": f"Disables addon(s) on cluster '{cluster_display}'",
        "start": f"Starts a stopped AKS cluster '{cluster_display}'",
    }
    analysis["what_this_does"] = descriptions.get(sub_cmd, f"Executes '{sub_cmd}' on AKS cluster")

    # ── Risk classification ──
    if sub_cmd == "delete":
        analysis["risk_level"] = "CRITICAL"
        analysis["direct_impact"] = [
            "Cluster and ALL node pools will be permanently deleted",
            "ALL deployments, services, pods, volumes will be destroyed",
            "External IPs and DNS entries will be released",
            "This action CANNOT be undone",
        ]
        analysis["safer_alternatives"] = [
            f"Stop instead: az aks stop (preserves cluster, stops billing for compute)",
            f"Check what's running first: kubectl get all -A",
        ]

    elif sub_cmd == "stop":
        analysis["risk_level"] = "HIGH"
        try:
            pods = subprocess.run(
                ["kubectl", "get", "pods", "-A", "--no-headers"],
                capture_output=True, text=True, timeout=10
            )
            if pods.returncode == 0 and pods.stdout:
                lines = [l for l in pods.stdout.strip().split("\n") if l.strip()]
                analysis["direct_impact"].append(f"{len(lines)} pod(s) across all namespaces will be stopped")
            svcs = subprocess.run(
                ["kubectl", "get", "svc", "-A", "--field-selector", "spec.type=LoadBalancer", "--no-headers"],
                capture_output=True, text=True, timeout=10
            )
            if svcs.returncode == 0 and svcs.stdout:
                svc_lines = [l for l in svcs.stdout.strip().split("\n") if l.strip()]
                analysis["direct_impact"].append(f"{len(svc_lines)} LoadBalancer service(s) will become unreachable")
        except Exception:
            pass
        analysis["direct_impact"].append("Cluster will be completely offline until started again")
        analysis["safer_alternatives"] = [
            "Scale node pools to minimum instead if you want to reduce cost but keep cluster running",
        ]

    elif sub_cmd == "upgrade":
        analysis["risk_level"] = "HIGH"
        analysis["direct_impact"] = [
            "All nodes will be drained and recreated with new K8s version",
            "Rolling upgrade — workloads will be rescheduled",
            "May take 15-30+ minutes depending on cluster size",
        ]
        try:
            # Check available upgrades
            if resource_group and cluster_name:
                upgrades = subprocess.run(
                    f"az aks get-upgrades --resource-group {resource_group} --name {cluster_name} -o json",
                    capture_output=True, text=True, timeout=30, shell=True
                )
                if upgrades.returncode == 0:
                    import json as _json
                    data = _json.loads(upgrades.stdout)
                    current = data.get("controlPlaneProfile", {}).get("kubernetesVersion", "")
                    available = data.get("controlPlaneProfile", {}).get("upgrades", [])
                    if current:
                        analysis["direct_impact"].append(f"Current version: {current}")
                    if available:
                        versions = [u.get("kubernetesVersion", "") for u in available if not u.get("isPreview")]
                        analysis["direct_impact"].append(f"Available upgrades: {', '.join(versions)}")
        except Exception:
            pass
        analysis["safer_alternatives"] = [
            f"Check available versions first: az aks get-upgrades -g {resource_group} -n {cluster_name}",
            "Upgrade a single node pool first to test: az aks nodepool upgrade",
        ]

    elif sub_cmd == "nodepool delete":
        analysis["risk_level"] = "HIGH"
        # Find which nodepool
        nodepool_name = None
        for i, p in enumerate(parts):
            if p in ("--name", "-n") and i + 1 < len(parts):
                nodepool_name = parts[i + 1]
        if nodepool_name:
            analysis["direct_impact"].append(f"Node pool '{nodepool_name}' will be removed")
            try:
                pods = subprocess.run(
                    ["kubectl", "get", "pods", "-A", "--field-selector",
                     f"spec.nodeName=aks-{nodepool_name}", "--no-headers"],
                    capture_output=True, text=True, timeout=10
                )
                if pods.returncode == 0 and pods.stdout:
                    lines = [l for l in pods.stdout.strip().split("\n") if l.strip()]
                    analysis["direct_impact"].append(f"Pods on this pool's nodes will be evicted")
            except Exception:
                pass
        analysis["direct_impact"].append("Nodes in this pool will be permanently removed")
        analysis["safer_alternatives"] = [
            "Scale to 0 first to test: az aks nodepool scale --node-count 0",
            f"Check pool details: az aks nodepool show --name {nodepool_name or '<pool>'}",
        ]

    elif sub_cmd == "nodepool scale":
        analysis["risk_level"] = "MEDIUM"
        # Check if scaling down
        for i, p in enumerate(parts):
            if p == "--node-count" and i + 1 < len(parts):
                new_count = parts[i + 1]
                analysis["direct_impact"].append(f"Node pool will be scaled to {new_count} node(s)")
                if new_count == "0":
                    analysis["risk_level"] = "HIGH"
                    analysis["direct_impact"].append("⚠ Scaling to 0 — all pods on this pool will be evicted")

    elif sub_cmd == "disable-addons":
        analysis["risk_level"] = "MEDIUM"
        for i, p in enumerate(parts):
            if p in ("--addons", "-a") and i + 1 < len(parts):
                addons = parts[i + 1]
                analysis["direct_impact"].append(f"Addon(s) to disable: {addons}")
                analysis["direct_impact"].append("Addon pods will be removed from the cluster")

    elif sub_cmd == "enable-addons":
        analysis["risk_level"] = "LOW"
        for i, p in enumerate(parts):
            if p in ("--addons", "-a") and i + 1 < len(parts):
                addons = parts[i + 1]
                analysis["direct_impact"].append(f"Addon(s) to enable: {addons}")
        analysis["direct_impact"].append("New addon pods will be deployed to the cluster")

    elif sub_cmd == "update":
        analysis["risk_level"] = "MEDIUM"
        cmd_flags = " ".join(parts)

        # Parse specific update flags and explain what they do
        update_details = {
            "--enable-cluster-autoscaler": "ENABLE cluster autoscaler — node count will change automatically based on workload demand",
            "--disable-cluster-autoscaler": "DISABLE cluster autoscaler — node count will be fixed, no automatic scaling",
            "--enable-aad": "Enable Azure Active Directory integration for RBAC",
            "--enable-defender": "Enable Microsoft Defender for Containers (security scanning)",
            "--disable-defender": "Disable Microsoft Defender for Containers",
            "--enable-azure-rbac": "Enable Azure RBAC for Kubernetes authorization",
            "--disable-azure-rbac": "Disable Azure RBAC for Kubernetes authorization",
            "--enable-oidc-issuer": "Enable OIDC issuer for workload identity",
            "--enable-workload-identity": "Enable workload identity (pod-level Azure access)",
            "--api-server-authorized-ip-ranges": "Restrict API server access to specific IP ranges",
            "--load-balancer-sku": "Change load balancer SKU",
            "--network-policy": "Change network policy engine",
        }

        found_flags = []
        for i, p in enumerate(parts):
            if p in update_details:
                found_flags.append(update_details[p])
            if p == "--min-count" and i + 1 < len(parts):
                found_flags.append(f"Autoscaler minimum nodes: {parts[i+1]}")
            if p == "--max-count" and i + 1 < len(parts):
                found_flags.append(f"Autoscaler maximum nodes: {parts[i+1]}")
            if p == "--auto-upgrade-channel" and i + 1 < len(parts):
                found_flags.append(f"Set auto-upgrade channel to '{parts[i+1]}'")
            if p == "--node-os-upgrade-channel" and i + 1 < len(parts):
                found_flags.append(f"Set node OS upgrade channel to '{parts[i+1]}'")
            if p == "--api-server-authorized-ip-ranges" and i + 1 < len(parts):
                found_flags.append(f"API server access restricted to: {parts[i+1]}")

        if found_flags:
            for detail in found_flags:
                analysis["direct_impact"].append(detail)
        else:
            analysis["direct_impact"].append(f"Cluster configuration will be updated with: {cmd_flags}")

        # Query current state for comparison
        try:
            if resource_group and cluster_name:
                current = subprocess.run(
                    f"az aks show -g {resource_group} -n {cluster_name} --query \"{{autoscaler:agentPoolProfiles[0].enableAutoScaling, minCount:agentPoolProfiles[0].minCount, maxCount:agentPoolProfiles[0].maxCount, nodeCount:agentPoolProfiles[0].count, vmSize:agentPoolProfiles[0].vmSize}}\" -o json",
                    capture_output=True, text=True, timeout=30, shell=True
                )
                if current.returncode == 0:
                    import json as _json
                    info = _json.loads(current.stdout)
                    state = (f"Current state: {info.get('nodeCount')} node(s), "
                             f"VM size: {info.get('vmSize')}, "
                             f"autoscaler: {'ON' if info.get('autoscaler') else 'OFF'}")
                    if info.get('autoscaler'):
                        state += f" (min={info.get('minCount')}, max={info.get('maxCount')})"
                    analysis["direct_impact"].insert(0, state)
        except Exception:
            pass

        # Risk escalation for dangerous flags
        if "--disable-cluster-autoscaler" in cmd_flags:
            analysis["risk_level"] = "HIGH"
            analysis["safer_alternatives"].append(
                "Consider adjusting min/max instead: az aks update --update-cluster-autoscaler --min-count 1 --max-count 3")
        if "--api-server-authorized-ip-ranges" in cmd_flags:
            analysis["risk_level"] = "HIGH"
            analysis["safer_alternatives"].append(
                "Wrong IP range can lock you out of the cluster — verify your IP first")

        analysis["safer_alternatives"].append(
            f"Check current config: az aks show -g {resource_group} -n {cluster_name}")

    return analysis


# ═══════════════════════════════════════════════════════════════════════════
#  LOCAL DOCS + KNOWLEDGE BASE SEARCH
# ═══════════════════════════════════════════════════════════════════════════

def search_local_docs(query):
    """Search Azure and Kubernetes documentation.
    Cascade: local (RAG + keyword) → online (Microsoft Learn) → no results.
    The agent only needs to call this one tool — the cascade is automatic."""
    try:
        from k8ai.kb import hybrid_search, is_docs_synced, has_embeddings
        from k8ai.embeddings import is_embedding_available, get_embedding

        # ── Step 1: Local search (RAG + keyword) ──
        if is_docs_synced():
            query_vector = None
            if is_embedding_available() and has_embeddings():
                query_vector = get_embedding(query)

            results = hybrid_search(query, query_vector=query_vector, category="docs", limit=5)

            if results:
                search_mode = "hybrid (keyword + RAG)" if query_vector else "keyword"
                return {"results": results, "query": query, "source": "local", "search_mode": search_mode}

        # ── Step 2: Online fallback (Microsoft Learn) ──
        online = search_azure_docs(query)
        if online and online.get("results"):
            online["source"] = "online_fallback"
            online["note"] = "No local results found. These results are from online Microsoft Learn. Run 'k8ai docs sync' to update local docs."
            return online
        if online and online.get("content"):
            online["source"] = "online_fallback"
            online["note"] = "No local results found. This content is from online Microsoft Learn. Run 'k8ai docs sync' to update local docs."
            return online

        # ── Step 3: Nothing found anywhere ──
        return {
            "query": query,
            "source": "none",
            "message": "No results found in local docs or online. Try a different search term, or check learn.microsoft.com directly.",
        }
    except Exception as e:
        # Last resort — try online on any error
        try:
            online = search_azure_docs(query)
            online["source"] = "online_fallback"
            online["note"] = "Local search failed. Showing online results instead."
            return online
        except Exception:
            return {"error": str(e), "query": query}


def search_knowledge_base(query):
    """Search your team's knowledge base — past incidents, runbooks, and team rules.
    Use this when an issue looks like something that may have happened before,
    or when the user asks about team processes and conventions."""
    try:
        from k8ai.kb import search_knowledge_base as _search_kb, is_azure_search_configured, search_azure

        results = _search_kb(query, limit=5)

        # Also check Azure AI Search if configured
        if is_azure_search_configured():
            azure_results = search_azure(query, limit=3)
            results.extend(azure_results)

        if not results:
            return {"message": "No matching incidents or runbooks found.", "query": query}
        return {"results": results, "query": query}
    except Exception as e:
        return {"error": str(e), "query": query}


def add_to_knowledge_base(title, description, resolution="", tags="", category="incident"):
    """Save a resolved incident, runbook, or team rule to the knowledge base.
    category: 'incident' for past issues, 'runbook' for team processes."""
    try:
        from k8ai.kb import add_incident, add_runbook

        if category == "runbook":
            add_runbook(title=title, content=f"{description}\n\n{resolution}".strip(), tags=tags)
        else:
            add_incident(title=title, description=description, resolution=resolution, tags=tags)

        return {"status": "saved", "title": title, "category": category}
    except Exception as e:
        return {"error": str(e)}
