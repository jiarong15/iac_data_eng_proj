import pulumi
import pulumi_aws as aws
import pulumi_kubernetes as k8s

class S3ServiceAccount(pulumi.ComponentResource):
    def __init__(self, name: str, args: dict, opts: pulumi.ResourceOptions = None):
        super().__init__("pkg:index:S3ServiceAccount", name, None, opts)

        # Unpack arguments
        oidc_provider = args.get("oidcProvider")
        namespace = args.get("namespace")
        read_only = args.get("readOnly", True)

        # Create the IAM policy document for the Service Account
        service_account_assume_role_policy = pulumi.Output.all(
            oidc_provider.url, oidc_provider.arn, namespace
        ).apply(lambda args: aws.iam.get_policy_document(
            statements=[{
                "actions": ["sts:AssumeRoleWithWebIdentity"],
                "conditions": [{
                    "test": "StringEquals",
                    "values": [f"system:serviceaccount:{args[2]}:{name}"],
                    "variable": f"{args[0].replace('https://', '')}:sub",
                }],
                "effect": "Allow",
                "principals": [{"identifiers": [args[1]], "type": "Federated"}]
            }]
        ))

        # Create a new IAM role for the Service Account
        service_account_role = aws.iam.Role(
            name,
            assume_role_policy=service_account_assume_role_policy.json
        )

        # Attach the IAM role to an AWS S3 access policy
        aws.iam.RolePolicyAttachment(
            name,
            policy_arn=(
                "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
                if read_only else
                "arn:aws:iam::aws:policy/AmazonS3FullAccess"
            ),
            role=service_account_role.name
        )

        # Create a Kubernetes Service Account annotated with the IAM role
        self.service_account = k8s.core.v1.ServiceAccount(
            name,
            metadata={
                "namespace": namespace,
                "name": name,
                "annotations": {
                    "eks.amazonaws.com/role-arn": service_account_role.arn
                }
            },
            opts=pulumi.ResourceOptions(provider=opts.provider if opts else None)
        )

        # Outputs
        self.name = self.service_account.metadata["name"]

        self.register_outputs({
            "name": self.name,
            "serviceAccount": self.service_account
        })
