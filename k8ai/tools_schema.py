TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_pods",
            "description": "List all pods in a namespace with their current status, container states, restart counts, and failure reasons. Use this first to get an overview of the cluster health.",
            "parameters": {
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace. Defaults to 'default'.",
                        "default": "default"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "describe_pod",
            "description": "Get detailed information and events for a specific pod. Reveals errors like ImagePullBackOff, OOMKilled, CrashLoopBackOff, scheduling failures. Always use this when a pod is not Running.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Name of the pod to describe."
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace. Defaults to 'default'.",
                        "default": "default"
                    }
                },
                "required": ["pod_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pod_logs",
            "description": "Fetch logs from a pod to diagnose application-level errors. Use 'previous=true' to get logs from the last crashed container.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Name of the pod."
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace. Defaults to 'default'.",
                        "default": "default"
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Number of log lines to fetch. Defaults to 100.",
                        "default": 100
                    },
                    "previous": {
                        "type": "boolean",
                        "description": "If true, get logs from the previously terminated container. Useful for CrashLoopBackOff.",
                        "default": False
                    }
                },
                "required": ["pod_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_pod",
            "description": "Deploy a new pod to the cluster with optional resource limits and a startup command. Use memory_limit to trigger OOMKill scenarios. Use command to run a specific process inside the container. ALWAYS ask user for permission before calling this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the new pod."
                    },
                    "image": {
                        "type": "string",
                        "description": "Container image to use (e.g. 'nginx:latest', 'busybox', 'python:3')."
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace. Defaults to 'default'.",
                        "default": "default"
                    },
                    "env_vars": {
                        "type": "object",
                        "description": "Optional environment variables as key-value pairs.",
                        "additionalProperties": {"type": "string"}
                    },
                    "command": {
                        "type": "string",
                        "description": "Shell command to run inside the container. Example: 'python3 -c \"x=[];\\nwhile True: x.append(\\\" \\\"*10**6)\"' to eat memory."
                    },
                    "memory_limit": {
                        "type": "string",
                        "description": "Maximum memory the container can use. Example: '10Mi', '50Mi', '256Mi'. Setting a low value like '10Mi' with a memory-hungry command will trigger OOMKill."
                    },
                    "cpu_limit": {
                        "type": "string",
                        "description": "CPU limit. Example: '100m' (100 millicores), '0.5'."
                    },
                    "memory_request": {
                        "type": "string",
                        "description": "Memory requested at scheduling time. Example: '10Mi'."
                    },
                    "cpu_request": {
                        "type": "string",
                        "description": "CPU requested at scheduling time. Example: '100m'."
                    }
                },
                "required": ["name", "image"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_pod",
            "description": "Delete a pod from the cluster. Used to force restart a failing pod. ALWAYS ask user for permission before calling this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Name of the pod to delete."
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace. Defaults to 'default'.",
                        "default": "default"
                    }
                },
                "required": ["pod_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_configmap",
            "description": "Create a ConfigMap with custom HTML content. Use this before deploy_web_pod when the user wants custom web page content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name for the ConfigMap."},
                    "html_content": {"type": "string", "description": "Full HTML content to serve as index.html."},
                    "namespace": {"type": "string", "default": "default"}
                },
                "required": ["name", "html_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_configmap",
            "description": "Update an existing ConfigMap with new HTML content to change what the web pod serves. REQUIRES user permission.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the ConfigMap to update."},
                    "html_content": {"type": "string", "description": "New HTML content for index.html."},
                    "namespace": {"type": "string", "default": "default"}
                },
                "required": ["name", "html_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_web_pod",
            "description": "Deploy an nginx web pod, optionally mounting a ConfigMap as the HTML content. Always follow with create_service to expose it. REQUIRES user permission.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name for the pod."},
                    "namespace": {"type": "string", "default": "default"},
                    "configmap_name": {"type": "string", "description": "Name of ConfigMap to mount as web content. Omit for default nginx page."},
                    "image": {"type": "string", "default": "nginx:latest"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_service",
            "description": "Expose a pod via a Kubernetes Service. Use service_type='LoadBalancer' to get a public IP for browser access. REQUIRES user permission.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name for the Service."},
                    "pod_name": {"type": "string", "description": "Name of the pod to expose (must match pod's app label)."},
                    "port": {"type": "integer", "default": 80},
                    "namespace": {"type": "string", "default": "default"},
                    "service_type": {"type": "string", "enum": ["LoadBalancer", "NodePort", "ClusterIP"], "default": "LoadBalancer"}
                },
                "required": ["name", "pod_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_service",
            "description": "Get service details including the external public IP and URL. Use after create_service to check if LoadBalancer IP has been assigned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the service."},
                    "namespace": {"type": "string", "default": "default"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_service",
            "description": "Delete a Kubernetes Service. REQUIRES user permission.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "namespace": {"type": "string", "default": "default"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "exec_in_pod",
            "description": "Run a shell command inside a running pod and return output. Use to inspect files, check processes, or verify content inside a pod.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod_name": {"type": "string"},
                    "command": {"type": "string", "description": "Shell command to run, e.g. 'ls /usr/share/nginx/html'"},
                    "namespace": {"type": "string", "default": "default"}
                },
                "required": ["pod_name", "command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_namespaces",
            "description": "List all namespaces in the cluster.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_node_status",
            "description": "Get the status, CPU, and memory of all nodes in the cluster.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pod_resource_usage",
            "description": "Get LIVE CPU and memory usage for pods using metrics-server. Use this when user asks about resource utilization, CPU usage, memory consumption, or performance of pods. If no pod_name given, returns usage for all pods in the namespace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Name of a specific pod. Omit to get usage for all pods."
                    },
                    "namespace": {
                        "type": "string",
                        "default": "default"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pod_resource_limits",
            "description": "Get the CPU and memory requests/limits configured for a pod. Shows what the pod is ALLOWED to use (not live usage). Use this to check if a pod is over/under provisioned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Name of the pod."
                    },
                    "namespace": {
                        "type": "string",
                        "default": "default"
                    }
                },
                "required": ["pod_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_node_names",
            "description": "Get all node names in the cluster. Always call this first before get_kubelet_logs to find the correct node name.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_kubelet_logs",
            "description": "Fetch kubelet system logs from an AKS node. Use when user asks about node-level issues, kubelet errors, pod scheduling failures, or OOMKill events at the node level. Automatically creates and cleans up a debug pod.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_name": {
                        "type": "string",
                        "description": "Full name of the node (e.g. aks-nodepool1-12345678-vmss000000). Use get_node_names first to find it."
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Number of log lines to fetch. Defaults to 100.",
                        "default": 100
                    }
                },
                "required": ["node_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_kubectl",
            "description": "Execute any kubectl command. Use this for ALL kubernetes operations that don't have a specific tool (e.g. get deployments, scale, rollout, apply, get ingress, get events, etc.). For common operations like list_pods, describe_pod, deploy_pod etc., prefer the specific tools. Use this for everything else kubectl can do.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The kubectl command WITHOUT the 'kubectl' prefix. Examples: 'get deployments', 'scale deploy nginx --replicas=3', 'get events --sort-by=.lastTimestamp', 'rollout restart deploy nginx', 'get ingress', 'top pods', 'get pvc', 'get configmaps', 'apply -f manifest.yaml', 'get all'"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace. Added as -n flag if not already in the command."
                    },
                    "output_format": {
                        "type": "string",
                        "description": "Output format (json, yaml, wide, name). Added as -o flag if not already in the command."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_metrics_server",
            "description": "Check if metrics-server is installed and working. Always call this first if get_pod_resource_usage returns an error about metrics-server not available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "default": "default"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_az_aks_help",
            "description": "Get the official help text for any az aks command. ALWAYS call this BEFORE run_az_aks when you are unsure about the correct flags or syntax. This shows all available arguments, required parameters, and examples. Examples: 'update', 'nodepool update', 'nodepool scale', 'enable-addons'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subcommand": {
                        "type": "string",
                        "description": "The az aks subcommand to get help for. Examples: 'update', 'nodepool update', 'nodepool scale', 'nodepool add', 'enable-addons', 'upgrade'. Leave empty for top-level az aks help."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_az_aks",
            "description": "Execute any 'az aks' command for AKS cluster management. ONLY available on AKS clusters. IMPORTANT: If you are unsure about the correct flags or syntax, call get_az_aks_help FIRST to check the official documentation. The resource group and cluster name are auto-injected — you don't need to provide them unless overriding.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The az aks sub-command WITHOUT 'az aks' prefix. Examples: 'show', 'get-upgrades', 'upgrade --kubernetes-version 1.29.0', 'stop', 'start', 'nodepool list', 'nodepool add --name gpu --node-count 1 --node-vm-size Standard_NC6', 'nodepool scale --name nodepool1 --node-count 5', 'nodepool delete --name oldpool', 'enable-addons --addons monitoring', 'disable-addons --addons monitoring', 'update --enable-cluster-autoscaler --min-count 1 --max-count 5'"
                    },
                    "resource_group": {
                        "type": "string",
                        "description": "Azure resource group. Auto-detected if not provided."
                    },
                    "cluster_name": {
                        "type": "string",
                        "description": "AKS cluster name. Auto-detected if not provided."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "debug_pod",
            "description": "Attach an ephemeral debug container to a running pod for network diagnostics. Uses nicolaka/netshoot image which includes dig, nslookup, curl, wget, tcpdump, ping, traceroute, iptables, ss, ip, netstat, and more. This creates an ephemeral container — REQUIRES user permission. For tcpdump, always use '-c N' to limit packet count.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Name of the pod to debug."
                    },
                    "command": {
                        "type": "string",
                        "description": "Diagnostic command to run. Examples: 'dig kubernetes.default', 'curl -v http://my-service:8080', 'tcpdump -i eth0 -c 20 -nn', 'ss -tlnp', 'nslookup my-service.default.svc.cluster.local', 'ping -c 3 10.0.0.1', 'traceroute my-service'"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace. Defaults to 'default'.",
                        "default": "default"
                    },
                    "container": {
                        "type": "string",
                        "description": "Target container name for multi-container pods. Shares the container's process namespace. Omit for single-container pods."
                    },
                    "image": {
                        "type": "string",
                        "description": "Debug container image. Defaults to nicolaka/netshoot.",
                        "default": "nicolaka/netshoot"
                    }
                },
                "required": ["pod_name", "command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "debug_node",
            "description": "Create a privileged debug pod on a specific node for host-level diagnostics. Provides access to dmesg, iptables, df, /proc/meminfo, ps, and more. Commands automatically run in the host context via chroot. Use get_node_names first to find the node name. REQUIRES user permission — creates a privileged pod.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_name": {
                        "type": "string",
                        "description": "Full name of the node. Use get_node_names() first."
                    },
                    "command": {
                        "type": "string",
                        "description": "Host-level command to run. Examples: 'dmesg | tail -50', 'df -h', 'cat /proc/meminfo', 'ps aux | head -20', 'iptables -L -n', 'cat /etc/resolv.conf', 'ss -tlnp', 'journalctl -u containerd -n 50 --no-pager'"
                    },
                    "image": {
                        "type": "string",
                        "description": "Debug image. Defaults to busybox.",
                        "default": "busybox"
                    }
                },
                "required": ["node_name", "command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_az",
            "description": "Execute any 'az' command for Azure resource inspection and management. Use for NSGs, disks, identities, ACR, Key Vault, Monitor, etc. Safe commands (show, list, get) run immediately. Destructive commands return impact analysis first. ONLY available on AKS clusters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The az sub-command WITHOUT 'az' prefix. Examples: 'network nsg list --resource-group myRG', 'disk list --resource-group myRG', 'identity list', 'acr list', 'keyvault list', 'monitor metrics list --resource myVM --resource-type Microsoft.Compute/virtualMachines --metric Percentage_CPU'"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_local_docs",
            "description": "Search Azure AKS and Kubernetes documentation. Searches local docs first (fast, offline, RAG-powered), then automatically falls back to online Microsoft Learn if no local results found. This is the ONLY doc search tool you need — it handles the full cascade internally.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query. Examples: 'AKS addons', 'pod disruption budget', 'istio mTLS setup', 'horizontal pod autoscaler'"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search your team's internal knowledge base — past incidents, runbooks, postmortems, and team rules. Use this when an issue looks recurring ('has this happened before?'), when the user asks about team processes, or after diagnosing a problem to check for past resolutions. Also checks Azure AI Search if configured.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query. Examples: 'payment-service OOMKilled', 'certificate rotation process', 'scaling rules', 'deployment best practices'"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_knowledge_base",
            "description": "Save a resolved incident, team rule, or runbook to the knowledge base for future reference. Use this after fixing an issue (ask the user first), or when the user explicitly asks to remember something. This data is searchable in future conversations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short title. Example: 'payment-service OOMKilled — April 2026'"
                    },
                    "description": {
                        "type": "string",
                        "description": "What happened or what the rule is. Example: 'Pod crashed due to memory leak in connection pool v2.3.1'"
                    },
                    "resolution": {
                        "type": "string",
                        "description": "How it was fixed. Example: 'Upgraded to v2.3.2, set memory limit to 512Mi'"
                    },
                    "tags": {
                        "type": "string",
                        "description": "Space-separated tags for easier search. Example: 'oomkill payment-service memory'"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["incident", "runbook"],
                        "description": "Type of entry. 'incident' for past issues, 'runbook' for team rules and processes.",
                        "default": "incident"
                    }
                },
                "required": ["title", "description"]
            }
        }
    }
]
