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
            "description": "Deploy a new pod to the cluster. ALWAYS ask user for permission before calling this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the new pod."
                    },
                    "image": {
                        "type": "string",
                        "description": "Container image to use (e.g. 'nginx:latest')."
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
    }
]
