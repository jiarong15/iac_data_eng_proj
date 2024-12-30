import pulumi
import pulumi_kubernetes as k8s

class TraefikRoute(pulumi.ComponentResource):
    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        super().__init__("pkg:index:TraefikRoute", name, None, opts)

        # Unpack arguments
        namespace = args.get("namespace")
        prefix = args.get("prefix")
        service = args.get("service")

        # Create the trailing slash middleware
        trailing_slash_middleware = k8s.apiextensions.CustomResource(
            f"{name}-trailing-slash",
            api_version="traefik.containo.us/v1alpha1",
            kind="Middleware",
            metadata={"namespace": namespace},
            spec={
                "redirectRegex": {
                    "regex": f"^.*\\{prefix}$",
                    "replacement": f"{prefix}/",
                    "permanent": False,
                },
            },
            opts=pulumi.ResourceOptions(provider=opts.provider if opts else None)
        )

        # Create the strip prefix middleware
        strip_prefix_middleware = k8s.apiextensions.CustomResource(
            f"{name}-strip-prefix",
            api_version="traefik.containo.us/v1alpha1",
            kind="Middleware",
            metadata={"namespace": namespace},
            spec={
                "stripPrefix": {
                    "prefixes": [prefix],
                },
            },
            opts=pulumi.ResourceOptions(provider=opts.provider if opts else None)
        )

        # Create the ingress route
        k8s.apiextensions.CustomResource(
            f"{name}-ingress-route",
            api_version="traefik.containo.us/v1alpha1",
            kind="IngressRoute",
            metadata={"namespace": namespace},
            spec={
                "entryPoints": ["web"],
                "routes": [
                    {
                        "match": f"PathPrefix(\"{prefix}\")",
                        "kind": "Rule",
                        "middlewares": [
                            {"name": trailing_slash_middleware.metadata["name"]},
                            {"name": strip_prefix_middleware.metadata["name"]},
                        ],
                        "services": [
                            {
                                "name": pulumi.Output.all(service.metadata["name"]).apply(lambda name: name),
                                "port": pulumi.Output.all(service.spec["ports"][0]["port"]).apply(lambda port: port),
                            },
                        ],
                    }
                ],
            },
            opts=pulumi.ResourceOptions(
                provider=opts.provider if opts else None,
                depends_on=[trailing_slash_middleware, strip_prefix_middleware]
            )
        )

        self.register_outputs({})
